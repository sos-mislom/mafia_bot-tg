# Telegram Mafia Bot

Бот для игры в мафию в Telegram-группах. Проект сделан как расширяемая основа под кастомные роли, картинки ролей, статистику, web-dashboard и полноценный игровой цикл.

## Быстрый Старт

1. Скопируйте `.env.example` в `.env`.
2. Укажите `BOT_TOKEN` от BotFather.
3. Запустите:

```bash
docker compose up --build
```

После запуска web-dashboard доступен на `http://localhost:8000`.

Для локального запуска без Docker:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]
python -m mafia_bot
```

## Деплой На VPS

Требования: Ubuntu/Debian VPS, домен с A-записью на IP сервера, открытые порты `80` и `443`, установленный Docker Compose.

```bash
git clone <repo-url> mafia-bot
cd mafia-bot
cp .env.production.example .env
nano .env
sh scripts/deploy.sh
```

В `.env` обязательно заполнить:

- `BOT_TOKEN`
- `DOMAIN`
- `PUBLIC_BASE_URL=https://your-domain`
- `ACME_EMAIL`
- `ADMINS`

Production-запуск использует [docker-compose.prod.yml](docker-compose.prod.yml): бот работает внутри сети Docker, dashboard закрыт Caddy reverse proxy с автоматическим HTTPS, данные SQLite лежат в `./data`.

Проверка после запуска:

```bash
curl https://your-domain/healthz
docker compose -f docker-compose.prod.yml logs -f bot
```

## Команды

- `/start`, `/help` - справка.
- `/game` - создать лобби в текущем чате.
- `/join` - вступить в лобби.
- `/players` - показать игроков.
- `/dashboard` - ссылка на live web-dashboard текущей партии.
- `/setroles sheriff doctor mafia citizen` - задать точный набор ролей для лобби.
- `/begin` - начать игру и раздать роли в личные сообщения.
- `/night` - повторно отправить активным ролям ночные кнопки.
- `/day` или `/night_end` - закрыть ночь и открыть день.
- `/vote` - открыть дневное голосование.
- `/vote_end` - закрыть голосование и применить результат.
- `/roles` - показать доступные роли.
- `/role_add code | Название | team | описание | night_action | priority` - создать или обновить роль.
- `/role_image code` - ответом на фото привязать картинку к роли.
- `/cancel` - отменить лобби.

`/role_add` и `/role_image` доступны только пользователям из `ADMINS` в `.env`.

Команды `team`: `town`, `mafia`, `neutral`. Базовые `night_action`: `kill`, `heal`, `check_team`, `find_sheriff`, `none`.

## Web-Dashboard

Dashboard показывает партии, фазы, стол игроков, раскрытые роли выбывших и каталог ролей. Живые роли во время партии скрыты, чтобы страница не спойлерила игру.

В Telegram dashboard открывается современными inline-кнопками: Mini App-кнопка в личном чате, обычная URL-кнопка в группах и кнопка копирования ссылки. При старте бот также настраивает список команд и, если `PUBLIC_BASE_URL` начинается с `https://`, добавляет кнопку `Mafia Live` в меню бота.

JSON API:

```text
GET /api/games/<id>
GET /api/chats/<chat_id>/active
```

## Архитектура

- `mafia_bot/bot` - Telegram-роутеры и middleware.
- `mafia_bot/web` - FastAPI dashboard и публичное API.
- `mafia_bot/domain` - чистые правила игры и базовый каталог ролей.
- `mafia_bot/database` - SQLAlchemy-модели и сессии.
- `mafia_bot/services` - сценарии приложения: партии, игроки, роли, dashboard.
- `mafia_bot/assets` - будущие картинки ролей.
