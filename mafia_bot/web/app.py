from html import escape

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from mafia_bot.config import Settings
from mafia_bot.services.dashboard import DashboardGame, DashboardRole, DashboardService


def create_web_app(session_factory: async_sessionmaker, settings: Settings) -> FastAPI:
    app = FastAPI(title="Mafia Live Dashboard")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        async with session_factory() as session:
            dashboard = DashboardService(session)
            games = await dashboard.latest_games()
            roles = await dashboard.roles()
        return _page(
            "Mafia Live",
            _hero()
            + _games_section(games)
            + _roles_section(roles)
            + _api_hint(settings.public_base_url),
        )

    @app.get("/chats/{chat_id}", response_class=HTMLResponse)
    async def chat_game(chat_id: int) -> str:
        async with session_factory() as session:
            game = await DashboardService(session).active_game_for_chat(chat_id)
        if game is None:
            return _page("Mafia Live", _empty(f"Для чата {chat_id} активной партии нет."))
        return _page(f"Game #{game.id}", _game_section(game, full=True))

    @app.get("/games/{game_id}", response_class=HTMLResponse)
    async def game_page(game_id: int) -> str:
        async with session_factory() as session:
            game = await DashboardService(session).game_by_id(game_id)
        if game is None:
            return _page("Mafia Live", _empty("Партия не найдена."))
        return _page(f"Game #{game.id}", _game_section(game, full=True))

    @app.get("/api/games/{game_id}")
    async def game_api(game_id: int) -> dict:
        async with session_factory() as session:
            game = await DashboardService(session).game_by_id(game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return game.to_dict()

    @app.get("/api/chats/{chat_id}/active")
    async def active_game_api(chat_id: int) -> dict:
        async with session_factory() as session:
            game = await DashboardService(session).active_game_for_chat(chat_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Active game not found")
        return game.to_dict()

    return app


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="8">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101114;
      --panel: #191b20;
      --panel-2: #22252d;
      --text: #f4f1e8;
      --muted: #a9a392;
      --line: #343844;
      --red: #d75f54;
      --gold: #d4ad59;
      --green: #6fb37c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, #2a2020 0, transparent 34rem), var(--bg);
      color: var(--text);
    }}
    main {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 56px; }}
    a {{ color: inherit; text-decoration: none; }}
    .hero {{ display: grid; gap: 12px; padding: 36px 0 24px; border-bottom: 1px solid var(--line); }}
    .hero h1 {{ margin: 0; font-size: clamp(32px, 5vw, 64px); line-height: 1; letter-spacing: 0; }}
    .hero p {{ max-width: 720px; margin: 0; color: var(--muted); font-size: 18px; }}
    section {{ padding-top: 28px; }}
    h2 {{ margin: 0 0 16px; font-size: 24px; letter-spacing: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .card:hover {{ border-color: var(--gold); }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; color: var(--muted); font-size: 14px; }}
    .pill {{ padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-2); }}
    .players {{ display: grid; gap: 8px; }}
    .player {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; padding: 12px; background: var(--panel-2); border-radius: 8px; border: 1px solid var(--line); }}
    .dead {{ opacity: .62; }}
    .role {{ color: var(--gold); font-size: 14px; }}
    .status {{ color: var(--muted); font-size: 13px; text-transform: uppercase; }}
    .town {{ color: var(--green); }}
    .mafia {{ color: var(--red); }}
    .neutral {{ color: var(--gold); }}
    code {{ color: var(--gold); }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 20px, 1120px); padding-top: 18px; }}
      .player {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""


def _hero() -> str:
    return """
<header class="hero">
  <h1>Mafia Live</h1>
  <p>Веб-комната партии: фазы, стол игроков, раскрытые роли и каталог кастомных ролей рядом с Telegram-игрой.</p>
</header>"""


def _games_section(games: list[DashboardGame]) -> str:
    if not games:
        return _empty("Пока нет партий. Создайте лобби в Telegram командой /game.")
    cards = "".join(_game_card(game) for game in games)
    return f"<section><h2>Партии</h2><div class=\"grid\">{cards}</div></section>"


def _game_card(game: DashboardGame) -> str:
    return f"""
<a class="card" href="/games/{game.id}">
  <strong>{escape(game.chat_title)}</strong>
  <div class="meta">
    <span class="pill">game #{game.id}</span>
    <span class="pill">{escape(game.status)}</span>
    <span class="pill">{escape(game.phase)}</span>
    <span class="pill">day {game.day_number}</span>
  </div>
</a>"""


def _game_section(game: DashboardGame, full: bool = False) -> str:
    players = "".join(_player_row(player) for player in game.players)
    winner = f"<span class=\"pill\">winner: {escape(game.winner_team)}</span>" if game.winner_team else ""
    prefix = _hero() if full else ""
    return f"""{prefix}
<section>
  <h2>{escape(game.chat_title)}</h2>
  <div class="meta">
    <span class="pill">game #{game.id}</span>
    <span class="pill">{escape(game.status)}</span>
    <span class="pill">{escape(game.phase)}</span>
    <span class="pill">day {game.day_number}</span>
    {winner}
  </div>
  <div style="height:16px"></div>
  <div class="players">{players}</div>
</section>"""


def _player_row(player) -> str:
    role = "hidden"
    team_class = ""
    if player.role_name:
        role = player.role_name
        team_class = player.role_team or ""
    status_class = " dead" if player.status == "dead" else ""
    return f"""
<div class="player{status_class}">
  <div>
    <strong>{escape(player.name)}</strong>
    <div class="role {escape(team_class)}">{escape(role)}</div>
  </div>
  <div class="status">{escape(player.status)}</div>
</div>"""


def _roles_section(roles: list[DashboardRole]) -> str:
    if not roles:
        return ""
    cards = "".join(_role_card(role) for role in roles)
    return f"<section><h2>Роли</h2><div class=\"grid\">{cards}</div></section>"


def _role_card(role: DashboardRole) -> str:
    action = role.night_action or "none"
    image = "image" if role.has_image else "no image"
    return f"""
<article class="card">
  <strong>{escape(role.name)}</strong>
  <div class="role {escape(role.team)}">{escape(role.code)} · {escape(role.team)}</div>
  <p>{escape(role.description)}</p>
  <div class="meta">
    <span class="pill">{escape(action)}</span>
    <span class="pill">{image}</span>
  </div>
</article>"""


def _api_hint(base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"""
<section>
  <h2>API</h2>
  <div class="card">
    <div><code>{escape(base)}/api/games/&lt;id&gt;</code></div>
    <div><code>{escape(base)}/api/chats/&lt;chat_id&gt;/active</code></div>
  </div>
</section>"""


def _empty(text: str) -> str:
    return f"<section><div class=\"card\">{escape(text)}</div></section>"
