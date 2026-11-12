"""A local test bench for the front office: one web page over the real code.

    python -m ui.server          # then open http://127.0.0.1:8765

Everything the page shows comes from the same functions the game and the agents
use: the league tools, the rule checks, saves and the season, the League Office
MCP server (started over stdio, as the agents start it) and the Analytics agent.
It only listens on this computer.

"Sim this week" plays the week's games with the season simulator (3.1).
"""

import json
import os
import sys
import time
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from agents import league_db, rules, saves, season, tools

PROJECT_ROOT = Path(__file__).parent.parent
PAGE = Path(__file__).parent / "index.html"
HOST, PORT = "127.0.0.1", 8765

# Errors a person can cause from the page; they come back as a message, not a crash.
USER_ERRORS = (ValueError, FileExistsError, FileNotFoundError, rules.IllegalMove, league_db.OutdatedDatabase)


def api(handler):
    async def endpoint(request: Request):
        try:
            body = await request.json() if request.method == "POST" else {}
            return JSONResponse(await handler(request, body))
        except rules.IllegalMove as refused:
            return JSONResponse({"error": str(refused),
                                 "violations": [v.__dict__ for v in refused.violations]}, status_code=400)
        except USER_ERRORS as error:
            return JSONResponse({"error": str(error)}, status_code=400)
    return endpoint


def active_save() -> str | None:
    """The loaded save's name, or None for the default league."""
    db_file = league_db.DB_FILE.resolve()
    return db_file.stem if db_file.parent == saves.SAVES_DIR.resolve() else None


def _db_for_agents() -> Path | None:
    return None if active_save() is None else league_db.DB_FILE


# ---- League and game -------------------------------------------------------

async def status(request, body):
    league_rules = json.loads(tools.get_league_rules())
    week = season.current_week()
    db_file = league_db.DB_FILE.resolve()
    if db_file.is_relative_to(PROJECT_ROOT.resolve()):
        db_file = db_file.relative_to(PROJECT_ROOT.resolve())
    return {"save": active_save(), "db_file": db_file.as_posix(),
            "week": week, "season_games": league_rules["season_games"],
            "season_over": week > league_rules["season_games"],
            "trade_deadline_week": league_rules["trade_deadline_week"],
            "our_team": json.loads(tools.list_teams())["our_team"],
            "api_key_set": bool(os.getenv("OPENROUTER_API_KEY"))}


async def list_saves(request, body):
    return {"saves": saves.list_saves(), "active": active_save()}


async def new_game(request, body):
    seed = body.get("seed")
    path = saves.new_game(body.get("name", ""), season_seed=int(seed) if seed not in (None, "") else None,
                          overwrite=bool(body.get("overwrite")))
    saves.load_game(path.stem)
    return {"loaded": path.stem}


async def load_game(request, body):
    return {"loaded": saves.load_game(body.get("name", "")).stem}


async def use_default(request, body):
    league_db.DB_FILE = league_db.DEFAULT_DB_FILE
    return {"loaded": None}


async def rebuild_default(request, body):
    if active_save() is not None:
        raise ValueError("Switch to the default league before rebuilding it.")
    league_db.build(league_db.DEFAULT_DB_FILE)
    return {"rebuilt": True}


async def teams(request, body):
    return json.loads(tools.list_teams())


async def roster(request, body):
    return json.loads(tools.get_roster(request.query_params.get("team", ""),
                                       request.query_params.get("position", "")))


async def compare(request, body):
    return json.loads(tools.compare_to_league(request.query_params.get("team", "")))


async def league_rules(request, body):
    return json.loads(tools.get_league_rules())


async def season_view(request, body):
    week = season.current_week()
    return {"week": week, "season_over": season.season_over(), "games": season.games(week),
            "standings": season.standings()}


async def schedule(request, body):
    return {"games": season.games()}


async def record_result(request, body):
    season.record_result(int(body["game_id"]), int(body["home_score"]), int(body["away_score"]))
    return {"ok": True}


async def sim_week(request, body):
    """Play this week's unplayed games snap by snap (task 3.1)."""
    return {"played": season.play_week()}


async def box_score(request, body):
    return season.box_score(int(request.query_params.get("id", "0")))


async def advance(request, body):
    return {"week": season.advance_week()}


def _trade(body) -> rules.Trade:
    return rules.Trade(body.get("team_a", ""), list(body.get("a_sends", [])),
                       body.get("team_b", ""), list(body.get("b_sends", [])))


async def check_trade(request, body):
    return rules.check_trade(_trade(body))


async def make_trade(request, body):
    return rules.make_trade(_trade(body))


async def moves(request, body):
    return {"moves": rules.move_log()}


# ---- The League Office over MCP --------------------------------------------

def _league_office() -> StdioServerParameters:
    """The server as the agents start it: a stdio subprocess, pointed at the loaded save."""
    args = ["-m", "servers.league_office"]
    if active_save() is not None:
        args += ["--db", str(league_db.DB_FILE.resolve())]
    return StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT_ROOT))


async def mcp_tools(request, body):
    started = time.perf_counter()
    async with Client(_league_office()) as client:
        listed = (await client.list_tools()).tools
    return {"elapsed_ms": round((time.perf_counter() - started) * 1000),
            "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema,
                       "read_only": bool(t.annotations and t.annotations.read_only_hint)} for t in listed]}


async def mcp_call(request, body):
    started = time.perf_counter()
    async with Client(_league_office()) as client:
        result = await client.call_tool(body.get("tool", ""), body.get("arguments") or {})
    text = "\n".join(getattr(part, "text", "") for part in result.content)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {"elapsed_ms": round((time.perf_counter() - started) * 1000), "is_error": bool(result.is_error),
            "text": text, "json": parsed}


# ---- The Analytics agent ---------------------------------------------------

async def run_analytics(request, body):
    from agents.analytics import RosterReport, build_analytics_agent, ground_report, league_office_tools

    question = (body.get("question") or "").strip()
    if not question:
        raise ValueError("Type a question for the agent.")
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is not set. Add it to .env and restart the UI.")

    started = time.perf_counter()
    async with league_office_tools(_db_for_agents()) as league_office:
        response = await build_analytics_agent(league_office).arun(question)
    elapsed = time.perf_counter() - started

    calls = []
    for call in response.tools or []:
        result = call.result if isinstance(call.result, str) else json.dumps(call.result, default=str)
        calls.append({"tool": call.tool_name, "args": call.tool_args, "error": bool(call.tool_call_error),
                      "result": result})
    metrics = response.metrics
    content = response.content
    report = ground_report(content).model_dump() if isinstance(content, RosterReport) else None
    return {"report": report, "text": None if report else str(content), "tool_calls": calls,
            "seconds": round(elapsed, 1), "model": response.model,
            "input_tokens": getattr(metrics, "input_tokens", None),
            "output_tokens": getattr(metrics, "output_tokens", None),
            "cost": getattr(metrics, "cost", None)}


async def page(request):
    return FileResponse(PAGE)


app = Starlette(routes=[
    Route("/", page),
    Route("/api/status", api(status)),
    Route("/api/saves", api(list_saves)),
    Route("/api/saves/new", api(new_game), methods=["POST"]),
    Route("/api/saves/load", api(load_game), methods=["POST"]),
    Route("/api/league/default", api(use_default), methods=["POST"]),
    Route("/api/league/rebuild", api(rebuild_default), methods=["POST"]),
    Route("/api/teams", api(teams)),
    Route("/api/roster", api(roster)),
    Route("/api/compare", api(compare)),
    Route("/api/rules", api(league_rules)),
    Route("/api/season", api(season_view)),
    Route("/api/schedule", api(schedule)),
    Route("/api/season/result", api(record_result), methods=["POST"]),
    Route("/api/season/sim", api(sim_week), methods=["POST"]),
    Route("/api/game", api(box_score)),
    Route("/api/season/advance", api(advance), methods=["POST"]),
    Route("/api/trade/check", api(check_trade), methods=["POST"]),
    Route("/api/trade/make", api(make_trade), methods=["POST"]),
    Route("/api/moves", api(moves)),
    Route("/api/mcp/tools", api(mcp_tools)),
    Route("/api/mcp/call", api(mcp_call), methods=["POST"]),
    Route("/api/agent/analytics", api(run_analytics), methods=["POST"]),
])


if __name__ == "__main__":
    load_dotenv()
    print(f"Front Office test bench: http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
