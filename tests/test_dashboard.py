from pathlib import Path

import pytest

from mafia_bot.database.session import create_session_factory, init_db
from mafia_bot.services.dashboard import DashboardService
from mafia_bot.services.games import GameService
from mafia_bot.services.roles import ensure_default_roles


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_dashboard_hides_alive_roles_and_reveals_dead(tmp_path: Path) -> None:
    factory = create_session_factory(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await init_db(factory)
    await ensure_default_roles(factory)

    async with factory() as session:
        game_service = GameService(session)
        await game_service.create_lobby(-100, "Watch Party", 1, "Owner")
        for user_id in range(2, 6):
            await game_service.join_lobby(-100, user_id, f"Player {user_id}", None)
        await game_service.set_lobby_roles(-100, ["mafia", "doctor", "sheriff", "citizen", "citizen"])
        assignments = await game_service.start_game(-100)

        snapshot = await DashboardService(session).active_game_for_chat(-100)
        assert snapshot is not None
        assert all(player.role_name is None for player in snapshot.players)

        mafia = next(assignment for assignment in assignments if assignment.role_name == "Мафия")
        citizen = next(
            assignment
            for assignment in assignments
            if assignment.role_name == "Мирный житель" and assignment.telegram_user_id != 1
        )
        menu = await game_service.get_night_action_menu(-100, mafia.telegram_user_id)
        assert menu is not None
        target = next(item for item in menu.targets if item.display_name == citizen.display_name)
        await game_service.record_night_action(-100, mafia.telegram_user_id, target.player_id)
        await game_service.resolve_night(-100)

        snapshot = await DashboardService(session).active_game_for_chat(-100)
        assert snapshot is not None
        dead = next(player for player in snapshot.players if player.status == "dead")
        assert dead.role_name == "Мирный житель"
        assert any(player.status == "alive" and player.role_name is None for player in snapshot.players)

    await factory.kw["bind"].dispose()
