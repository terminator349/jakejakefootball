"""Plain Python tools the agents can call.

Agno reads each function's name, type hints and docstring and shows them to
the model as a tool. The docstring is the model's only description of what a
tool does, so write it for the model.

In task 1.1 these moved into the League Office MCP server; the agent code barely
changes, because it still just sees tools. They read the league from SQLite
(agents/league_db.py).
"""

import json

from agents import rules
from agents.league_db import load_league


def _team_ids(league: dict) -> list[str]:
    return [t["id"] for t in league["teams"]]


def _unknown_team(league: dict, team_id: str) -> str:
    return json.dumps({"error": f"Unknown team_id {team_id!r}. Valid ids: {_team_ids(league)}"})


def list_teams() -> str:
    """List every team in the league with its id, city, nickname, total payroll and
    cap space (both in $M). Also says which team id is ours."""
    league = load_league()
    cap = league["rules"]["salary_cap"]
    teams = []
    for team in league["teams"]:
        payroll = sum(p["salary"] for p in league["players"] if p["team_id"] == team["id"])
        teams.append({**team, "payroll": round(payroll, 1), "cap_space": round(cap - payroll, 1)})
    return json.dumps({"our_team": league["our_team"], "teams": teams})


def get_roster(team_id: str, position: str = "") -> str:
    """Get the players on one team, best first within each position: age, salary ($M),
    contract years left, games missed last season, overall rating, and position-specific
    ratings from 25-99. Starters are marked.

    Args:
        team_id: three-letter team id, e.g. "HAR". Use list_teams to find ids.
        position: optional filter, one of QB, RB, WR, TE, OL, DL, LB, CB, S, K, P.
            Leave empty for the full 48-player roster.
    """
    league = load_league()
    team_id, position = team_id.upper(), position.upper()
    if team_id not in _team_ids(league):
        return _unknown_team(league, team_id)

    starters = league["rules"]["starters_per_position"]
    if position and position not in starters:
        return json.dumps({"error": f"Unknown position {position!r}. Valid positions: {list(starters)}"})

    roster = []
    for pos in ([position] if position else starters):
        group = sorted((p for p in league["players"] if p["team_id"] == team_id and p["position"] == pos),
                       key=lambda p: p["overall"], reverse=True)
        roster += [{**p, "starter": depth < starters[pos]} for depth, p in enumerate(group)]
    return json.dumps({"team_id": team_id, "players": roster})


def _starter_average(league: dict, team_id: str, position: str, rating: str) -> float:
    group = sorted((p for p in league["players"] if p["team_id"] == team_id and p["position"] == position),
                   key=lambda p: p["overall"], reverse=True)
    starters = group[:league["rules"]["starters_per_position"][position]]
    values = [p["overall"] if rating == "overall" else p["ratings"][rating] for p in starters]
    return sum(values) / len(values)


def compare_to_league(team_id: str) -> str:
    """Compare one team's starters with the rest of the league, position by position.

    For every position (QB, RB, WR, TE, OL, DL, LB, CB, S, K, P) and each of that
    position's ratings plus "overall", a row gives the team's starter average, the league
    average, the gap (negative = below the league) and the team's rank (1 = best). Rows
    are sorted worst gap first, so the top rows are the team's biggest weaknesses relative
    to the league. Use this before get_roster when looking for strengths or weaknesses.

    Args:
        team_id: three-letter team id, e.g. "HAR". Use list_teams to find ids.
    """
    league = load_league()
    team_id = team_id.upper()
    team_ids = _team_ids(league)
    if team_id not in team_ids:
        return _unknown_team(league, team_id)

    rows = []
    for position in league["rules"]["starters_per_position"]:
        sample = next(p for p in league["players"] if p["position"] == position)
        for rating in ["overall", *sample["ratings"]]:
            averages = {tid: _starter_average(league, tid, position, rating) for tid in team_ids}
            ours = averages[team_id]
            league_avg = sum(averages.values()) / len(averages)
            rank = 1 + sum(1 for value in averages.values() if value > ours)
            rows.append({
                "position": position,
                "rating": rating,
                "team_avg": round(ours, 1),
                "league_avg": round(league_avg, 1),
                "gap": round(ours - league_avg, 1),
                "rank": rank,
            })

    rows.sort(key=lambda row: row["gap"])
    return json.dumps({"team_id": team_id, "teams_in_league": len(team_ids), "comparisons": rows})


def get_league_rules() -> str:
    """Get the league's rules: hard salary cap ($M), minimum/maximum roster size, games
    per season, trade deadline week, and how many players start at each position."""
    return json.dumps(load_league()["rules"])


def check_trade(team_a: str, a_sends: list[str], team_b: str, b_sends: list[str]) -> str:
    """Check whether a trade between two teams is legal under the league rules this week,
    without making it. Returns "legal" (true/false), the current week, every rule the
    trade would break with a plain-English reason (roster below the minimum or above the
    maximum size, payroll over the hard cap, trade after the deadline week, or players
    who are not on the team that sends them), and each team's roster size, payroll and
    cap space ($M) after the trade.

    Args:
        team_a: three-letter id of the first team, e.g. "HAR".
        a_sends: player ids team_a gives up, e.g. ["HAR-31"]. May be empty.
        team_b: three-letter id of the other team, e.g. "MES".
        b_sends: player ids team_b gives up. May be empty, but not both sides.
    """
    return json.dumps(rules.check_trade(rules.Trade(team_a, a_sends, team_b, b_sends)))
