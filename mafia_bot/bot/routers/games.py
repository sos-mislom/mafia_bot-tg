from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from mafia_bot.bot.telegram_features import dashboard_keyboard, react_to_message
from mafia_bot.config import get_settings
from mafia_bot.services.games import ActionTarget, GameService, NightActionMenu, RoleAssignment

router = Router(name="games")


class NightActionCallback(CallbackData, prefix="night"):
    chat_id: int
    target_player_id: int


class VoteCallback(CallbackData, prefix="vote"):
    chat_id: int
    target_player_id: int


def _display_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Игрок"
    return user.full_name or user.username or str(user.id)


def _telegram_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Команда доступна только пользователям Telegram.")
    return message.from_user.id


def _targets_keyboard(
    chat_id: int,
    targets: list[ActionTarget],
    callback_type: type[NightActionCallback] | type[VoteCallback],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for target in targets:
        builder.button(
            text=target.display_name,
            callback_data=callback_type(chat_id=chat_id, target_player_id=target.player_id),
        )
    builder.adjust(1)
    return builder.as_markup()


async def _send_role(bot: Bot, assignment: RoleAssignment) -> bool:
    text = (
        f"<b>Твоя роль: {assignment.role_name}</b>\n\n"
        f"{assignment.role_description}\n\n"
        f"Команда: <b>{assignment.team}</b>"
    )
    try:
        if assignment.image_path:
            await bot.send_photo(
                chat_id=assignment.telegram_user_id,
                photo=FSInputFile(assignment.image_path),
                caption=text,
            )
        elif assignment.image_file_id:
            await bot.send_photo(
                chat_id=assignment.telegram_user_id,
                photo=assignment.image_file_id,
                caption=text,
            )
        else:
            await bot.send_message(assignment.telegram_user_id, text)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return True


async def _send_night_menu(
    bot: Bot,
    telegram_user_id: int,
    chat_id: int,
    menu: NightActionMenu,
) -> bool:
    if not menu.targets:
        return True
    try:
        await bot.send_message(
            telegram_user_id,
            f"<b>Ночь. {menu.role_name}</b>\nВыбери цель:",
            reply_markup=_targets_keyboard(chat_id, menu.targets, NightActionCallback),
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return True


async def _notify_night_roles(bot: Bot, chat_id: int, service: GameService) -> tuple[int, int]:
    menus = await service.list_night_menus(chat_id)
    delivered = 0
    for telegram_user_id, menu in menus:
        if await _send_night_menu(bot, telegram_user_id, chat_id, menu):
            delivered += 1
    return delivered, len(menus)


@router.message(Command("game"))
async def create_game(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    game = await service.create_lobby(
        chat_id=message.chat.id,
        chat_title=message.chat.title or message.chat.full_name or str(message.chat.id),
        owner_telegram_id=_telegram_user_id(message),
        owner_name=_display_name(message),
    )
    await session.commit()

    settings = get_settings()
    dashboard_url = f"{settings.public_base_url.rstrip('/')}/chats/{message.chat.id}"
    await message.answer(
        "Лобби создано. Игроки могут нажать /join.\n"
        f"Сейчас игроков: {len(game.players)}.\n"
        "Когда все готовы, ведущий запускает /begin.",
        reply_markup=dashboard_keyboard(
            dashboard_url,
            use_web_app=message.chat.type == "private",
        )
        if settings.web_enabled
        else None,
    )
    await react_to_message(bot, message.chat.id, message.message_id, "👍")


@router.message(Command("join"))
async def join_game(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    try:
        players = await service.join_lobby(
            chat_id=message.chat.id,
            telegram_user_id=_telegram_user_id(message),
            display_name=_display_name(message),
            username=message.from_user.username if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(str(error))
        return
    await session.commit()
    await message.answer(f"{_display_name(message)} в игре. Игроков: {len(players)}.")
    await react_to_message(bot, message.chat.id, message.message_id, "🎲")


@router.message(Command("players"))
async def list_players(message: Message, session: AsyncSession) -> None:
    service = GameService(session)
    players = await service.list_lobby_players(message.chat.id)
    if not players:
        await message.answer("Активного лобби пока нет. Создать можно командой /game.")
        return
    lines = "\n".join(f"{index}. {player.display_name}" for index, player in enumerate(players, 1))
    await message.answer(f"<b>Игроки</b>\n{lines}")


@router.message(Command("dashboard"))
async def dashboard_link(message: Message) -> None:
    settings = get_settings()
    if not settings.web_enabled:
        await message.answer("Web-dashboard отключен.")
        return
    url = f"{settings.public_base_url.rstrip('/')}/chats/{message.chat.id}"
    await message.answer(
        f"Live-dashboard этой партии:\n{url}",
        reply_markup=dashboard_keyboard(url, use_web_app=message.chat.type == "private"),
    )


@router.message(Command("begin"))
async def begin_game(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    try:
        assignments = await service.start_game(message.chat.id)
    except ValueError as error:
        await message.answer(str(error))
        return
    await session.commit()

    delivered = 0
    for assignment in assignments:
        if await _send_role(bot, assignment):
            delivered += 1
    night_delivered, night_total = await _notify_night_roles(bot, message.chat.id, service)

    await message.answer(
        "Игра началась. Роли разданы в личные сообщения.\n"
        f"Роли доставлены: {delivered}/{len(assignments)}.\n"
        f"Ночные меню доставлены: {night_delivered}/{night_total}.\n"
        "Если роль не пришла, игроку нужно открыть личный чат с ботом и нажать /start."
    )
    await react_to_message(bot, message.chat.id, message.message_id, "🔥")


@router.message(Command("cancel"))
async def cancel_game(message: Message, session: AsyncSession) -> None:
    service = GameService(session)
    cancelled = await service.cancel_lobby(message.chat.id)
    await session.commit()
    if cancelled:
        await message.answer("Лобби отменено.")
    else:
        await message.answer("Активного лобби нет.")


@router.message(Command("setroles"))
async def set_lobby_roles(message: Message, session: AsyncSession) -> None:
    role_codes = message.text.split()[1:] if message.text else []
    if not role_codes:
        await message.answer("Формат: /setroles sheriff doctor mafia citizen")
        return
    service = GameService(session)
    try:
        await service.set_lobby_roles(message.chat.id, role_codes)
    except ValueError as error:
        await message.answer(str(error))
        return
    await session.commit()
    await message.answer("Набор ролей для лобби сохранен.")


@router.message(Command("night"))
async def resend_night_actions(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    delivered, total = await _notify_night_roles(bot, message.chat.id, service)
    await message.answer(f"Ночные меню отправлены: {delivered}/{total}.")


@router.message(Command("day"))
@router.message(Command("night_end"))
async def resolve_night(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    try:
        result = await service.resolve_night(message.chat.id)
    except ValueError as error:
        await message.answer(str(error))
        return
    await session.commit()
    await message.answer(result.message)
    await react_to_message(bot, message.chat.id, message.message_id, "🌅")


@router.message(Command("vote"))
async def start_vote(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    try:
        await service.start_vote(message.chat.id)
    except ValueError as error:
        await message.answer(str(error))
        return
    targets = await service.list_vote_targets(message.chat.id)
    await session.commit()
    await message.answer(
        "<b>Голосование открыто</b>\nВыберите, кого вывести днем:",
        reply_markup=_targets_keyboard(message.chat.id, targets, VoteCallback),
    )
    await react_to_message(bot, message.chat.id, message.message_id, "🗳")


@router.message(Command("vote_end"))
async def resolve_vote(message: Message, bot: Bot, session: AsyncSession) -> None:
    service = GameService(session)
    try:
        result = await service.resolve_vote(message.chat.id)
        night_delivered = (0, 0)
        if not result.finished:
            night_delivered = await _notify_night_roles(bot, message.chat.id, service)
    except ValueError as error:
        await message.answer(str(error))
        return
    await session.commit()
    suffix = ""
    if not result.finished:
        suffix = f"\nНочные меню доставлены: {night_delivered[0]}/{night_delivered[1]}."
    await message.answer(result.message + suffix)
    await react_to_message(bot, message.chat.id, message.message_id, "✅")


@router.callback_query(NightActionCallback.filter())
async def choose_night_target(
    callback: CallbackQuery,
    callback_data: NightActionCallback,
    session: AsyncSession,
) -> None:
    service = GameService(session)
    try:
        result = await service.record_night_action(
            callback_data.chat_id,
            callback.from_user.id,
            callback_data.target_player_id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await session.commit()
    await callback.answer(result, show_alert=True)


@router.callback_query(VoteCallback.filter())
async def choose_vote_target(
    callback: CallbackQuery,
    callback_data: VoteCallback,
    session: AsyncSession,
) -> None:
    service = GameService(session)
    try:
        result = await service.cast_vote(
            callback_data.chat_id,
            callback.from_user.id,
            callback_data.target_player_id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await session.commit()
    await callback.answer(result, show_alert=True)
