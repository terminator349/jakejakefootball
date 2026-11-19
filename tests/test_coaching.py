"""Checks for the Coaching agent. These need no API key: run `pytest`."""

import asyncio

from agno.tools.mcp import MCPTools

from agents.analytics import TOOL_CALL_LIMIT
from agents.coaching import CoachingReport, build_coaching_agent, ground_report, league_office_tools


def test_agent_builds_with_its_tools():
    agent = build_coaching_agent(league_office_tools())
    assert agent.name == "Coaching"
    assert agent.model.id == "deepseek/deepseek-v4.1-flash-1017"
    assert len(agent.tools) == 1 and isinstance(agent.tools[0], MCPTools)


def test_agent_sees_the_league_office_tools():
    """Starts the League Office server the way check_coaching.py does and lists what the agent gets."""
    async def go():
        async with league_office_tools() as league_office:
            return set(league_office.functions)
    assert asyncio.run(go()) == {"list_teams", "get_roster", "get_league_rules", "get_depth_chart",
                                 "set_depth_chart", "get_team_tendencies", "get_injury_report"}


def test_agent_has_loop_guards():
    agent = build_coaching_agent(league_office_tools())
    assert agent.tool_call_limit is not None and agent.tool_call_limit <= TOOL_CALL_LIMIT
    assert agent.parser_model is not None


def test_parser_has_its_own_prompt():
    agent = build_coaching_agent(league_office_tools())
    assert "coaching report" in agent.parser_model_prompt


def test_ground_report_takes_the_team_id_from_the_league():
    report = CoachingReport(team_id="Harbor City Herons", answer="a", depth_chart_changes=[], game_plan="g",
                            evidence=["e"])
    assert ground_report(report).team_id == "HAR"
    assert ground_report(report).answer == "a"
    assert ground_report(report.model_copy(update={"team_id": "nobody"})).team_id == "nobody"
