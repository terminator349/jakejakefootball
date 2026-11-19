"""The game and its test bench, served on this computer only.

    python -m ui.server          # then open http://127.0.0.1:8765

/ is the game (task G2): new game, load, one week at a time, roster, standings,
schedule and cap, play the week (sim or watch our game), save and quit.

/bench is the test bench: one page over the real code, for trying out
everything built so far: the league tools, the rule checks, saves and the
season, the League Office MCP server (started over stdio, as the agents start
it) and the agents: Analytics, Cap & Contracts, and the GM who leads them (1.4).

Both pages share ui/static/ and read and change the same loaded league.
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
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from agents import briefing, deadline, game_loop, league_db, live, orders, rivals, rules, saves, season, tools

PROJECT_ROOT = Path(__file__).parent.parent
UI_DIR = Path(__file__).parent
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

MCP_SERVERS = {"league_office": "servers.league_office", "trade_desk": "servers.trade_desk"}  # 1.1, 2.1


def _mcp_server(name: str | None) -> StdioServerParameters:
    """A server as the agents start it: a stdio subprocess, pointed at the loaded save."""
    name = name or "league_office"
    if name not in MCP_SERVERS:
        raise ValueError(f"Unknown MCP server {name!r}. Valid: {', '.join(MCP_SERVERS)}.")
    args = ["-m", MCP_SERVERS[name]]
    if active_save() is not None:
        args += ["--db", str(league_db.DB_FILE.resolve())]
    return StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT_ROOT))


async def mcp_tools(request, body):
    started = time.perf_counter()
    async with Client(_mcp_server(request.query_params.get("server"))) as client:
        listed = (await client.list_tools()).tools
    return {"elapsed_ms": round((time.perf_counter() - started) * 1000),
            "tools": [{"name": t.name, "description": t.description, "input_schema": t.input_schema,
                       "read_only": bool(t.annotations and t.annotations.read_only_hint),
                       "destructive": bool(t.annotations and t.annotations.destructive_hint)} for t in listed]}


async def mcp_call(request, body):
    started = time.perf_counter()
    async with Client(_mcp_server(body.get("server"))) as client:
        result = await client.call_tool(body.get("tool", ""), body.get("arguments") or {})
    text = "\n".join(getattr(part, "text", "") for part in result.content)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {"elapsed_ms": round((time.perf_counter() - started) * 1000), "is_error": bool(result.is_error),
            "text": text, "json": parsed}


# ---- The agents ---------------------------------------------------------------

def _question(body) -> str:
    question = (body.get("question") or "").strip()
    if not question:
        raise ValueError("Type a question for the agent.")
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("OPENROUTER_API_KEY is not set. Add it to .env and restart the UI.")
    return question


async def run_analytics(request, body):
    from agents.analytics import RosterReport, build_analytics_agent, ground_report, league_office_tools
    return await _run_specialist(_question(body), league_office_tools, build_analytics_agent,
                                 RosterReport, ground_report)


async def run_cap_contracts(request, body):
    from agents.cap_contracts import CapReport, build_cap_contracts_agent, ground_report, league_office_tools
    return await _run_specialist(_question(body), league_office_tools, build_cap_contracts_agent,
                                 CapReport, ground_report)


async def run_gm(request, body):
    """The GM's team (1.4): the GM delegates to Analytics, Cap & Contracts and Draft."""
    from agents import gm
    return await gm.ask(_question(body), _db_for_agents())


async def _run_specialist(question, league_office_tools, build, report_type, ground_report):
    started = time.perf_counter()
    async with league_office_tools(_db_for_agents()) as league_office:
        response = await build(league_office).arun(question)
    elapsed = time.perf_counter() - started

    from agents.gm import tool_calls
    calls = tool_calls(response)
    metrics = response.metrics
    content = response.content
    report = ground_report(content).model_dump() if isinstance(content, report_type) else None
    return {"report": report, "text": None if report else str(content), "tool_calls": calls,
            "seconds": round(elapsed, 1), "model": response.model,
            "input_tokens": getattr(metrics, "input_tokens", None),
            "output_tokens": getattr(metrics, "output_tokens", None),
            "cost": getattr(metrics, "cost", None)}


# ---- The game (G2) ------------------------------------------------------------

async def hub(request, body):
    """The week as the owner sees it. The game only plays saves, never the default league."""
    if active_save() is None:
        return {"save": None}
    week = game_loop.overview()
    return {"save": active_save(), **week, "api_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
            "briefing": None if week["season_over"] else briefing.stored(week["week"]),  # G3, once written
            "desk": orders.desk_view(),  # G4: standing orders and the GM's proposed moves
            "offers": rivals.offers_to_us(),  # G5: rival GMs' offers to us, with our GM's read
            "news": [] if week["season_over"] else rivals.news(week["week"]),  # G5: trades between rivals
            "deadline": None if week["season_over"] else deadline.status()}  # 2.3: the trade deadline


def _needs_a_save():
    if active_save() is None:
        raise ValueError("Start or load a game first.")


async def hub_play(request, body):
    _needs_a_save()
    return game_loop.play_week()


async def hub_advance(request, body):
    """On to the next week. Then the rival GMs move (G5): they trade with each other and
    may make us an offer."""
    _needs_a_save()
    week = season.advance_week()
    news = rivals.between_weeks(_db_for_agents())["news"]
    return {"week": week, "news": news + deadline.close(_db_for_agents())}  # 2.3: past the deadline, it closes


