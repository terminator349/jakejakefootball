"""The Medical director: reports injuries and how they've thinned the roster.

It reads the league through the same League Office MCP server as the other
directors, with a short tool list: just enough roster and injury data (task
3.2's get_injury_report) to answer a question about who is hurt and what it
costs the team. It is a member of the GM's Team (agents/gm.py), alongside
Coaching (agents/coaching.py). Its `role` is what the GM reads when deciding
whether to delegate to it.
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

MEDICAL_TOOLS = ["list_teams", "get_roster", "get_injury_report"]


def league_office_tools(db_file: Path | None = None) -> MCPTools:
    """The League Office server's tools this agent needs. Connect with `async with`
    before running the agent. Pass a save file to serve that game instead of the
    default league."""
    args = ["-m", "servers.league_office"] + (["--db", str(Path(db_file).resolve())] if db_file else [])
    server = StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT_ROOT))
    return MCPTools(server_params=server, transport="stdio", include_tools=MEDICAL_TOOLS)


PARSER_PROMPT = (
    "The user message is a medical report written by the head athletic trainer of an American "
    "football front office, answering a question about injuries. Fill the output fields from "
    "that report only: copy its facts and numbers, invent nothing, and do not reply to these "
    "instructions. `answer` is the report's own direct answer to the question, in two or three "
    "sentences."
)


class MedicalReport(BaseModel):
    """Structured output, so later code (and the GM) can rely on its shape."""

    team_id: str = Field(description="Three-letter id of the team the report is about, e.g. 'HAR'.")
    answer: str = Field(description="Direct answer to the question, two or three sentences.")
    injuries: list[str] = Field(description="Every player currently out hurt, e.g. 'Jordan Pratt (S): "
                                "out 3 more games.' Empty if nobody of interest is hurt.")
    thinnest_position: str = Field(description="The position group hit hardest by injury right now, "
                                   "e.g. 'safety, with its top two players both out'. Empty string if "
                                   "none stand out.")
    evidence: list[str] = Field(description="Specific numbers from the league that support the answer, "
                                "e.g. games remaining or the backups' ratings at a thinned position.")


def ground_report(report: MedicalReport) -> MedicalReport:
    """Replace the team id the database knows with its own value.

    The parser model sometimes writes the team's name instead of its id.
    """
    guess = report.team_id.strip().lower()
    for team in json.loads(list_teams())["teams"]:
        if guess in {team["id"].lower(), team["city"].lower(), team["name"].lower(),
                     f"{team['city']} {team['name']}".lower()}:
            return report.model_copy(update={"team_id": team["id"]})
    return report


def build_medical_agent(league_office: MCPTools, debug: bool = False) -> Agent:
    return Agent(
        name="Medical",
        role="Reports who is currently injured, for how much longer, and which "
             "position group it leaves thinnest.",
        model=specialist_model(),
        tools=[league_office],
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the head athletic trainer of an American football front office.",
            "Always look at the real data with your tools before answering; never invent an injury "
            "or a recovery time.",
            "Call get_injury_report for our team to see who is out and how many games they have left "
            "to miss.",
            "If an injury leaves a position thin, call get_roster for that position to name the "
            "backup stepping in and their rating, so the owner knows what to expect on the field.",
            "Cite the exact games-remaining figures the tools give, as your evidence.",
            "Tool results do not change during a run: call each tool at most once per team or "
            "position, then write your answer.",
        ],
        output_schema=MedicalReport,
        # Same loop/parsing issue as Analytics: a parser model avoids DeepSeek looping on
        # tool calls when the JSON schema is attached to a tool-calling request.
        parser_model=specialist_model(),
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )
