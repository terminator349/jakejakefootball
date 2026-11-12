"""The season: schedule, current week, game results and standings (task G1).

Each league database (a save, or data/league.db) holds one season. The
schedule is made from the season's seed when the database is built, so the
same seed always gives the same schedule. Results are written one game at a
time (by the simulator, task 3.1), and the week only moves on once every game
in it has a result. Standings are worked out from the results when asked for,
so they can never disagree with them.

Weeks run from 1 to the league's season_games (17). After the last week's games
the current week is season_games + 1, meaning the regular season is over.
"""

import random
from pathlib import Path

from agents.league_db import connect


def _round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Rounds in which every team plays once, together covering every pairing once
    (the circle method: fix one team and rotate the rest)."""
    first, rest = teams[0], teams[1:]
    rounds = []
    for _ in range(len(teams) - 1):
        order = [first, *rest]
        rounds.append([(order[i], order[-1 - i]) for i in range(len(teams) // 2)])
        rest = rest[-1:] + rest[:-1]
    return rounds


def make_schedule(team_ids: list[str], weeks: int, seed: int) -> list[tuple[int, str, str]]:
    """(week, home, away) for every game. Every team plays once a week, and plays
    every rival before playing any of them again, so with six teams and 17 weeks
    each team meets three rivals three times and two rivals four times. No team
    plays the same opponent two weeks running, and home games are shared out as
    evenly as possible."""
    if len(team_ids) % 2:
        raise ValueError("The schedule needs an even number of teams.")
    rng = random.Random(seed)
    teams = sorted(team_ids)
    rng.shuffle(teams)
    rounds = _round_robin(teams)

    order: list[list[tuple[str, str]]] = []
    while len(order) < weeks:
        cycle = rounds[:]
        rng.shuffle(cycle)
        if order and cycle[0] == order[-1]:  # would repeat last week's matchups
            cycle[0], cycle[-1] = cycle[-1], cycle[0]
        order += cycle

    home_games = {team: 0 for team in teams}
    hosted: dict[tuple[str, str], int] = {}  # (host, visitor) -> times
    schedule = []
    for week, pairs in enumerate(order[:weeks], start=1):
        for a, b in pairs:
            # Host the rival you have hosted less; then whoever has fewer home games.
            key_a = (hosted.get((a, b), 0), home_games[a], rng.random())
            key_b = (hosted.get((b, a), 0), home_games[b], rng.random())
            home, away = (a, b) if key_a < key_b else (b, a)
            hosted[(home, away)] = hosted.get((home, away), 0) + 1
            home_games[home] += 1
            schedule.append([week, home, away])
    _even_out_home_games(schedule, weeks)
    return [tuple(game) for game in schedule]


def _even_out_home_games(schedule: list[list], weeks: int) -> None:
    """Give every team weeks // 2 or weeks // 2 + 1 home games (8 or 9 of 17).

    The first pass can leave a team with 7 or 10. Take a team with too many and
    follow a chain of rivals it could give a home game to, until one with too few:
    swapping home and away along the chain moves one home game from the first team
    to the last and leaves everyone in between as they were. Only a series played
    an odd number of times may change hands (2-1 becomes 1-2); a 2-2 split stays.
    """
    low, high = weeks // 2, (weeks + 1) // 2
    while True:
        home_games: dict[str, int] = {}
        hosted: dict[tuple[str, str], int] = {}
        for _, home, away in schedule:
            home_games[home] = home_games.get(home, 0) + 1
            home_games.setdefault(away, 0)
            hosted[(home, away)] = hosted.get((home, away), 0) + 1

        def can_give(home: str, away: str) -> bool:
            return hosted.get((home, away), 0) > hosted.get((away, home), 0)

        start = next((t for t in sorted(home_games) if home_games[t] > high), None)
        if start is None:
            start = next((t for t in sorted(home_games) if home_games[t] == high
                          and any(home_games[u] < low for u in home_games)), None)
        if start is None:
            return
        # Breadth-first search for the shortest chain to a team that can take a home game.
        came_from = {start: None}
        queue, end = [start], None
        while queue and end is None:
            team = queue.pop(0)
            for rival in sorted(home_games):
                if rival not in came_from and can_give(team, rival):
                    came_from[rival] = team
                    if home_games[rival] < low or (home_games[start] > high and home_games[rival] < high):
                        end = rival
                        break
                    queue.append(rival)
        if end is None:
            raise RuntimeError("Could not even out home games.")  # not seen for six teams
        while came_from[end] is not None:
            giver = came_from[end]
            game = next(g for g in reversed(schedule) if g[1] == giver and g[2] == end)
            game[1], game[2] = end, giver
            end = giver


def _season_games(db) -> int:
    return int(db.execute("SELECT value FROM rules WHERE key = 'season_games'").fetchone()[0])


def _current_week(db) -> int:
    return db.execute("SELECT current_week FROM game").fetchone()[0]


def current_week(db_file: Path | None = None) -> int:
    db = connect(db_file)
    try:
        return _current_week(db)
    finally:
        db.close()


def season_over(db_file: Path | None = None) -> bool:
    db = connect(db_file)
    try:
        return _current_week(db) > _season_games(db)
    finally:
        db.close()


def games(week: int | None = None, db_file: Path | None = None) -> list[dict]:
    """The schedule, or one week of it, with scores for games already played."""
    db = connect(db_file)
    try:
        sql = "SELECT * FROM games" + (" WHERE week = ?" if week is not None else "") + " ORDER BY week, id"
        return [dict(row) for row in db.execute(sql, () if week is None else (week,))]
    finally:
        db.close()


def record_result(game_id: int, home_score: int, away_score: int, db_file: Path | None = None) -> None:
    """Write the final score of a game in the current week. A game is played once."""
    if home_score < 0 or away_score < 0:
        raise ValueError("Scores cannot be negative.")
    db = connect(db_file)
    try:
        with db:
            game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
            if game is None:
                raise ValueError(f"There is no game {game_id}.")
            week = _current_week(db)
            if game["week"] != week:
                raise ValueError(f"Game {game_id} is in week {game['week']}; it is week {week}.")
            if game["home_score"] is not None:
                raise ValueError(f"Game {game_id} has already been played.")
            db.execute("UPDATE games SET home_score = ?, away_score = ? WHERE id = ?",
                       (home_score, away_score, game_id))
    finally:
        db.close()


def advance_week(db_file: Path | None = None) -> int:
    """Move on to the next week once every game this week has a result. Returns the new week."""
    db = connect(db_file)
    try:
        with db:
            week = _current_week(db)
            if week > _season_games(db):
                raise ValueError("The regular season is over.")
            unplayed = db.execute("SELECT COUNT(*) FROM games WHERE week = ? AND home_score IS NULL",
                                  (week,)).fetchone()[0]
            if unplayed:
                raise ValueError(f"{unplayed} game(s) in week {week} have not been played.")
            db.execute("UPDATE game SET current_week = current_week + 1")
            return week + 1
    finally:
        db.close()


def standings(db_file: Path | None = None) -> list[dict]:
    """Every team's record, best first: by win percentage (a tie counts as half a
    win), then point difference, then points scored."""
    db = connect(db_file)
    try:
        rows = [dict(row) for row in db.execute(
            "SELECT s.*, t.city, t.name FROM standings s JOIN teams t ON t.id = s.team_id ORDER BY t.rowid")]
    finally:
        db.close()

    for row in rows:
        played = row["wins"] + row["losses"] + row["ties"]
        row["win_pct"] = round((row["wins"] + row["ties"] / 2) / played, 3) if played else 0.0
        row["point_diff"] = row["points_for"] - row["points_against"]
    rows.sort(key=lambda r: (-r["win_pct"], -r["point_diff"], -r["points_for"], r["team_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
