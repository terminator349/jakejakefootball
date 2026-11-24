"""The playoffs and the end of the season (task G6).

After week 17 the top four teams by the regular season's standings play for the
championship: the 1st seed against the 4th and the 2nd against the 3rd in the
semifinals (week 18), and the winners in the final (week 19), each game at the
better seed's ground. agents/season.py puts each round on the schedule when the
week moves on to it, and the simulator plays overtime until someone scores, so a
playoff game always has a winner. Playoff games are ordinary games: they're
simmed, watched or called like any other, with box scores and replays, but they
don't count in the standings.

This module reads it all back for the game: `bracket()` for the playoff screen,
and `summary()`, once the season is over, for the season summary the game ends
with: the record and standing, how far we went, the moves made (trades, moves
the owner approved or vetoed, rivals' offers), the final cap position and our
season leaders. Everything is plain Python; no model is involved.
"""

from pathlib import Path

from agents import deadline, season
from agents.game_loop import _ordinal, _record
from agents.league_db import connect, load_league

OUR_TEAM = "HAR"

# Season leaders for the summary: (stat, what it's called).
LEADERS = [("pass_yds", "passing yards"), ("rush_yds", "rushing yards"), ("rec_yds", "receiving yards"),
           ("def_sacks", "sacks"), ("def_int", "interceptions")]


def _teams(db_file: Path | None) -> dict[str, dict]:
    return {t["id"]: t for t in load_league(db_file)["teams"]}


def _periods(db_file: Path | None, game_ids: list[int]) -> dict[int, int]:
    """How many periods each game went to (5 = one overtime, 6 = two, ...)."""
    if not game_ids:
        return {}
    db = connect(db_file)
    try:
        return {row[0]: row[1] for row in db.execute(
            f"SELECT game_id, MAX(quarter) FROM plays WHERE game_id IN ({','.join('?' * len(game_ids))}) "
            "GROUP BY game_id", game_ids)}
    finally:
        db.close()


def bracket(db_file: Path | None = None) -> dict | None:
    """The seeds and every playoff round so far, with scores and winners. None during the
    regular season."""
    db = connect(db_file)
    try:
        week, season_games = season._current_week(db), season._season_games(db)
    finally:
        db.close()
    if week <= season_games:
        return None
    table = season.standings(db_file)
    seeded = [row["team_id"] for row in table[:season.PLAYOFF_TEAMS]]
    teams = _teams(db_file)

    def side(team_id):
        t = teams[team_id]
        return {"team_id": team_id, "city": t["city"], "name": t["name"], "seed": seeded.index(team_id) + 1}

    rounds = []
    for i, name in enumerate(season.PLAYOFF_ROUNDS):
        games = season.games(season_games + 1 + i, db_file)
        periods = _periods(db_file, [g["id"] for g in games])
        rounds.append({"name": name, "week": season_games + 1 + i, "games": [{
            "id": g["id"], "home": side(g["home_team_id"]), "away": side(g["away_team_id"]),
            "home_score": g["home_score"], "away_score": g["away_score"],
            "winner": season.winner(g, seeded), "overtimes": max(0, periods.get(g["id"], 4) - 4)} for g in games]})
    final = rounds[-1]["games"]
    champion = final[0]["winner"] if final and final[0]["winner"] else None
    out = {"round_now": season.playoff_round(week, season_games),
           "seeds": [{**side(row["team_id"]), "record": _record(row)} for row in table[:season.PLAYOFF_TEAMS]],
           "rounds": rounds, "champion": champion and side(champion), "we_made_it": OUR_TEAM in seeded}
    out["our_result"] = our_result(out)
    return out


def our_result(b: dict) -> str | None:
    """How far we went, once it's settled: 'missed the playoffs', 'lost in the semifinals
    to Summit', 'lost in the final to Summit' or 'won the championship'. None while we're
    still playing."""
    if not b["we_made_it"]:
        return "missed the playoffs"
    for rnd in b["rounds"]:
        for g in rnd["games"]:
            sides = {g["home"]["team_id"]: g["home"], g["away"]["team_id"]: g["away"]}
            if OUR_TEAM not in sides or g["winner"] is None:
                continue
            if g["winner"] != OUR_TEAM:
                return f"lost in the {rnd['name'].lower()} to {sides[g['winner']]['city']}"
    if b["champion"] and b["champion"]["team_id"] == OUR_TEAM:
        return "won the championship"
    return None


def _counts(db_file: Path | None) -> dict:
    db = connect(db_file)
    try:
        ours = dict(db.execute("SELECT status, COUNT(*) FROM gm_proposals GROUP BY status").fetchall())
        to_us = dict(db.execute("SELECT status, COUNT(*) FROM trade_proposals WHERE to_team_id = ? "
                                "GROUP BY status", (OUR_TEAM,)).fetchall())
        orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    finally:
        db.close()
    return {"orders_given": orders,
            "gm_moves": {"approved": ours.get("approved", 0), "vetoed": ours.get("vetoed", 0),
                         "void": ours.get("void", 0)},
            "offers_to_us": {"accepted": to_us.get("accepted", 0), "rejected": to_us.get("rejected", 0),
                             "expired": to_us.get("withdrawn", 0), "void": to_us.get("void", 0)}}


def leaders(db_file: Path | None = None) -> list[dict]:
    """Our season leaders, regular season and playoffs together."""
    db = connect(db_file)
    try:
        out = []
        for stat, label in LEADERS:
            row = db.execute(
                "SELECT s.player_id, p.name, p.position, SUM(s.value) AS total FROM player_game_stats s "
                "JOIN players p ON p.id = s.player_id WHERE s.team_id = ? AND s.stat = ? "
                "GROUP BY s.player_id ORDER BY total DESC, s.player_id LIMIT 1", (OUR_TEAM, stat)).fetchone()
            if row and row["total"]:
                out.append({"stat": label, "name": row["name"], "position": row["position"], "total": row["total"]})
        return out
    finally:
        db.close()


def summary(db_file: Path | None = None) -> dict:
    """The season summary the game ends with."""
    league = load_league(db_file)
    table = {row["team_id"]: row for row in season.standings(db_file)}
    ours, team = table[OUR_TEAM], _teams(db_file)[OUR_TEAM]
    b = bracket(db_file)
    payroll = round(sum(p["salary"] for p in league["players"] if p["team_id"] == OUR_TEAM), 2)
    cap = league["rules"]["salary_cap"]
    return {
        "team": f"{team['city']} {team['name']}", "record": _record(ours),
        "standing": f"{_ordinal(ours['rank'])} of {len(table)}",
        "points_for": ours["points_for"], "points_against": ours["points_against"],
        "playoffs": b and b["our_result"], "champion": b and b["champion"],
        "trades": deadline.our_trades(db_file), **_counts(db_file),
        "cap": {"payroll": payroll, "cap_space": round(cap - payroll, 2), "hard_cap": cap,
                "roster": sum(p["team_id"] == OUR_TEAM for p in league["players"]),
                "under_the_cap": payroll <= cap},
        "leaders": leaders(db_file)}
