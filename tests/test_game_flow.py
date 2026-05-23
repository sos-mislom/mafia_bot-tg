from pathlib import Path

import pytest

from mafia_bot.database.session import create_session_factory, init_db
from mafia_bot.services.games import GameService
from mafia_bot.services.roles import RoleService, ensure_default_roles


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_night_and_vote_flow(tmp_path: Path) -> None:
    factory = create_session_factory(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await init_db(factory)
    await ensure_default_roles(factory)

    async with factory() as session:
        service = GameService(session)
        await service.create_lobby(-100, "Chat", 1, "Owner")
        for user_id in range(2, 6):
            await service.join_lobby(-100, user_id, f"Player {user_id}", None)
        await service.set_lobby_roles(-100, ["mafia", "doctor", "sheriff", "citizen", "citizen"])
        assignments = await service.start_game(-100)

        mafia_assignment = next(assignment for assignment in assignments if assignment.role_name == "Мафия")
        citizen_assignment = next(
            assignment
            for assignment in assignments
            if assignment.role_name == "Мирный житель" and assignment.telegram_user_id != 1
        )
        night_menu = await service.get_night_action_menu(-100, mafia_assignment.telegram_user_id)
        assert night_menu is not None
        citizen_target = next(
            target for target in night_menu.targets if target.display_name == citizen_assignment.display_name
        )

        await service.record_night_action(
            -100,
            mafia_assignment.telegram_user_id,
            citizen_target.player_id,
        )
        night_result = await service.resolve_night(-100)
        assert "погиб ночью" in night_result.message

        await service.start_vote(-100)
        vote_targets = await service.list_vote_targets(-100)
        target = vote_targets[0]
        for assignment in assignments:
            if assignment.telegram_user_id != citizen_assignment.telegram_user_id:
                await service.cast_vote(-100, assignment.telegram_user_id, target.player_id)
        vote_result = await service.resolve_vote(-100)
        assert "Наступает ночь" in vote_result.message or vote_result.finished

    await factory.kw["bind"].dispose()


@pytest.mark.anyio
async def test_custom_role_can_be_used(tmp_path: Path) -> None:
    factory = create_session_factory(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    await init_db(factory)
    await ensure_default_roles(factory)

    async with factory() as session:
        role = await RoleService(session).upsert_role(
            code="maniac",
            name="Маньяк",
            team="neutral",
            description="Играет сам за себя.",
            night_action="kill",
        )
        assert role.code == "maniac"

    await factory.kw["bind"].dispose()
