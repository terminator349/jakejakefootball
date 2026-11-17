"""Plain Python tools the agents can call.

Agno reads each function's name, type hints and docstring and shows them to
the model as a tool. The docstring is the model's only description of what a
tool does, so write it for the model.

In task 1.1 these moved into the League Office MCP server; the agent code barely
changes, because it still just sees tools. They read the league from SQLite
(agents/league_db.py).
"""

import json

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


def _team_payroll(league: dict, team_id: str) -> float:
    return sum(p["salary"] for p in league["players"] if p["team_id"] == team_id)


def cap_math(payroll: float, new_salary: float, cap: float) -> dict:
    """The salary-cap arithmetic behind every cap-fit check in this project.

    Shared by check_cap_fit (the main SQLite league) and draft/tools.py (the
    standalone draft's in-memory teams), so a pick or a signing is judged by
    exactly the same rule and reported in the same shape everywhere.
    """
    cap_space = cap - payroll
    return {
        "salary_cap": cap, "payroll": round(payroll, 2), "cap_space_before": round(cap_space, 2),
        "new_salary": round(new_salary, 2), "fits_under_cap": new_salary <= cap_space,
        "cap_space_after": round(cap_space - new_salary, 2),
        "salary_to_clear": round(max(0.0, new_salary - cap_space), 2),
    }


def validate_cap_compliance() -> str:
    """Check every team's payroll against the league's hard salary cap and report which
    teams, if any, are over it. Use this to confirm the whole league is legal, or when
    no specific team or move is named."""
    league = load_league()
    cap = league["rules"]["salary_cap"]
    teams = []
    for team in league["teams"]:
        payroll = _team_payroll(league, team["id"])
        teams.append({"team_id": team["id"], "payroll": round(payroll, 2),
                      "cap_space": round(cap - payroll, 2), "over_cap": payroll > cap})
    over = [t for t in teams if t["over_cap"]]
    return json.dumps({"salary_cap": cap, "all_teams_compliant": not over,
                       "teams_over_cap": over, "teams": teams})


def check_cap_fit(team_id: str, new_salary: float) -> str:
    """Check whether signing or acquiring a player at a given salary ($M per season) fits
    under one team's hard salary cap, and if not, exactly how much salary the team must
    send away or cut first to make the move legal.

    Args:
        team_id: three-letter team id, e.g. "HAR". Use list_teams to find ids.
        new_salary: the new contract's salary in $M per season.
    """
    league = load_league()
    team_id = team_id.upper()
    if team_id not in _team_ids(league):
        return _unknown_team(league, team_id)

    cap = league["rules"]["salary_cap"]
    payroll = _team_payroll(league, team_id)
    return json.dumps({"team_id": team_id, **cap_math(payroll, new_salary, cap)})
