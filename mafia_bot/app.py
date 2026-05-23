import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import uvicorn

from mafia_bot.bot.middleware import DbSessionMiddleware
from mafia_bot.bot.routers import admin, common, games
from mafia_bot.config import get_settings
from mafia_bot.database.session import create_session_factory, init_db
from mafia_bot.services.roles import ensure_default_roles
from mafia_bot.web.app import create_web_app
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    session_factory = create_session_factory(settings.database_url)
    await init_db(session_factory)
    await ensure_default_roles(session_factory)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await _configure_bot_surface(bot)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.middleware(DbSessionMiddleware(session_factory))
    dispatcher.include_router(common.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(games.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        polling = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
        )
        if settings.web_enabled:
            web = create_web_app(session_factory, settings)
            config = uvicorn.Config(
                web,
                host=settings.web_host,
                port=settings.web_port,
                log_level=settings.log_level.lower(),
            )
            server = uvicorn.Server(config)
            web_server = asyncio.create_task(server.serve())
            done, pending = await asyncio.wait(
                {polling, web_server},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
        else:
            await polling
    finally:
        await session_factory.kw["bind"].dispose()


async def _configure_bot_surface(bot: Bot) -> None:
    settings = get_settings()
    await bot.set_my_commands(
        [
            BotCommand(command="game", description="Создать лобби"),
            BotCommand(command="join", description="Вступить в игру"),
            BotCommand(command="players", description="Игроки за столом"),
            BotCommand(command="dashboard", description="Открыть Mafia Live"),
            BotCommand(command="begin", description="Начать игру"),
            BotCommand(command="night", description="Отправить ночные действия"),
            BotCommand(command="day", description="Закрыть ночь"),
            BotCommand(command="vote", description="Начать голосование"),
            BotCommand(command="vote_end", description="Закрыть голосование"),
            BotCommand(command="roles", description="Список ролей"),
        ]
    )
    if settings.web_enabled and settings.public_base_url.startswith("https://"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Mafia Live",
                    web_app=WebAppInfo(url=settings.public_base_url.rstrip("/")),
                )
            )
        except TelegramBadRequest:
            return
