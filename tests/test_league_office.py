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

from agents.tools import check_trade, compare_to_league, get_roster, list_teams
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
    assert names == {"list_teams", "get_roster", "compare_to_league", "get_league_rules", "check_trade"}


def test_tools_are_read_only():
    for tool in list_tools():
        assert tool.annotations.read_only_hint is True
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
    trade = {"team_a": "HAR", "a_sends": ["HAR-01"], "team_b": "MES", "b_sends": ["MES-01"], "week": 3}
    assert call("check_trade", trade) == json.loads(check_trade(**trade))


def test_check_trade_shows_the_rule_a_trade_breaks():
    result = call("check_trade", {"team_a": "HAR", "a_sends": ["HAR-01"], "team_b": "MES",
                                  "b_sends": ["MES-01"], "week": 10})
    assert result["legal"] is False
    assert "trade_deadline" in {v["rule"] for v in result["violations"]}


def test_bad_arguments_come_back_as_error_json():
    assert "error" in call("get_roster", {"team_id": "XYZ"})
    assert "error" in call("compare_to_league", {"team_id": "XYZ"})


def test_runs_over_stdio():
    server = StdioServerParameters(command=sys.executable, args=["-m", "servers.league_office"], cwd=PROJECT_ROOT)
    rules = call("get_league_rules", server=server)
    assert rules["cap_type"] == "hard"
    assert len(list_tools(server)) == 5
