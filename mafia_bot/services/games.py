from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mafia_bot.database.models import (
    ActionStatus,
    Chat,
    Game,
    GameAction,
    GamePhase,
    GamePlayer,
    GameStatus,
    PlayerStatus,
    Role,
    User,
    Vote,
)
from mafia_bot.domain.roles import MAFIA, TOWN, build_classic_role_codes, check_winner


@dataclass(frozen=True)
class LobbyPlayer:
    telegram_user_id: int
    display_name: str


@dataclass(frozen=True)
class RoleAssignment:
    telegram_user_id: int
    display_name: str
    role_name: str
    role_description: str
    team: str
    night_action: str | None
    image_file_id: str | None
    image_path: str | None


@dataclass(frozen=True)
class ActionTarget:
    player_id: int
    display_name: str


@dataclass(frozen=True)
class NightActionMenu:
    action_type: str
    role_name: str
    targets: list[ActionTarget]


@dataclass(frozen=True)
class PhaseResolution:
    message: str
    finished: bool = False


class GameService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_lobby(
        self,
        chat_id: int,
        chat_title: str,
        owner_telegram_id: int,
        owner_name: str,
    ) -> Game:
        active = await self._get_active_game(chat_id)
        if active:
            return active

        chat = await self._upsert_chat(chat_id, chat_title)
        owner = await self._upsert_user(owner_telegram_id, owner_name, None)
        game = Game(chat=chat, owner_user_id=owner.id, status=GameStatus.LOBBY, phase=GamePhase.LOBBY)
        self.session.add(game)
        await self.session.flush()

        self.session.add(GamePlayer(game_id=game.id, user_id=owner.id, is_owner=True))
        await self.session.flush()
        return await self._load_game(game.id)

    async def join_lobby(
        self,
        chat_id: int,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
    ) -> list[LobbyPlayer]:
        game = await self._get_active_game(chat_id)
        if game is None or game.status != GameStatus.LOBBY:
            raise ValueError("Сначала создайте лобби командой /game.")

        user = await self._upsert_user(telegram_user_id, display_name, username)
        existing = await self.session.scalar(
            select(GamePlayer).where(GamePlayer.game_id == game.id, GamePlayer.user_id == user.id)
        )
        if existing is None:
            self.session.add(GamePlayer(game_id=game.id, user_id=user.id))
            await self.session.flush()
        return await self.list_lobby_players(chat_id)

    async def list_lobby_players(self, chat_id: int) -> list[LobbyPlayer]:
        game = await self._get_active_game(chat_id)
        if game is None:
            return []
        await self.session.refresh(game, attribute_names=["players"])
        players = await self.session.scalars(
            select(GamePlayer)
            .options(selectinload(GamePlayer.user))
            .where(GamePlayer.game_id == game.id)
            .order_by(GamePlayer.id)
        )
        return [
            LobbyPlayer(player.user.telegram_id, player.user.display_name)
            for player in players
            if player.status != PlayerStatus.LEFT
        ]

    async def start_game(self, chat_id: int) -> list[RoleAssignment]:
        game = await self._get_active_game(chat_id)
        if game is None or game.status != GameStatus.LOBBY:
            raise ValueError("Активного лобби нет.")

        players = (
            await self.session.scalars(
                select(GamePlayer)
                .options(selectinload(GamePlayer.user))
                .where(GamePlayer.game_id == game.id, GamePlayer.status == PlayerStatus.ALIVE)
                .order_by(GamePlayer.id)
            )
        ).all()
        role_codes = build_classic_role_codes(len(players))
        if game.settings.get("role_codes"):
            role_codes = list(game.settings["role_codes"])
            if len(role_codes) != len(players):
                raise ValueError("Количество ролей в /setroles должно совпадать с числом игроков.")

        roles = {
            role.code: role
            for role in (
                await self.session.scalars(select(Role).where(Role.code.in_(set(role_codes))))
            ).all()
        }

        assignments: list[RoleAssignment] = []
        for player, role_code in zip(players, role_codes, strict=True):
            role = roles[role_code]
            player.role_id = role.id
            assignments.append(
                RoleAssignment(
                    telegram_user_id=player.user.telegram_id,
                    display_name=player.user.display_name,
                    role_name=role.name,
                    role_description=role.description,
                    team=role.team,
                    night_action=role.night_action,
                    image_file_id=role.image_file_id,
                    image_path=role.image_path,
                )
            )

        game.status = GameStatus.RUNNING
        game.phase = GamePhase.NIGHT
        game.day_number = 1
        await self.session.flush()
        return assignments

    async def list_night_menus(self, chat_id: int) -> list[tuple[int, NightActionMenu]]:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.NIGHT:
            return []

        result: list[tuple[int, NightActionMenu]] = []
        for player in await self._alive_players(game.id):
            if player.role is None or not player.role.night_action:
                continue
            menu = await self.get_night_action_menu(chat_id, player.user.telegram_id)
            if menu is not None:
                result.append((player.user.telegram_id, menu))
        return result

    async def set_lobby_roles(self, chat_id: int, role_codes: list[str]) -> None:
        game = await self._get_active_game(chat_id)
        if game is None or game.status != GameStatus.LOBBY:
            raise ValueError("Активного лобби нет.")

        players = await self.list_lobby_players(chat_id)
        if len(role_codes) != len(players):
            raise ValueError(f"Нужно {len(players)} ролей, получено {len(role_codes)}.")

        existing = set((await self.session.scalars(select(Role.code))).all())
        missing = sorted(set(role_codes) - existing)
        if missing:
            raise ValueError(f"Неизвестные роли: {', '.join(missing)}.")

        game.settings = {**(game.settings or {}), "role_codes": role_codes}
        await self.session.flush()

    async def get_night_action_menu(
        self,
        chat_id: int,
        telegram_user_id: int,
    ) -> NightActionMenu | None:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.NIGHT:
            return None

        actor = await self._get_player_by_telegram_id(game.id, telegram_user_id)
        if actor is None or actor.status != PlayerStatus.ALIVE or actor.role is None:
            return None
        if not actor.role.night_action:
            return None

        players = await self._alive_players(game.id)
        targets = [
            ActionTarget(player.id, player.user.display_name)
            for player in players
            if self._is_valid_night_target(actor, player)
        ]
        return NightActionMenu(actor.role.night_action, actor.role.name, targets)

    async def record_night_action(
        self,
        chat_id: int,
        actor_telegram_id: int,
        target_player_id: int,
    ) -> str:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.NIGHT:
            raise ValueError("Сейчас не ночь.")

        actor = await self._get_player_by_telegram_id(game.id, actor_telegram_id)
        target = await self._get_player(target_player_id)
        if actor is None or actor.status != PlayerStatus.ALIVE or actor.role is None:
            raise ValueError("Ты не активный игрок этой партии.")
        if not actor.role.night_action:
            raise ValueError("У твоей роли нет ночного действия.")
        if target is None or target.game_id != game.id or target.status != PlayerStatus.ALIVE:
            raise ValueError("Цель недоступна.")
        if not self._is_valid_night_target(actor, target):
            raise ValueError("Эту цель выбрать нельзя.")

        existing = await self.session.scalar(
            select(GameAction).where(
                GameAction.game_id == game.id,
                GameAction.actor_player_id == actor.id,
                GameAction.day_number == game.day_number,
            )
        )
        if existing is None:
            self.session.add(
                GameAction(
                    game_id=game.id,
                    actor_player_id=actor.id,
                    target_player_id=target.id,
                    action_type=actor.role.night_action,
                    day_number=game.day_number,
                )
            )
        else:
            existing.target_player_id = target.id
            existing.action_type = actor.role.night_action
            existing.status = ActionStatus.PENDING

        await self.session.flush()
        if actor.role.night_action == "check_team":
            return f"{target.user.display_name}: команда {target.role.team if target.role else 'unknown'}."
        if actor.role.night_action == "find_sheriff":
            result = "да" if target.role and target.role.code == "sheriff" else "нет"
            return f"{target.user.display_name} шериф? {result}."
        return f"Выбрана цель: {target.user.display_name}."

    async def resolve_night(self, chat_id: int) -> PhaseResolution:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.NIGHT:
            raise ValueError("Сейчас не ночь.")

        actions = (
            await self.session.scalars(
                select(GameAction)
                .options(
                    selectinload(GameAction.actor).selectinload(GamePlayer.role),
                    selectinload(GameAction.target).selectinload(GamePlayer.user),
                    selectinload(GameAction.target).selectinload(GamePlayer.role),
                )
                .where(
                    GameAction.game_id == game.id,
                    GameAction.day_number == game.day_number,
                    GameAction.status == ActionStatus.PENDING,
                )
            )
        ).all()

        healed_ids = {action.target_player_id for action in actions if action.action_type == "heal"}
        killed: list[GamePlayer] = []
        for action in actions:
            if action.action_type != "kill":
                continue
            if action.target_player_id in healed_ids:
                continue
            if action.target not in killed:
                killed.append(action.target)

        for player in killed:
            player.status = PlayerStatus.DEAD
        for action in actions:
            action.status = ActionStatus.RESOLVED

        winner = await self._winner_for_game(game.id)
        if winner:
            game.status = GameStatus.FINISHED
            game.phase = GamePhase.FINISHED
            game.winner_team = winner
            await self.session.flush()
            deaths = self._format_deaths(killed)
            return PhaseResolution(f"{deaths}\nПобедила команда: {winner}.", finished=True)

        game.phase = GamePhase.DAY
        await self.session.flush()
        deaths = self._format_deaths(killed)
        return PhaseResolution(f"{deaths}\nНаступил день. Обсуждение открыто.")

    async def start_vote(self, chat_id: int) -> None:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.DAY:
            raise ValueError("Голосование можно начать только днем.")
        game.phase = GamePhase.VOTING
        await self.session.flush()

    async def list_vote_targets(self, chat_id: int) -> list[ActionTarget]:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.VOTING:
            return []
        return [ActionTarget(player.id, player.user.display_name) for player in await self._alive_players(game.id)]

    async def cast_vote(self, chat_id: int, voter_telegram_id: int, target_player_id: int) -> str:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.VOTING:
            raise ValueError("Сейчас нет голосования.")

        voter = await self._get_player_by_telegram_id(game.id, voter_telegram_id)
        target = await self._get_player(target_player_id)
        if voter is None or voter.status != PlayerStatus.ALIVE:
            raise ValueError("Голосовать могут только живые игроки.")
        if target is None or target.game_id != game.id or target.status != PlayerStatus.ALIVE:
            raise ValueError("Цель недоступна.")

        existing = await self.session.scalar(
            select(Vote).where(
                Vote.game_id == game.id,
                Vote.voter_player_id == voter.id,
                Vote.day_number == game.day_number,
            )
        )
        if existing is None:
            self.session.add(
                Vote(
                    game_id=game.id,
                    voter_player_id=voter.id,
                    target_player_id=target.id,
                    day_number=game.day_number,
                )
            )
        else:
            existing.target_player_id = target.id

        await self.session.flush()
        return f"Голос принят: {target.user.display_name}."

    async def resolve_vote(self, chat_id: int) -> PhaseResolution:
        game = await self._get_active_game(chat_id)
        if game is None or game.phase != GamePhase.VOTING:
            raise ValueError("Сейчас нет голосования.")

        votes = (
            await self.session.scalars(
                select(Vote)
                .options(selectinload(Vote.target).selectinload(GamePlayer.user))
                .where(Vote.game_id == game.id, Vote.day_number == game.day_number)
            )
        ).all()
        if not votes:
            game.phase = GamePhase.NIGHT
            game.day_number += 1
            await self.session.flush()
            return PhaseResolution("Голосов нет. Наступает ночь.")

        counts: dict[int, int] = {}
        targets: dict[int, GamePlayer] = {}
        for vote in votes:
            counts[vote.target_player_id] = counts.get(vote.target_player_id, 0) + 1
            targets[vote.target_player_id] = vote.target

        max_votes = max(counts.values())
        leaders = [player_id for player_id, count in counts.items() if count == max_votes]
        if len(leaders) == 1:
            eliminated = targets[leaders[0]]
            eliminated.status = PlayerStatus.DEAD
            result = f"Игрок выбыл днем: {eliminated.user.display_name} ({max_votes} голосов)."
        else:
            result = "Ничья на голосовании. Никто не выбыл."

        winner = await self._winner_for_game(game.id)
        if winner:
            game.status = GameStatus.FINISHED
            game.phase = GamePhase.FINISHED
            game.winner_team = winner
            await self.session.flush()
            return PhaseResolution(f"{result}\nПобедила команда: {winner}.", finished=True)

        game.phase = GamePhase.NIGHT
        game.day_number += 1
        await self.session.flush()
        return PhaseResolution(f"{result}\nНаступает ночь.")

    async def cancel_lobby(self, chat_id: int) -> bool:
        game = await self._get_active_game(chat_id)
        if game is None or game.status != GameStatus.LOBBY:
            return False
        game.status = GameStatus.CANCELLED
        game.phase = GamePhase.FINISHED
        await self.session.flush()
        return True

    async def _upsert_chat(self, telegram_id: int, title: str) -> Chat:
        chat = await self.session.scalar(select(Chat).where(Chat.telegram_id == telegram_id))
        if chat is None:
            chat = Chat(telegram_id=telegram_id, title=title)
            self.session.add(chat)
            await self.session.flush()
        else:
            chat.title = title
        return chat

    async def _upsert_user(
        self,
        telegram_id: int,
        display_name: str,
        username: str | None,
    ) -> User:
        user = await self.session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None:
            user = User(telegram_id=telegram_id, display_name=display_name, username=username)
            self.session.add(user)
            await self.session.flush()
        else:
            user.display_name = display_name
            user.username = username
        return user

    async def _get_active_game(self, chat_telegram_id: int) -> Game | None:
        return await self.session.scalar(
            select(Game)
            .join(Chat)
            .options(selectinload(Game.players))
            .where(
                Chat.telegram_id == chat_telegram_id,
                Game.status.in_([GameStatus.LOBBY, GameStatus.RUNNING]),
            )
            .order_by(Game.id.desc())
        )

    async def _load_game(self, game_id: int) -> Game:
        game = await self.session.scalar(
            select(Game).options(selectinload(Game.players)).where(Game.id == game_id)
        )
        if game is None:
            raise RuntimeError("Game disappeared after creation.")
        return game

    async def _alive_players(self, game_id: int) -> list[GamePlayer]:
        return (
            await self.session.scalars(
                select(GamePlayer)
                .options(selectinload(GamePlayer.user), selectinload(GamePlayer.role))
                .where(GamePlayer.game_id == game_id, GamePlayer.status == PlayerStatus.ALIVE)
                .order_by(GamePlayer.id)
            )
        ).all()

    async def _get_player_by_telegram_id(
        self,
        game_id: int,
        telegram_user_id: int,
    ) -> GamePlayer | None:
        return await self.session.scalar(
            select(GamePlayer)
            .join(User)
            .options(selectinload(GamePlayer.user), selectinload(GamePlayer.role))
            .where(GamePlayer.game_id == game_id, User.telegram_id == telegram_user_id)
        )

    async def _get_player(self, player_id: int) -> GamePlayer | None:
        return await self.session.scalar(
            select(GamePlayer)
            .options(selectinload(GamePlayer.user), selectinload(GamePlayer.role))
            .where(GamePlayer.id == player_id)
        )

    def _is_valid_night_target(self, actor: GamePlayer, target: GamePlayer) -> bool:
        action = actor.role.night_action if actor.role else None
        if action in {"kill", "heal"}:
            return True
        return actor.id != target.id

    async def _winner_for_game(self, game_id: int) -> str | None:
        alive = await self._alive_players(game_id)
        teams = [player.role.team for player in alive if player.role and player.role.team in {TOWN, MAFIA}]
        return check_winner(teams)

    def _format_deaths(self, killed: list[GamePlayer]) -> str:
        if not killed:
            return "Ночь прошла спокойно. Никто не погиб."
        lines = [
            f"{player.user.display_name} погиб ночью. Роль: {player.role.name if player.role else 'неизвестно'}."
            for player in killed
        ]
        return "\n".join(lines)
