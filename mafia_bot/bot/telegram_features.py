from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReactionTypeEmoji,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def dashboard_keyboard(url: str, use_web_app: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if use_web_app and url.startswith("https://"):
        builder.add(
            InlineKeyboardButton(
                text="Открыть Mafia Live",
                web_app=WebAppInfo(url=url),
                style="primary",
            )
        )
    builder.add(InlineKeyboardButton(text="Открыть в браузере", url=url))
    builder.add(
        InlineKeyboardButton(
            text="Скопировать ссылку",
            copy_text=CopyTextButton(text=url),
        )
    )
    builder.adjust(1)
    return builder.as_markup()


async def react_to_message(bot: Bot, chat_id: int, message_id: int, emoji: str) -> None:
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        return
