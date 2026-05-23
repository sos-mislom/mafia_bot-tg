from dataclasses import dataclass, field
from random import shuffle


TOWN = "town"
MAFIA = "mafia"
NEUTRAL = "neutral"


@dataclass(frozen=True)
class RoleSpec:
    code: str
    name: str
    team: str
    description: str
    count: int = 1
    night_action: str | None = None
    priority: int = 100
    is_unique: bool = False
    min_players: int = 0
    ability_config: dict = field(default_factory=dict)


DEFAULT_ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(
        code="citizen",
        name="Мирный житель",
        team=TOWN,
        description="Ищет мафию днем и голосует на обсуждении.",
        count=99,
    ),
    RoleSpec(
        code="mafia",
        name="Мафия",
        team=MAFIA,
        description="Ночью выбирает жертву вместе с мафией.",
        count=2,
        night_action="kill",
        priority=40,
    ),
    RoleSpec(
        code="don",
        name="Дон",
        team=MAFIA,
        description="Глава мафии. Ночью ищет шерифа.",
        count=1,
        night_action="find_sheriff",
        priority=30,
        is_unique=True,
        min_players=6,
    ),
    RoleSpec(
        code="sheriff",
        name="Шериф",
        team=TOWN,
        description="Ночью проверяет команду одного игрока.",
        count=1,
        night_action="check_team",
        priority=20,
        is_unique=True,
        min_players=4,
    ),
    RoleSpec(
        code="doctor",
        name="Доктор",
        team=TOWN,
        description="Ночью лечит одного игрока.",
        count=1,
        night_action="heal",
        priority=10,
        is_unique=True,
        min_players=5,
    ),
)


def build_classic_role_codes(player_count: int) -> list[str]:
    if player_count < 4:
        raise ValueError("Для игры нужно минимум 4 игрока.")

    codes: list[str] = ["sheriff"]
    if player_count >= 5:
        codes.append("doctor")
    if player_count >= 6:
        codes.append("don")

    mafia_count = max(1, player_count // 4)
    if "don" in codes:
        mafia_count -= 1
    codes.extend(["mafia"] * max(1, mafia_count))

    while len(codes) < player_count:
        codes.append("citizen")

    codes = codes[:player_count]
    shuffle(codes)
    return codes


def check_winner(alive_teams: list[str]) -> str | None:
    mafia_alive = alive_teams.count(MAFIA)
    town_alive = alive_teams.count(TOWN)
    if mafia_alive == 0:
        return TOWN
    if mafia_alive >= town_alive:
        return MAFIA
    return None
