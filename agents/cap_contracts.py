"""The Cap & Contracts director: checks whether a roster move is legal under the cap.

It reads the league through the same League Office MCP server as Analytics, which
Agno starts as a subprocess. In task 1.4 this agent becomes the second member of the
GM's Team. Its `role` is what the GM will read when deciding whether to delegate to it.
"""

import json

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from pydantic import BaseModel, Field

from agents.analytics import TOOL_CALL_LIMIT, specialist_model
from agents.tools import list_teams

PARSER_PROMPT = (
    "The user message is a cap report written by the salary cap and contracts director of an "
    "American football front office, answering a question about a roster move. Fill the output "
    "fields from that report only: copy its facts and numbers, invent nothing, and do not reply "
    "to these instructions. `answer` is the report's own direct answer to the question, in two "
    "or three sentences."
)


class CapReport(BaseModel):
    """Structured output, so later code (and the GM) can rely on its shape."""

    team_id: str = Field(description="Three-letter id of the team the report is about, e.g. 'HAR'.")
    answer: str = Field(description="Direct answer to the question, two or three sentences.")
    evidence: list[str] = Field(description="Specific numbers from the league that support the "
                                "answer, e.g. teams over the cap or the salary involved.")
    payroll: float = Field(description="The team's total payroll in $M, before the move.")
    cap_space: float = Field(description="Salary cap minus payroll, in $M, before the move. "
                             "Negative means over the cap.")
    fits_under_cap: bool = Field(description="Whether the move described fits under the hard cap.")
    salary_to_clear: float = Field(description="$M of salary the team must send away or cut to "
                                   "make the move legal. 0 if it already fits.")


def ground_report(report: CapReport) -> CapReport:
    """Replace the facts the database knows with the database's values.

    The parser model sometimes writes the team's name instead of its id, or the payroll
    in dollars instead of $M. Payroll and cap space come from the league, not the model.
    """
    guess = report.team_id.strip().lower()
    for team in json.loads(list_teams())["teams"]:
        if guess in {team["id"].lower(), team["city"].lower(), team["name"].lower(),
                     f"{team['city']} {team['name']}".lower()}:
            return report.model_copy(update={"team_id": team["id"], "payroll": team["payroll"],
                                             "cap_space": team["cap_space"]})
    return report


def build_cap_contracts_agent(league_office: MCPTools, debug: bool = False) -> Agent:
    return Agent(
        name="Cap & Contracts",
        role="Reads payroll and contracts and says whether a roster move fits under the hard "
             "salary cap, and what salary would have to go back to make it fit.",
        model=specialist_model(),
        tools=[league_office],
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the salary cap and contracts director of an American football front office.",
            "Always look at the real data with your tools before answering; never invent salaries, "
            "contract years or players.",
            "The salary cap is $255M per team and hard: going over it is illegal, not just taxed. "
            "Every team's payroll must stay at or under it.",
            "To test a specific move (signing, extending or acquiring a player at some salary), call "
            "check_cap_fit for that team. If it does not fit, report salary_to_clear exactly as the "
            "tool gives it: the salary the team must send away or cut first.",
            "If no specific team or move is named, or you're asked to confirm the whole league is "
            "legal, call validate_cap_compliance instead and report any teams it flags as over the cap.",
            "Cite the exact payroll, cap space and salary figures in $M, as the tools give them, as "
            "your evidence.",
            "Tool results do not change during a run: call each tool at most once per team or move, "
            "then write your answer.",
        ],
        output_schema=CapReport,
        # Same loop/parsing issue as Analytics: a parser model avoids DeepSeek looping on
        # tool calls when the JSON schema is attached to a tool-calling request.
        parser_model=specialist_model(),
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )
