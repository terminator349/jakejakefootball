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
    games missed last season, and ratings from 25-99 (passing, rushing, receiving,
    blocking, pass_rush, run_defense, coverage, kicking, athleticism).

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
    "all": ("QB", "RB", "WR", "TE", "OT", "OG", "C", "EDGE", "DT", "LB", "CB", "S", "K"),
    "offense": ("QB", "RB", "WR", "TE", "OT", "OG", "C"),
    "defense": ("EDGE", "DT", "LB", "CB", "S"),
    "secondary": ("CB", "S"),
}
# Note: K is deliberately left out of its own group here. With only one K per
# team, a group average over it is really just one player's rating - too
# noisy across 8 mostly-irrelevant categories to mean anything. K still
# counts toward the "all" average.


def _group_average(players: list[dict], team_id: str, positions: tuple, rating: str) -> float:
    values = [p["ratings"][rating] for p in players if p["team_id"] == team_id and p["position"] in positions]
    return sum(values) / len(values)


def compare_to_league(team_id: str) -> str:
    """Compare one team's average ratings with the rest of the league, for each rating and
    position group (all players, offense = QB/RB/WR/TE/OT/OG/C, defense = EDGE/DT/LB/CB/S,
    secondary = CB/S). The kicker is excluded from these groups (one player per team is too
    noisy to compare meaningfully) but still counts in the "all" average.

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
    """Get the league's money and roster rules: the salary cap in $M (a hard cap - no team
    may legally exceed it, there is no luxury-tax overage like in basketball), and the
    minimum/maximum roster size."""
    return json.dumps(load_league()["rules"])
