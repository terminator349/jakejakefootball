"""The Analytics director: finds roster weaknesses and values players.

In Step 3 this same agent becomes a member of the GM's Team. Its `role` is
what the GM will read when deciding whether to delegate to it.
"""

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from pydantic import BaseModel, Field

from agents.tools import compare_to_league, get_league_rules, get_roster, list_teams

# DeepSeek V4.1 Flash through OpenRouter ($0.15 / $0.60 per million tokens).
# OpenRouter reads OPENROUTER_API_KEY from the environment.
SPECIALIST_MODEL = "deepseek/deepseek-v4.1-flash-1017"

# Hard stop for runaway loops. A good answer needs about 3 tool calls.
TOOL_CALL_LIMIT = 8


def specialist_model() -> OpenRouter:
    # Agno's OpenRouter default of 1024 output tokens is too tight for a full report.
    return OpenRouter(id=SPECIALIST_MODEL, max_tokens=8192)


class RosterReport(BaseModel):
    """Structured output, so later code (and the GM) can rely on its shape."""

    team_id: str
    answer: str = Field(description="Direct answer to the owner's question, two or three sentences.")
    weakest_area: str = Field(description="The single biggest weakness, e.g. 'secondary coverage'.")
    evidence: list[str] = Field(description="Specific numbers from the roster that support the answer.")
    target_profile: str = Field(description="The kind of player we should acquire to fix the weakness.")
    payroll: float = Field(description="Our total payroll in $M.")
    room_under_cap: float = Field(description="Salary cap minus payroll, in $M. Negative means illegally over the hard cap.")


def build_analytics_agent(debug: bool = False) -> Agent:
    return Agent(
        name="Analytics",
        role="Finds roster weaknesses, compares players and values them using ratings and contracts.",
        model=specialist_model(),
        tools=[list_teams, compare_to_league, get_roster, get_league_rules],
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the analytics director of a football front office.",
            "Always look at the real data with your tools before answering; never invent players or numbers.",
            "To find strengths or weaknesses, call compare_to_league first. A weakness is weak relative "
            "to other teams, not just low; do not fetch every team's roster to work this out yourself.",
            "Then call get_roster for our team to name the specific players behind the numbers.",
            "Cite exact player names and ratings, plus the team's rank and gap from compare_to_league, in your evidence.",
            "Remember our salary cap is a hard cap: going over it is illegal, not just taxed, so call out "
            "any team at or near the cap as a real roster-building constraint, not a minor detail.",
            "Tool results do not change during a run: call each tool at most once per team, then write your answer.",
        ],
        output_schema=RosterReport,
        # DeepSeek looped on tool calls when the JSON schema was sent with every request.
        # With a parser model, the agent answers in plain text and a second call turns
        # that text into a RosterReport.
        parser_model=specialist_model(),
        debug_mode=debug,
    )
