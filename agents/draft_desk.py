"""The Draft desk: the GM's specialist for Draft Day (task 1.4).

Draft Day (`draft_day.py`, `draft/`) is a separate 53-round snake draft of
real NFL players, run by the Draft GM agent (`draft/agent.py`) one pick at a
time. That agent only makes picks, so the GM gets this desk instead: it reads
the last draft's results (`data/draft_results.json`) and the draft class
through three plain Python tools, and answers questions about them. Draft Day's
rosters are its own, not the league's 48-player rosters.

When the rookie draft moves into the game (G7), these tools read the save's
prospect pool instead, and the GM's questions stay the same.
"""

import json
from pathlib import Path

from agno.agent import Agent
from pydantic import BaseModel, Field

from agents.analytics import TOOL_CALL_LIMIT, specialist_model
from draft.players import build_player_pool
from draft.roster_rules import PICKS_PER_ROUND, SALARY_CAP, ROSTER_TEMPLATE
from draft.valuation import market_value

RESULTS_FILE = Path(__file__).parent.parent / "data" / "draft_results.json"

PARSER_PROMPT = (
    "The user message is a report on a rookie draft written by the draft director of an American "
    "football front office. Fill the output fields from that report only: copy its facts and numbers, "
    "invent nothing, and do not reply to these instructions. `answer` is the report's own direct answer "
    "to the question, in two or three sentences."
)


class DraftReport(BaseModel):
    """Structured output, so the GM (and later code) can rely on its shape."""

    team_id: str = Field(description="Three-letter id of the team the report is mostly about, e.g. 'HAR'.")
    answer: str = Field(description="Direct answer to the question, two or three sentences.")
    evidence: list[str] = Field(description="Specific picks, ratings and salaries from the draft that "
                                "support the answer.")


def _load(results_file: Path) -> dict:
    if not Path(results_file).exists():
        raise FileNotFoundError("No draft has been run yet. Run `python draft_day.py --no-llm` first.")
    return json.loads(Path(results_file).read_text(encoding="utf-8"))


def _round_of(pick: int) -> int:
    return (pick - 1) // PICKS_PER_ROUND + 1


