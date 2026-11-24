"""The Coaching director: sets the depth chart and plans around the next opponent.

It reads the league through the same League Office MCP server as the other
directors, but with its own tool slice: the depth chart tools (task 3.2's
get_depth_chart/set_depth_chart) and get_team_tendencies are for this agent alone.
It is a member of the GM's Team (agents/gm.py), alongside Medical
(agents/medical.py). Its `role` is what the GM reads when deciding whether to
delegate to it.
"""

import json
import sys
from pathlib import Path

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from agents.analytics import TOOL_CALL_LIMIT, specialist_model
from agents.tools import list_teams

PROJECT_ROOT = Path(__file__).parent.parent

# This agent's own slice of the League Office's tools: the depth chart, injuries
# (to know who's actually available) and tendencies, plus enough roster data to
# name names.
COACHING_TOOLS = ["list_teams", "get_roster", "get_league_rules", "get_depth_chart",
                  "set_depth_chart", "get_team_tendencies", "get_injury_report"]


def league_office_tools(db_file: Path | None = None) -> MCPTools:
    """The League Office server's tools this agent needs. Connect with `async with`
    before running the agent. Pass a save file to serve that game instead of the
    default league."""
    args = ["-m", "servers.league_office"] + (["--db", str(Path(db_file).resolve())] if db_file else [])
    server = StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT_ROOT))
    return MCPTools(server_params=server, transport="stdio", include_tools=COACHING_TOOLS)


PARSER_PROMPT = (
    "The user message is a coaching report written by the head coach of an American football "
    "front office, answering a question about the depth chart or the game plan. Fill the output "
    "fields from that report only: copy its facts and numbers, invent nothing, and do not reply "
    "to these instructions. `answer` is the report's own direct answer to the question, in two "
    "or three sentences."
)


class CoachingReport(BaseModel):
    """Structured output, so later code (and the GM) can rely on its shape."""

    team_id: str = Field(description="Three-letter id of the team the report is about, e.g. 'HAR'.")
    answer: str = Field(description="Direct answer to the question, two or three sentences.")
    depth_chart_changes: list[str] = Field(description="Any depth chart changes made or recommended, "
                                           "e.g. 'S: Marcus Vance now starts over Jordan Pratt (out 3 more "
                                           "games).' Empty if none.")
    game_plan: str = Field(description="The suggested approach for the next game: a tendency or matchup "
                           "to lean on or guard against, from get_team_tendencies.")
    evidence: list[str] = Field(description="Specific numbers from the league that support the answer, "
                                "e.g. tendency percentages, ratings or games remaining for an injury.")


def ground_report(report: CoachingReport) -> CoachingReport:
    """Replace the team id the database knows with its own value.

    The parser model sometimes writes the team's name instead of its id.
    """
    guess = report.team_id.strip().lower()
    for team in json.loads(list_teams())["teams"]:
        if guess in {team["id"].lower(), team["city"].lower(), team["name"].lower(),
                     f"{team['city']} {team['name']}".lower()}:
            return report.model_copy(update={"team_id": team["id"]})
    return report


def build_coaching_agent(league_office: MCPTools, debug: bool = False) -> Agent:
    return Agent(
        name="Coaching",
        role="Sets the depth chart around injuries and plans the game around the next "
             "opponent's tendencies.",
        model=specialist_model(),
        tools=[league_office],
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the head coach of an American football front office.",
            "Always look at the real data with your tools before answering; never invent players, "
            "injuries or tendencies.",
            "Before touching the depth chart, call get_injury_report and get_depth_chart for our team "
            "so you know who is actually available; never recommend starting a player who is still out hurt.",
            "set_depth_chart is the only way to change who starts: call it with every player currently "
            "on the roster at that position, best first, rather than just describing the change. It is "
            "rejected if you leave anyone out or add someone who isn't there.",
            "To plan around an opponent, call get_team_tendencies for them: lean the game plan on what "
            "their numbers actually show, especially their mix on 3rd/4th down with 7 or more yards to go.",
            "Cite exact percentages, ratings and games-remaining figures, as the tools give them, as "
            "your evidence.",
            "Tool results do not change during a run: call each tool at most once per team or "
            "position, then write your answer.",
        ],
        output_schema=CoachingReport,
        # Same loop/parsing issue as Analytics: a parser model avoids DeepSeek looping on
        # tool calls when the JSON schema is attached to a tool-calling request.
        parser_model=specialist_model(),
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )
