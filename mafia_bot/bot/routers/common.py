from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="common")


HELP_TEXT = """
<b>Мафия</b>

/game - создать лобби
/join - вступить в игру
/players - список игроков
/dashboard - ссылка на live web-dashboard
/begin - начать игру
/night - повторно отправить ночные действия
/day - закрыть ночь и открыть день
/vote - начать дневное голосование
/vote_end - закрыть голосование
/roles - список ролей
/setroles - задать роли для лобби
/cancel - отменить лобби
""".strip()


@router.message(CommandStart())
@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT)
