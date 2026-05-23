import pytest

from mafia_bot.domain.roles import MAFIA, TOWN, build_classic_role_codes, check_winner


def test_classic_roles_match_player_count() -> None:
    roles = build_classic_role_codes(7)

    assert len(roles) == 7
    assert "sheriff" in roles
    assert "doctor" in roles
    assert "don" in roles
    assert any(role in {"mafia", "don"} for role in roles)


def test_classic_roles_require_minimum_players() -> None:
    with pytest.raises(ValueError):
        build_classic_role_codes(3)


def test_winner_conditions() -> None:
    assert check_winner([TOWN, TOWN]) == TOWN
    assert check_winner([MAFIA, TOWN]) == MAFIA
    assert check_winner([MAFIA, TOWN, TOWN]) is None
