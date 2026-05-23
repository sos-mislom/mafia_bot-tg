from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from mafia_bot.config import get_settings
from mafia_bot.services.roles import RoleService, RoleView

router = Router(name="admin")


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in get_settings().admins)


def _format_role(role: RoleView) -> str:
    action = role.night_action or "-"
    image = "yes" if role.has_image else "no"
    return f"<b>{role.code}</b> · {role.name} · {role.team} · action: {action} · image: {image}"


@router.message(Command("roles"))
async def list_roles(message: Message, session: AsyncSession) -> None:
    roles = await RoleService(session).list_roles()
    if not roles:
        await message.answer("Ролей пока нет.")
        return
    await message.answer("\n".join(_format_role(role) for role in roles))


@router.message(Command("role_add"))
async def add_role(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message):
        await message.answer("Команда доступна только администраторам бота.")
        return
    payload = (message.text or "").removeprefix("/role_add").strip()
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) < 4:
        await message.answer(
            "Формат: /role_add code | Название | team | описание | night_action | priority\n"
            "team: town, mafia, neutral. night_action можно пропустить или указать none."
        )
        return

    code, name, team, description = parts[:4]
    night_action = parts[4] if len(parts) >= 5 and parts[4] else None
    try:
        priority = int(parts[5]) if len(parts) >= 6 and parts[5] else 100
        role = await RoleService(session).upsert_role(
            code=code,
            name=name,
            team=team,
            description=description,
            night_action=night_action,
            priority=priority,
        )
    except ValueError as error:
        await message.answer(str(error))
        return

    await session.commit()
    await message.answer(f"Роль сохранена:\n{_format_role(role)}")


@router.message(Command("role_image"))
async def set_role_image(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message):
        await message.answer("Команда доступна только администраторам бота.")
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Формат: ответьте на фото командой /role_image code")
        return
    if message.reply_to_message is None or not message.reply_to_message.photo:
        await message.answer("Нужно ответить этой командой на сообщение с фото.")
        return

    image_file_id = message.reply_to_message.photo[-1].file_id
    try:
        role = await RoleService(session).set_role_image(args[1], image_file_id)
    except ValueError as error:
        await message.answer(str(error))
        return

    await session.commit()
    await message.answer(f"Картинка привязана к роли:\n{_format_role(role)}")
