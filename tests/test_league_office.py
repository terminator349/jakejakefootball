"""Checks for the League Office MCP server. No API key needed.

Most tests connect to the server in-process; one launches it as a real stdio
subprocess, the way an agent will.
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agents import league_db, rules, saves
from agents.tools import (check_cap_fit, check_trade, compare_to_league, get_depth_chart,
                          get_injury_report, get_roster, get_team_tendencies, list_teams,
                          set_depth_chart, validate_cap_compliance)
from servers.league_office import league_office

PROJECT_ROOT = Path(__file__).parent.parent


def call(tool: str, arguments: dict | None = None, server=league_office) -> dict:
    async def go():
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments or {})
            assert not result.is_error, result.content
            return json.loads(result.content[0].text)
    return asyncio.run(go())


def list_tools(server=league_office):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools
    return asyncio.run(go())


def test_serves_the_league_tools():
    names = {t.name for t in list_tools()}
    assert names == {"list_teams", "get_roster", "compare_to_league", "get_league_rules", "check_trade",
                     "validate_cap_compliance", "check_cap_fit", "get_depth_chart", "set_depth_chart",
                     "get_injury_report", "get_team_tendencies"}


def test_tools_are_read_only():
    """set_depth_chart is the one exception: it's the only tool that changes the league."""
    for tool in list_tools():
        assert tool.annotations.read_only_hint is (tool.name != "set_depth_chart")
        assert tool.annotations.destructive_hint is not True


def test_docstrings_become_tool_descriptions():
    """The docstring is the model's only description of a tool."""
    roster = next(t for t in list_tools() if t.name == "get_roster")
    assert "best first" in roster.description
    assert roster.input_schema["required"] == ["team_id"]
    assert "position" in roster.input_schema["properties"]


def test_results_match_the_plain_python_tools():
    assert call("list_teams") == json.loads(list_teams())
    assert call("get_roster", {"team_id": "HAR", "position": "CB"}) == json.loads(get_roster("HAR", "CB"))
    assert call("compare_to_league", {"team_id": "HAR"}) == json.loads(compare_to_league("HAR"))
    assert call("validate_cap_compliance") == json.loads(validate_cap_compliance())
    assert call("check_cap_fit", {"team_id": "HAR", "new_salary": 5.0}) == json.loads(check_cap_fit("HAR", 5.0))
    trade = {"team_a": "HAR", "a_sends": ["HAR-01"], "team_b": "MES", "b_sends": ["MES-01"]}
    assert call("check_trade", trade) == json.loads(check_trade(**trade))
    assert call("get_depth_chart", {"team_id": "HAR"}) == json.loads(get_depth_chart("HAR"))
    assert call("get_injury_report") == json.loads(get_injury_report())
    assert call("get_team_tendencies", {"team_id": "HAR"}) == json.loads(get_team_tendencies("HAR"))


def test_check_trade_shows_the_rule_a_trade_breaks(scratch_db):
    """The week comes from the league database, not from the caller."""
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = 10")
    db.close()
    result = call("check_trade", {"team_a": "HAR", "a_sends": ["HAR-01"], "team_b": "MES", "b_sends": ["MES-01"]})
    assert (result["legal"], result["week"]) == (False, 10)
    assert "trade_deadline" in {v["rule"] for v in result["violations"]}
    assert "week" not in next(t for t in list_tools() if t.name == "check_trade").input_schema["properties"]


def test_bad_arguments_come_back_as_error_json():
    assert "error" in call("get_roster", {"team_id": "XYZ"})
    assert "error" in call("compare_to_league", {"team_id": "XYZ"})
    assert "error" in call("check_cap_fit", {"team_id": "XYZ", "new_salary": 5.0})
    assert "error" in call("get_depth_chart", {"team_id": "XYZ"})
    assert "error" in call("get_injury_report", {"team_id": "XYZ"})
    assert "error" in call("get_team_tendencies", {"team_id": "XYZ"})


def test_set_depth_chart_over_mcp_changes_who_starts(scratch_db):
    safeties = call("get_depth_chart", {"team_id": "HAR", "position": "S"})["depth_chart"]["S"]["players"]
    new_order = [p["id"] for p in reversed(safeties)]
    result = call("set_depth_chart", {"team_id": "HAR", "position": "S", "player_order": new_order})
    assert [p["id"] for p in result["depth_chart"]["S"]["players"]] == new_order
    assert call("get_depth_chart", {"team_id": "HAR", "position": "S"})["depth_chart"]["S"]["custom_order"] is True


def test_runs_over_stdio():
    server = StdioServerParameters(command=sys.executable, args=["-m", "servers.league_office"], cwd=PROJECT_ROOT)
    rules = call("get_league_rules", server=server)
    assert rules["cap_type"] == "hard"
    assert len(list_tools(server)) == 11


def test_serves_a_save_over_stdio(tmp_path, monkeypatch):
    """The game starts the server with --db pointing at the loaded save."""
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path)
    save = saves.new_game("served", season_seed=5)
    rules.make_trade(rules.Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"]), db_file=save)

    server = StdioServerParameters(command=sys.executable, args=["-m", "servers.league_office", "--db", str(save)],
                                   cwd=PROJECT_ROOT)
    safeties = call("get_roster", {"team_id": "HAR", "position": "S"}, server=server)["players"]
    assert "SUM-45" in {p["id"] for p in safeties}