def build_draft_tools(results_file: Path = RESULTS_FILE) -> list:
    """The desk's tools, bound to one draft's results file. Each returns JSON, as the
    League Office's tools do, and an error instead of raising when there is no draft."""

    def draft_summary() -> str:
        """The last draft at a glance, with every team's class graded so teams can be
        compared in one call: the draft order, and for each team its front-office
        philosophy, average overall rating, players rated 90+, total market value against
        total rookie salary (the surplus is value gained), payroll, cap room under the
        hard cap, its three best picks, and its rank among the six by average overall."""
        try:
            results = _load(results_file)
        except FileNotFoundError as missing:
            return json.dumps({"error": str(missing)})
        teams = []
        for team in results["teams"]:
            players = team["players"]
            payroll = round(sum(p["salary"] or 0 for p in players), 1)
            value = round(sum(market_value(p["overall"], p["position"]) for p in players), 1)
            best = sorted(players, key=lambda p: (-p["overall"], p["pick_number"]))[:3]
            teams.append({"team_id": team["id"], "team": f"{team['city']} {team['name']}",
                          "philosophy": team["philosophy"], "players": len(players),
                          "average_overall": round(sum(p["overall"] for p in players) / max(1, len(players)), 1),
                          "rated_90_plus": sum(p["overall"] >= 90 for p in players),
                          "market_value": value, "value_surplus": round(value - payroll, 1),
                          "payroll": payroll, "cap_room": round(SALARY_CAP - payroll, 1),
                          "best_picks": [{"name": p["name"], "position": p["position"], "overall": p["overall"],
                                          "pick": p["pick_number"]} for p in best]})
        for rank, team in enumerate(sorted(teams, key=lambda t: -t["average_overall"]), 1):
            team["rank_by_average_overall"] = rank
        return json.dumps({"draft_order": results["draft_order"], "rounds": len(results["draft_log"]) // PICKS_PER_ROUND,
                           "salary_cap": SALARY_CAP, "teams": teams})

    def team_draft(team_id: str, position: str = "") -> str:
        """Every pick one team made, in order: pick number, round, player, position,
        overall rating (25-99), rookie salary and market value in $M per season.

        Args:
            team_id: three-letter team id, e.g. "HAR".
            position: optional position filter, e.g. "CB" or "QB". Empty for every pick.
        """
        try:
            results = _load(results_file)
        except FileNotFoundError as missing:
            return json.dumps({"error": str(missing)})
        team = next((t for t in results["teams"] if t["id"] == team_id.strip().upper()), None)
        if team is None:
            return json.dumps({"error": f"Unknown team_id {team_id!r}. Valid ids: {results['draft_order']}"})
        position = position.strip().upper()
        if position and position not in ROSTER_TEMPLATE:
            return json.dumps({"error": f"Unknown position {position!r}. Valid: {list(ROSTER_TEMPLATE)}"})
        picks = sorted((p for p in team["players"] if not position or p["position"] == position),
                       key=lambda p: p["pick_number"])
        return json.dumps({"team_id": team["id"], "position": position or None, "picks": [
            {"pick": p["pick_number"], "round": _round_of(p["pick_number"]), "name": p["name"],
             "position": p["position"], "overall": p["overall"], "salary": p["salary"],
             "market_value": market_value(p["overall"], p["position"])} for p in picks]})

    def best_undrafted(position: str = "", limit: int = 10) -> str:
        """The best players in the draft class nobody took, by overall rating, with the
        market value ($M per season) each would cost.

        Args:
            position: optional position filter, e.g. "S". Empty for every position.
            limit: how many players to list, at most 25.
        """
        try:
            results = _load(results_file)
        except FileNotFoundError as missing:
            return json.dumps({"error": str(missing)})
        drafted = {p["player_id"] for p in results["draft_log"]}
        position = position.strip().upper()
        left = [p for p in build_player_pool() if p.id not in drafted and (not position or p.position == position)]
        left.sort(key=lambda p: (-p.overall, p.id))
        return json.dumps({"position": position or None, "undrafted": len(left), "players": [
            {"name": p.name, "position": p.position, "overall": p.overall,
             "market_value": market_value(p.overall, p.position)} for p in left[:max(1, min(int(limit), 25))]]})

    return [draft_summary, team_draft, best_undrafted]


def build_draft_desk(results_file: Path = RESULTS_FILE, debug: bool = False) -> Agent:
    return Agent(
        name="Draft",
        role="Knows Draft Day, the separate 53-round draft of real NFL players: the draft order, what "
             "each team took and why it fits their philosophy, rookie salaries, and who went undrafted. "
             "Draft Day's rosters are not the league's rosters.",
        model=specialist_model(),
        tools=build_draft_tools(results_file),
        tool_call_limit=TOOL_CALL_LIMIT,
        instructions=[
            "You are the draft director of an American football front office, reporting on Draft Day: "
            "a 6-team, 53-round snake draft of real NFL players with rookie-scale salaries.",
            "Always look at the draft with your tools before answering; never invent picks, players, "
            "ratings or salaries.",
            "Start with draft_summary. It already grades every team's class (average overall, players "
            "rated 90+, value surplus, rank), so compare teams from it alone; never call team_draft for "
            "every team.",
            "Then, only if the question needs specific players, call team_draft for one team with a "
            "position filter, or best_undrafted. Answer only the question you were asked.",
            "Draft Day's rosters are separate from the league's 48-player rosters. If you're asked about "
            "the league's own players or cap, say that's for Analytics or Cap & Contracts.",
            "The salary cap is $255M and hard. Report payroll and cap room exactly as draft_summary gives them.",
            "Tool results do not change during a run: call each tool at most once per team and position, "
            "then write your answer.",
        ],
        output_schema=DraftReport,
        # The same parser-model pattern as Analytics and Cap & Contracts (see agents/analytics.py).
        parser_model=specialist_model(),
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )
