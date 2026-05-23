from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from mafia_bot.database.models import Role, RolePreset, RolePresetRole
from mafia_bot.domain.roles import DEFAULT_ROLES


@dataclass(frozen=True)
class RoleView:
    code: str
    name: str
    team: str
    night_action: str | None
    has_image: bool
    description: str


async def ensure_default_roles(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        existing_codes = set((await session.scalars(select(Role.code))).all())
        roles_by_code: dict[str, Role] = {}

        for spec in DEFAULT_ROLES:
            role = await session.scalar(select(Role).where(Role.code == spec.code))
            if spec.code not in existing_codes:
                role = Role(
                    code=spec.code,
                    name=spec.name,
                    team=spec.team,
                    description=spec.description,
                    night_action=spec.night_action,
                    priority=spec.priority,
                    is_unique=spec.is_unique,
                    min_players=spec.min_players,
                    ability_config=spec.ability_config,
                )
                session.add(role)
            elif role is not None:
                role.name = spec.name
                role.team = spec.team
                role.description = spec.description
                role.night_action = spec.night_action
                role.priority = spec.priority
                role.is_unique = spec.is_unique
                role.min_players = spec.min_players
                role.ability_config = spec.ability_config
            if role is not None:
                roles_by_code[spec.code] = role

        preset = await session.scalar(select(RolePreset).where(RolePreset.code == "classic"))
        if preset is None:
            preset = RolePreset(
                code="classic",
                name="Классика",
                description="Автоматический классический набор ролей по числу игроков.",
                min_players=4,
                max_players=None,
            )
            session.add(preset)

        await session.flush()

        existing_links = set(
            (
                await session.execute(
                    select(RolePresetRole.role_id).where(RolePresetRole.preset_id == preset.id)
                )
            ).scalars()
        )
        for role in roles_by_code.values():
            if role.id not in existing_links:
                session.add(RolePresetRole(preset_id=preset.id, role_id=role.id, count=1))

        await session.commit()


class RoleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_roles(self) -> list[RoleView]:
        roles = (
            await self.session.scalars(
                select(Role).order_by(Role.team, Role.priority, Role.name)
            )
        ).all()
        return [
            RoleView(
                code=role.code,
                name=role.name,
                team=role.team,
                night_action=role.night_action,
                has_image=bool(role.image_file_id or role.image_path),
                description=role.description,
            )
            for role in roles
        ]

    async def upsert_role(
        self,
        code: str,
        name: str,
        team: str,
        description: str,
        night_action: str | None = None,
        priority: int = 100,
    ) -> RoleView:
        code = self._normalize_code(code)
        if not name.strip():
            raise ValueError("Название роли не может быть пустым.")
        if team not in {"town", "mafia", "neutral"}:
            raise ValueError("Команда должна быть town, mafia или neutral.")
        if night_action == "none":
            night_action = None

        role = await self.session.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(
                code=code,
                name=name.strip(),
                team=team,
                description=description.strip(),
                night_action=night_action,
                priority=priority,
            )
            self.session.add(role)
        else:
            role.name = name.strip()
            role.team = team
            role.description = description.strip()
            role.night_action = night_action
            role.priority = priority

        await self.session.flush()
        return RoleView(
            code=role.code,
            name=role.name,
            team=role.team,
            night_action=role.night_action,
            has_image=bool(role.image_file_id or role.image_path),
            description=role.description,
        )

    async def set_role_image(self, code: str, image_file_id: str) -> RoleView:
        role = await self.session.scalar(select(Role).where(Role.code == self._normalize_code(code)))
        if role is None:
            raise ValueError("Роль не найдена.")
        role.image_file_id = image_file_id
        role.image_path = None
        await self.session.flush()
        return RoleView(
            code=role.code,
            name=role.name,
            team=role.team,
            night_action=role.night_action,
            has_image=True,
            description=role.description,
        )

    def _normalize_code(self, code: str) -> str:
        normalized = code.strip().lower().replace("-", "_")
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("Код роли должен содержать только буквы, цифры и подчёркивания.")
        return normalized
