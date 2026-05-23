from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mafia_bot.database.models import Chat, Game, GamePhase, GamePlayer, GameStatus, PlayerStatus, Role


@dataclass(frozen=True)
class DashboardPlayer:
    id: int
    name: str
    status: str
    role_name: str | None
    role_team: str | None


@dataclass(frozen=True)
class DashboardGame:
    id: int
    chat_title: str
    chat_telegram_id: int
    status: str
    phase: str
    day_number: int
    winner_team: str | None
    players: list[DashboardPlayer]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DashboardRole:
    code: str
    name: str
    team: str
    description: str
    night_action: str | None
    has_image: bool


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def latest_games(self, limit: int = 12) -> list[DashboardGame]:
        games = (
            await self.session.scalars(
                select(Game)
                .options(
                    selectinload(Game.chat),
                    selectinload(Game.players).selectinload(GamePlayer.user),
                    selectinload(Game.players).selectinload(GamePlayer.role),
                )
                .order_by(Game.id.desc())
                .limit(limit)
            )
        ).all()
        return [self._game_to_dashboard(game) for game in games]

    async def game_by_id(self, game_id: int) -> DashboardGame | None:
        game = await self.session.scalar(
            select(Game)
            .options(
                selectinload(Game.chat),
                selectinload(Game.players).selectinload(GamePlayer.user),
                selectinload(Game.players).selectinload(GamePlayer.role),
            )
            .where(Game.id == game_id)
        )
        if game is None:
            return None
        return self._game_to_dashboard(game)

    async def active_game_for_chat(self, chat_telegram_id: int) -> DashboardGame | None:
        game = await self.session.scalar(
            select(Game)
            .join(Chat)
            .options(
                selectinload(Game.chat),
                selectinload(Game.players).selectinload(GamePlayer.user),
                selectinload(Game.players).selectinload(GamePlayer.role),
            )
            .where(
                Chat.telegram_id == chat_telegram_id,
                Game.status.in_([GameStatus.LOBBY, GameStatus.RUNNING]),
            )
            .order_by(Game.id.desc())
        )
        if game is None:
            return None
        return self._game_to_dashboard(game)

    async def roles(self) -> list[DashboardRole]:
        roles = (await self.session.scalars(select(Role).order_by(Role.team, Role.name))).all()
        return [
            DashboardRole(
                code=role.code,
                name=role.name,
                team=role.team,
                description=role.description,
                night_action=role.night_action,
                has_image=bool(role.image_file_id or role.image_path),
            )
            for role in roles
        ]

    def _game_to_dashboard(self, game: Game) -> DashboardGame:
        reveal_all_roles = game.status == GameStatus.FINISHED or game.phase == GamePhase.FINISHED
        players = sorted(game.players, key=lambda player: player.id)
        return DashboardGame(
            id=game.id,
            chat_title=game.chat.title,
            chat_telegram_id=game.chat.telegram_id,
            status=game.status.value,
            phase=game.phase.value,
            day_number=game.day_number,
            winner_team=game.winner_team,
            players=[
                DashboardPlayer(
                    id=player.id,
                    name=player.user.display_name,
                    status=player.status.value,
                    role_name=self._public_role_name(player, reveal_all_roles),
                    role_team=self._public_role_team(player, reveal_all_roles),
                )
                for player in players
                if player.status != PlayerStatus.LEFT
            ],
        )

    def _public_role_name(self, player: GamePlayer, reveal_all_roles: bool) -> str | None:
        if player.role is None:
            return None
        if reveal_all_roles or player.status == PlayerStatus.DEAD:
            return player.role.name
        return None

    def _public_role_team(self, player: GamePlayer, reveal_all_roles: bool) -> str | None:
        if player.role is None:
            return None
        if reveal_all_roles or player.status == PlayerStatus.DEAD:
            return player.role.team
        return None
