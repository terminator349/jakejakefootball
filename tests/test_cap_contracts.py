"""Checks for the Cap & Contracts agent. These need no API key: run `pytest`."""

import asyncio

from agno.tools.mcp import MCPTools

from agents.analytics import TOOL_CALL_LIMIT, league_office_tools
from agents.cap_contracts import CapReport, build_cap_contracts_agent, ground_report


def test_agent_builds_with_its_tools():
    agent = build_cap_contracts_agent(league_office_tools())
    assert agent.name == "Cap & Contracts"
    assert agent.model.id == "deepseek/deepseek-v4.1-flash-1017"
    assert len(agent.tools) == 1 and isinstance(agent.tools[0], MCPTools)


def test_agent_sees_the_league_office_tools():
    """Starts the League Office server the way check_cap.py does and lists what the agent gets."""
    async def go():
        async with league_office_tools() as league_office:
            return set(league_office.functions)
    assert asyncio.run(go()) == {"list_teams", "get_roster", "compare_to_league", "get_league_rules",
                                 "validate_cap_compliance", "check_cap_fit"}


def test_agent_has_loop_guards():
    agent = build_cap_contracts_agent(league_office_tools())
    assert agent.tool_call_limit is not None and agent.tool_call_limit <= TOOL_CALL_LIMIT
    assert agent.parser_model is not None


def test_parser_has_its_own_prompt():
    agent = build_cap_contracts_agent(league_office_tools())
    assert "cap report" in agent.parser_model_prompt


def test_ground_report_takes_facts_from_the_league():
    report = CapReport(team_id="Harbor City Herons", answer="a", evidence=["e"], payroll=249500000.0,
                       cap_space=-1.0, fits_under_cap=False, salary_to_clear=6.5)
    grounded = ground_report(report)
    assert (grounded.team_id, grounded.payroll, grounded.cap_space) == ("HAR", 249.5, 5.5)
    assert grounded.answer == "a"
    assert ground_report(report.model_copy(update={"team_id": "nobody"})).team_id == "nobody"
