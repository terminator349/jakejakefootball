"""The game loop (task G2): what the owner sees each week, in plain Python.

The web page (ui/game.html) shows one week at a time. Before the games:
the record, the cap, this week's opponent and a few front-office notes. The
owner plays the week (sim our game, or watch it drive by drive), sees the
results and moves on to the next week. Everything is saved as it happens, so
quitting at any point and loading the save later carries on from there.

The notes are facts read from the league, not model output. The GM's own
briefing (task G3, agents/briefing.py) is written from the same facts; the notes
stand in for it while it's written, without an API key, or if it doesn't check out.
"""

import json

from agents import live, season, tools

POSITION_NAMES = {"QB": "quarterback", "RB": "running back", "WR": "receiver", "TE": "tight end",
                  "OL": "offensive line", "DL": "defensive line", "LB": "linebacker", "CB": "cornerback",
                  "S": "safety", "K": "kicker", "P": "punter"}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _record(row: dict) -> str:
    return f"{row['wins']}-{row['losses']}" + (f"-{row['ties']}" if row["ties"] else "")


def _our_game(games: list[dict], team_id: str) -> dict | None:
    return next((g for g in games if team_id in (g["home_team_id"], g["away_team_id"])), None)


def _from_our_side(game: dict, team_id: str, table: dict[str, dict]) -> dict:
    """A game as the owner sees it: the opponent, home or away, and the score if played."""
    home = game["home_team_id"] == team_id
    opponent = game["away_team_id"] if home else game["home_team_id"]
    played = game["home_score"] is not None
    ours, theirs = (game["home_score"], game["away_score"]) if home else (game["away_score"], game["home_score"])
    opp = table[opponent]
    return {"game_id": game["id"], "week": game["week"], "home": home, "played": played,
            "opponent": {"id": opponent, "city": opp["city"], "name": opp["name"], "record": _record(opp),
                         "rank": opp["rank"]},
            "our_score": ours, "their_score": theirs,
            "outcome": None if not played else "win" if ours > theirs else "loss" if ours < theirs else "tie"}


def _rating_name(comparison: dict) -> str:
    position = POSITION_NAMES.get(comparison["position"], comparison["position"])
    rating = comparison["rating"].replace("_", " ")
    return position if rating == "overall" else f"{position} {rating}"


def overview() -> dict:
    """The week as the owner sees it, for the loaded league."""
    league = json.loads(tools.list_teams())
    rules = json.loads(tools.get_league_rules())
    our = league["our_team"]
    team = next(t for t in league["teams"] if t["id"] == our)
    table = {row["team_id"]: row for row in season.standings()}
    week, last_week = season.current_week(), rules["season_games"]
    over = week > last_week

    this_week = None if over else _our_game(season.games(week), our)
    this_week = this_week and _from_our_side(this_week, our, table)
    week_played = not over and all(g["home_score"] is not None for g in season.games(week))
    last = _our_game(season.games(week - 1), our) if week > 1 else None
    last = last and _from_our_side(last, our, table)
    roster = json.loads(tools.get_roster(our))["players"]
    deadline = rules["trade_deadline_week"]

    notes = []
    if last:
        score, city = f"{last['our_score']}-{last['their_score']}", last["opponent"]["city"]
        if last["home"]:
            verb = {"win": "Beat", "loss": "Lost to", "tie": "Tied"}[last["outcome"]]
            notes.append(f"Last week: {verb} {city} {score} at home.")
        else:
            verb = {"win": "Won", "loss": "Lost", "tie": "Tied"}[last["outcome"]]
            notes.append(f"Last week: {verb} at {city} {score}.")
    if this_week and not this_week["played"]:
        opp = this_week["opponent"]
        standing = f", {_ordinal(opp['rank'])}" if week > 1 else ""
        notes.append(f"This week: {'' if this_week['home'] else 'at '}{opp['city']} {opp['name']} "
                     f"({opp['record']}{standing}){' at home' if this_week['home'] else ''}.")
    comparisons = json.loads(tools.compare_to_league(our))["comparisons"]
    weakest, strongest = comparisons[0], comparisons[-1]
    notes.append(f"Weakest spot: {_rating_name(weakest)}, {_ordinal(weakest['rank'])} of "
                 f"{len(league['teams'])} ({weakest['team_avg']:.0f} against a league average of "
                 f"{weakest['league_avg']:.0f}).")
    if strongest["gap"] > 0:
        notes.append(f"Strongest: {_rating_name(strongest)}, {_ordinal(strongest['rank'])} of {len(league['teams'])}.")
    if over:
        notes.append(f"The regular season is over: {_record(table[our])}, {_ordinal(table[our]['rank'])} of "
                     f"{len(league['teams'])}. The playoffs arrive with task G6.")
    elif week <= deadline:
        left = deadline - week
        notes.append("The trade deadline is after this week." if left == 0 else
                     f"Trade deadline after week {deadline}: {left} more week{'s' if left != 1 else ''} after this one.")
    else:
        notes.append("The trade deadline has passed. The roster is set for the season.")
    notes.append(f"Cap space: ${team['cap_space']:.1f}M under the ${rules['salary_cap']:.0f}M hard cap, "
                 f"with {len(roster)} players (limit {rules['roster_max']}).")

    ours = table[our]
    return {
        "week": week, "season_games": last_week, "season_over": over, "week_played": week_played,
        "trade_deadline_week": deadline, "deadline_passed": week > deadline,
        "team": {"id": our, "city": team["city"], "name": team["name"], "record": _record(ours),
                 "wins": ours["wins"], "losses": ours["losses"], "ties": ours["ties"], "rank": ours["rank"],
                 "teams": len(league["teams"]), "points_for": ours["points_for"],
                 "points_against": ours["points_against"], "payroll": team["payroll"],
                 "cap_space": team["cap_space"], "salary_cap": rules["salary_cap"], "roster_size": len(roster),
                 "roster_max": rules["roster_max"]},
        "this_week": this_week, "last_week": last, "notes": notes,
        "live": None if over else live.current(),  # our game, if the owner is calling it (G8)
    }


def play_week() -> dict:
    """Play the rest of this week's games (ours included) and say which one is ours.
    The scores are saved at once, so watching our game afterwards is a replay."""
    our = json.loads(tools.list_teams())["our_team"]
    if live.current():
        raise ValueError("Our game is being called. Finish it, or sim the rest of it, first.")
    played = season.play_week()
    ours = _our_game(season.games(season.current_week()), our)
    return {"played": played, "our_game_id": ours["id"] if ours else None}


def our_schedule() -> list[dict]:
    """Our 17 games: opponent, home or away, and the result once played."""
    our = json.loads(tools.list_teams())["our_team"]
    table = {row["team_id"]: row for row in season.standings()}
    return [_from_our_side(g, our, table) for g in season.games() if our in (g["home_team_id"], g["away_team_id"])]
