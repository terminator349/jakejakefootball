"""The CPU GM: an LLM agent that makes one draft pick at a time.

Called once per CPU pick (no tools - the shortlist and team context are
already in the prompt), so a full draft is one completion call per CPU pick,
not a tool-calling loop. Same model and parser_model pattern as
agents/analytics.py, for the same reason: DeepSeek loops when a JSON schema
is attached to a request that also has tools; a parser_model call avoids
that even here, where there are no tools, so the structured output stays
reliable call after call.
"""

import json

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from pydantic import BaseModel, Field

DRAFT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
TOOL_CALL_LIMIT = 1


def draft_model() -> OpenRouter:
    return OpenRouter(id=DRAFT_MODEL, max_tokens=512)


class PickDecision(BaseModel):
    player_id: str = Field(description="The id of the chosen player, copied exactly from the shortlist.")
    reason: str = Field(description="One short sentence on why this player, for the draft log.")


def build_draft_agent(debug: bool = False) -> Agent:
    return Agent(
        name="Draft GM",
        role="Makes a single NFL draft pick for one team, given its roster needs, cap room and a shortlist.",
        model=draft_model(),
        instructions=[
            "You are the general manager making one pick in a 53-round amateur draft for your team.",
            "Choose exactly one player from the shortlist you're given - never invent a player or id "
            "that isn't in it.",
            "Weigh the player's value against your team's open roster needs and your front office's "
            "stated philosophy. A slightly lower-value player who fills an urgent need can beat a "
            "slightly higher-value player at a position you've already filled.",
            "Respect your remaining cap room: never pick a player whose cost would push you over it.",
        ],
        output_schema=PickDecision,
        parser_model=draft_model(),
        tool_call_limit=TOOL_CALL_LIMIT,
        debug_mode=debug,
    )


def build_pick_prompt(team_display_name: str, philosophy: str, pick_number: int, round_number: int,
                       cap_room: float, needs: dict[str, int], shortlist: list[dict]) -> str:
    return (
        f"You are the GM of the {team_display_name}. Front office philosophy: {philosophy}\n"
        f"This is pick #{pick_number} overall (round {round_number}).\n"
        f"Cap room remaining: ${cap_room:.1f}M.\n"
        f"Open roster needs (position: slots still needed): {json.dumps(needs)}\n\n"
        "Shortlist of available players (id, name, position, overall rating 25-99, "
        "estimated market value $M/yr, rookie salary $M/yr this pick would cost):\n"
        f"{json.dumps(shortlist, indent=2)}\n\n"
        "Pick exactly one player_id from this shortlist."
    )


def choose_pick(agent: Agent, team_display_name: str, philosophy: str, pick_number: int, round_number: int,
                 cap_room: float, needs: dict[str, int], shortlist: list[dict]) -> str | None:
    """Return the chosen player_id, or None if the agent failed or picked
    something invalid (caller falls back to the top of the shortlist)."""
    prompt = build_pick_prompt(team_display_name, philosophy, pick_number, round_number,
                                cap_room, needs, shortlist)
    valid_ids = {player["id"] for player in shortlist}
    try:
        response = agent.run(prompt)
        decision = response.content
        if isinstance(decision, PickDecision) and decision.player_id in valid_ids:
            return decision.player_id
    except Exception:
        pass
    return None