async def hub_briefing(request, body):
    """This week's GM briefing (G3): the one in the save, or the GM writes it now."""
    _needs_a_save()
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("The GM's briefing needs OPENROUTER_API_KEY in .env (then restart the server).")
    return await briefing.this_week()


async def hub_ask(request, body):
    """Ask the front office: the owner talks to the GM, who asks the specialists (1.4)."""
    _needs_a_save()
    return await run_gm(request, body)


async def hub_order(request, body):
    """Give the GM an order (G4): it reads the terms and proposes moves for the owner."""
    _needs_a_save()
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError("Orders need OPENROUTER_API_KEY in .env (then restart the server).")
    return await orders.give_order(body.get("order") or "", _db_for_agents())


async def hub_order_cancel(request, body):
    _needs_a_save()
    return orders.cancel_order(int(body.get("order_id") or 0))


async def hub_move_approve(request, body):
    """The owner approves a proposed move: it goes to the Trade Desk as our offer."""
    _needs_a_save()
    return orders.approve(int(body.get("move_id") or 0), body.get("note") or "")


async def hub_move_veto(request, body):
    _needs_a_save()
    return orders.veto(int(body.get("move_id") or 0), body.get("note") or "")


async def hub_deadline(request, body):
    """Work the trade deadline (2.3): the GM looks for trades that fix our biggest weakness
    and that the other team will take. Without an API key the rules' search does it."""
    _needs_a_save()
    return await deadline.work(_db_for_agents(), use_model=bool(os.getenv("OPENROUTER_API_KEY")))


async def hub_offer_answer(request, body):
    """The rival GM our offer was made to answers it (2.2): accept, counter or reject.
    Without an API key the rules answer for them."""
    _needs_a_save()
    return await rivals.answer_offer(int(body.get("proposal_id") or 0), _db_for_agents(),
                                     use_model=bool(os.getenv("OPENROUTER_API_KEY")))


async def hub_offer_accept(request, body):
    """The owner accepts an offer made to us (a rival's offer or counter)."""
    _needs_a_save()
    return rivals.accept_offer(int(body.get("proposal_id") or 0), body.get("note") or "", _db_for_agents())


async def hub_offer_reject(request, body):
    _needs_a_save()
    return rivals.reject_offer(int(body.get("proposal_id") or 0), body.get("note") or "", _db_for_agents())


async def hub_schedule(request, body):
    _needs_a_save()
    return {"games": game_loop.our_schedule()}


async def live_start(request, body):
    _needs_a_save()
    return live.start(body.get("level", "key"))


async def live_state(request, body):
    _needs_a_save()
    return live.state(int(request.query_params.get("id", "0")))


async def live_call(request, body):
    _needs_a_save()
    return live.call(int(body.get("game_id", 0)), body.get("call", ""), body.get("level"))


async def live_level(request, body):
    _needs_a_save()
    return live.set_level(int(body.get("game_id", 0)), body.get("level", ""))


async def live_sim(request, body):
    _needs_a_save()
    return live.sim_rest(int(body.get("game_id", 0)))


class FreshStaticFiles(StaticFiles):
    """ui/static/, checked with the server on every load, so an updated page never runs old code."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# The pages too: most of the game's code is in game.html, so a cached copy would run
# old code against a newer server.
FRESH = {"Cache-Control": "no-cache"}


async def game_page(request):
    return FileResponse(UI_DIR / "game.html", headers=FRESH)


async def bench_page(request):
    return FileResponse(UI_DIR / "bench.html", headers=FRESH)


app = Starlette(routes=[
    Route("/", game_page),
    Route("/bench", bench_page),
    Mount("/static", FreshStaticFiles(directory=UI_DIR / "static"), name="static"),
    Route("/api/hub", api(hub)),
    Route("/api/hub/play", api(hub_play), methods=["POST"]),
    Route("/api/hub/advance", api(hub_advance), methods=["POST"]),
    Route("/api/hub/schedule", api(hub_schedule)),
    Route("/api/hub/ask", api(hub_ask), methods=["POST"]),
    Route("/api/hub/briefing", api(hub_briefing), methods=["POST"]),
    Route("/api/hub/order", api(hub_order), methods=["POST"]),
    Route("/api/hub/order/cancel", api(hub_order_cancel), methods=["POST"]),
    Route("/api/hub/move/approve", api(hub_move_approve), methods=["POST"]),
    Route("/api/hub/move/veto", api(hub_move_veto), methods=["POST"]),
    Route("/api/hub/deadline", api(hub_deadline), methods=["POST"]),
    Route("/api/hub/offer/answer", api(hub_offer_answer), methods=["POST"]),
    Route("/api/hub/offer/accept", api(hub_offer_accept), methods=["POST"]),
    Route("/api/hub/offer/reject", api(hub_offer_reject), methods=["POST"]),
    Route("/api/live", api(live_state)),
    Route("/api/live/start", api(live_start), methods=["POST"]),
    Route("/api/live/call", api(live_call), methods=["POST"]),
    Route("/api/live/level", api(live_level), methods=["POST"]),
    Route("/api/live/sim", api(live_sim), methods=["POST"]),
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
    Route("/api/agent/cap", api(run_cap_contracts), methods=["POST"]),
    Route("/api/agent/gm", api(run_gm), methods=["POST"]),
])


if __name__ == "__main__":
    load_dotenv()
    print(f"Front Office: http://{HOST}:{PORT}   (test bench: http://{HOST}:{PORT}/bench)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
