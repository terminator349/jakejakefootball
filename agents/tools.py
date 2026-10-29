"""Plain Python tools the agents can call.

Agno reads each function's name, type hints and docstring and shows them to
the model as a tool. The docstring is the model's only description of what a
tool does, so write it for the model.

In Step 2 these move into the League Office MCP server; the agent code barely
changes, because it still just sees tools.
"""

import json
from pathlib import Path

LEAGUE_FILE = Path(__file__).parent.parent / "data" / "league.json"


def load_league() -> dict:
    if not LEAGUE_FILE.exists():
        raise FileNotFoundError(f"{LEAGUE_FILE} not found. Run: python data/generate_league.py")
    return json.loads(LEAGUE_FILE.read_text())


def list_teams() -> str:
    """List every team in the league with its id, city, nickname and total payroll (in $M).
    Also says which team id is ours."""
    league = load_league()
    teams = []
    for team in league["teams"]:
        payroll = sum(p["salary"] for p in league["players"] if p["team_id"] == team["id"])
        teams.append({**team, "payroll": round(payroll, 1)})
    return json.dumps({"our_team": league["our_team"], "teams": teams})


def get_roster(team_id: str) -> str:
    """Get every player on one team: position, age, salary ($M), contract years left,
    games missed last season, and ratings from 25-99 (offense, three_pt, rebounding,
    perimeter_defense, interior_defense, athleticism).

    Args:
        team_id: three-letter team id, e.g. "HAR". Use list_teams to find ids.
    """
    league = load_league()
    roster = [p for p in league["players"] if p["team_id"] == team_id.upper()]
    if not roster:
        valid = [t["id"] for t in league["teams"]]
        return json.dumps({"error": f"Unknown team_id {team_id!r}. Valid ids: {valid}"})
    return json.dumps({"team_id": team_id.upper(), "players": roster})


POSITION_GROUPS = {
    "all": ("PG", "SG", "SF", "PF", "C"),
    "perimeter": ("PG", "SG", "SF"),
    "frontcourt": ("PF", "C"),
}


def _group_average(players: list[dict], team_id: str, positions: tuple, rating: str) -> float:
    values = [p["ratings"][rating] for p in players if p["team_id"] == team_id and p["position"] in positions]
    return sum(values) / len(values)


def compare_to_league(team_id: str) -> str:
    """Compare one team's average ratings with the rest of the league, for each rating and
    position group (all players, perimeter = PG/SG/SF, frontcourt = PF/C).

    Each row gives the team's average, the league average, the gap (negative = below the
    league) and the team's rank (1 = best). Rows are sorted worst gap first, so the top
    rows are the team's biggest weaknesses relative to the league. Use this before
    get_roster when looking for strengths or weaknesses.

    Args:
        team_id: three-letter team id, e.g. "HAR". Use list_teams to find ids.
    """
    league = load_league()
    players = league["players"]
    team_id = team_id.upper()
    team_ids = [t["id"] for t in league["teams"]]
    if team_id not in team_ids:
        return json.dumps({"error": f"Unknown team_id {team_id!r}. Valid ids: {team_ids}"})

    rating_names = list(players[0]["ratings"])
    rows = []
    for group, positions in POSITION_GROUPS.items():
        for rating in rating_names:
            averages = {tid: _group_average(players, tid, positions, rating) for tid in team_ids}
            ours = averages[team_id]
            league_avg = sum(averages.values()) / len(averages)
            rank = 1 + sum(1 for value in averages.values() if value > ours)
            rows.append({
                "rating": rating,
                "group": group,
                "team_avg": round(ours, 1),
                "league_avg": round(league_avg, 1),
                "gap": round(ours - league_avg, 1),
                "rank": rank,
            })

    rows.sort(key=lambda row: row["gap"])
    return json.dumps({"team_id": team_id, "teams_in_league": len(team_ids), "comparisons": rows})


def get_league_rules() -> str:
    """Get the league's money and roster rules: salary cap, luxury tax line (both $M),
    and minimum/maximum roster size."""
    return json.dumps(load_league()["rules"])
