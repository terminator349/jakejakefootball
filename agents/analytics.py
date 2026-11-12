"""The Analytics director: finds roster weaknesses and values players.

It reads the league through the League Office MCP server, which Agno starts
as a subprocess. In task 1.4 this same agent becomes a member of the GM's Team.
Its `role` is what the GM will read when deciding whether to delegate to it.
"""

import json
import sys
from pathlib import Path

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from agents.tools import list_teams

PROJECT_ROOT = Path(__file__).parent.parent

# DeepSeek V4.1 Flash through OpenRouter ($0.15 / $0.60 per million tokens).
# OpenRouter reads OPENROUTER_API_KEY from the environment.
SPECIALIST_MODEL = "deepseek/deepseek-v4.1-flash-1017"

# Hard stop for runaway loops. A good answer needs about 3-5 tool calls.
TOOL_CALL_LIMIT = 10

PARSER_PROMPT = (
    "The user message is a roster report written by the analytics director of an American football "
    "front office, answering a question from the team's owner. Fill the output fields from that report "
    "only: copy its facts and numbers, invent nothing, and do not reply to these instructions. "
    "`answer` is the report's own direct answer to the owner's question, in two or three sentences."
)


def specialist_model() -> OpenRouter:
    # Agno's OpenRouter default of 1024 output tokens is too tight for a full report.
    return OpenRouter(id=SPECIALIST_MODEL, max_tokens=8192)


def league_office_tools() -> MCPTools:
    """The League Office server's tools. Connect with `async with` before running the agent."""
    server = StdioServerParameters(command=sys.executable, args=["-m", "servers.league_office"],
                                   cwd=str(PROJECT_ROOT))
    return MCPTools(server_params=server, transport="stdio")


class RosterReport(BaseModel):
    """Structured output, so later code (and the GM) can rely on its shape."""

    team_id: str = Field(description="Three-letter id of the team the report is about, e.g. 'HAR'.")
    answer: str = Field(description="Direct answer to the owner's question, two or three sentences.")
    weakest_area: str = Field(description="The single biggest weakness, e.g. 'pass coverage at safety'.")
    evidence: list[str] = Field(description="Specific numbers from the roster that support the answer.")
    target_profile: str = Field(description="The kind of player we should acquire to fix the weakness.")
    payroll: float = Field(description="Our total payroll in $M.")
    cap_space: float = Field(description="Salary cap minus payroll, in $M. Negative means over the cap.")


def ground_report(report: RosterReport) -> RosterReport:
    """Replace the facts the database knows with the database's values.

    The parser model sometimes writes the team's name instead of its id, or the payroll in
    dollars instead of $M. Payroll and cap space come from the league, not the model.
    """
    guess = report.team_id.strip().lower()
    for team in json.loads(list_teams())["teams"]:
        if guess in {team["id"].lower(), team["city"].lower(), team["name"].lower(),
                     f"{team['city']} {team['name']}".lower()}:
            return report.model_copy(update={"team_id": team["id"], "payroll": team["payroll"],
                                             "cap_space": team["cap_space"]})
    return report


def build_analytics_agent(league_office: MCPTools, debug: bool = False) -> Agent:
    return Agent(
        name="Analytics",
        role="Finds roster weaknesses, compares players and values them using ratings and contracts.",
        model=specialist_model(),
        tools=[league_office],
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the analytics director of an American football front office.",
            "Always look at the real data with your tools before answering; never invent players or numbers.",
            "To find strengths or weaknesses, call compare_to_league first. A weakness is weak relative "
            "to other teams, not just low; do not fetch every team's roster to work this out yourself.",
            "Then call get_roster for our team with a position filter for the weak positions, "
            "to name the specific players behind the numbers.",
            "Cite exact player names and ratings, plus the team's rank and gap from compare_to_league, in your evidence.",
            "The salary cap is hard: going over it is illegal, not just taxed. Any player we add must fit in "
            "our cap space, or we must send salary back, so treat a team at or near the cap as a real "
            "roster-building constraint, not a minor detail.",
            "End your answer with our exact payroll and cap space in $M, as list_teams gives them.",
            "Tool results do not change during a run: call each tool at most once per team and position, "
            "then write your answer.",
        ],
        output_schema=RosterReport,
        # DeepSeek looped on tool calls when the JSON schema was sent with every request.
        # With a parser model, the agent answers in plain text and a second call turns
        # that text into a RosterReport.
        parser_model=specialist_model(),
        # Agno's default parser prompt ("create a structured output from the provided user
        # message") led the parser to fill `answer` with a reply to that request instead of
        # the report's answer, so say what the message is and that it is only to be copied.
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )
