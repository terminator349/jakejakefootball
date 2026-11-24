"""Calling the plays (task G8): the owner calls the Herons' plays in a live game.

A game in progress is kept as the list of calls made so far, one entry per
Game.step(): [offense_call, defense_call], where None means the AI made that
call. The simulator is seeded, so replaying the game's seed with the same
calls rebuilds exactly the same game. A live game therefore survives a
restart, Save & quit, or another browser tab, and costs one replay (well under
a tenth of a second) per request.

Two levels, as in the roadmap:
  key    the game sims until a key moment, then hands the owner the call:
         on offense a 4th down, the red zone, the two-minute drill or
         overtime; on defense the opponent in our red zone, overtime, or
         its two-minute drill in a one-score game.
  every  the owner calls every snap, on offense and on defense.

Rival games are always simmed. When our game ends it is saved like any other
(season.save_result), and the rest of the week is played.
"""

import json
import random

from agents import season
from agents.league_db import connect
from agents.simulator import (DEFENSE_CALLS, MATCHUP, OFFENSE_PLAYS, UNITS, Game, Situation,
                              call_offense, drives, field_goal_distance, in_field_goal_range, soften, wants_spike)

LEVELS = ("key", "every")
OFFENSE_LABELS = {"run_inside": "Run inside", "run_outside": "Run outside", "pass_short": "Short pass",
                  "pass_deep": "Deep pass", "play_action": "Play action", "screen": "Screen", "punt": "Punt",
                  "field_goal": "Field goal", "kneel": "Kneel", "spike": "Spike"}
DEFENSE_LABELS = {"base": "Base", "blitz": "Blitz", "cover_2": "Cover 2", "deep_zone": "Deep zone",
                  "run_stuff": "Run stuff"}


def key_moment(sit: Situation, team_id: str) -> bool:
    """Whether the owner gets the call at the 'key moments' level."""
    two_minute = sit.quarter in (2, 4) and sit.clock <= 120
    if sit.quarter >= 5:  # overtime
        return True
    if sit.offense == team_id:
        return sit.down == 4 or sit.yardline >= 80 or two_minute
    close = abs(sit.lead) <= 8
    return sit.yardline >= 80 or (two_minute and sit.quarter == 4 and close)


def _ai_special_teams(game: Game, sit: Situation) -> bool:
    """Whether the AI offense is about to punt, kick, kneel or spike (so a defensive call
    would do nothing). Peeks with a copy of the AI's random stream, so nothing changes."""
    offense = game.teams[sit.offense]
    if wants_spike(sit, offense):
        return True
    rng = random.Random()
    rng.setstate(game.call_rng.getstate())
    return call_offense(sit, offense, game.teams[sit.defense], rng) not in OFFENSE_PLAYS


def _our_call(game: Game, team_id: str, level: str) -> bool:
    if game.over:
        return False
    sit = game.situation()
    if level == "key" and not key_moment(sit, team_id):
        return False
    return sit.offense == team_id or not _ai_special_teams(game, sit)


# ---- Loading and saving a game in progress ---------------------------------------

def _row(db, game_id: int):
    row = db.execute("SELECT l.*, g.week, g.home_team_id, g.away_team_id, g.home_score FROM live_games l "
                     "JOIN games g ON g.id = l.game_id WHERE l.game_id = ?", (game_id,)).fetchone()
    if row is None:
        raise ValueError(f"Game {game_id} isn't being called. Start it with Call it.")
    return row


def _replay(db, row) -> tuple[Game, list]:
    game_row = db.execute("SELECT * FROM games WHERE id = ?", (row["game_id"],)).fetchone()
    game, inputs = season.new_game(db, game_row), json.loads(row["inputs"])
    for offense_call, defense_call in inputs:
        game.step(offense_call, defense_call)
    return game, inputs


def _run_to_our_call(game: Game, inputs: list, team_id: str, level: str) -> None:
    while not game.over and not _our_call(game, team_id, level):
        game.step()
        inputs.append([None, None])


def _store(db, game_id: int, inputs: list, level: str) -> None:
    db.execute("UPDATE live_games SET inputs = ?, level = ? WHERE game_id = ?", (json.dumps(inputs), level, game_id))


def _finish(db, row, game: Game) -> None:
    game_row = db.execute("SELECT * FROM games WHERE id = ?", (row["game_id"],)).fetchone()
    season.save_result(db, game_row, game)  # also removes the live game


def _transaction(action):
    """Run action(db) in one write transaction; play the rest of the week if our game ended."""
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        result, finished = action(db)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
    if finished:
        season.play_week()  # the rival games; ours is already saved
    return result


# ---- What the owner sees ----------------------------------------------------------

def _options(game: Game, sit: Situation, team_id: str) -> list[dict]:
    if sit.offense == team_id:
        options = []
        for call in OFFENSE_PLAYS:
            unit, against = UNITS[call]
            edge = soften(game._unit(sit.offense, unit) - game._unit(sit.defense, against))
            options.append({"call": call, "label": OFFENSE_LABELS[call], "group": "run" if "run" in call else "pass",
                            "edge": round(edge, 1)})
        distance = field_goal_distance(sit.yardline)
        in_range = in_field_goal_range(sit, game.teams[sit.offense])
        options += [{"call": "punt", "label": "Punt", "group": "special"},
                    {"call": "field_goal", "label": f"Field goal ({distance} yds)", "group": "special",
                     "note": None if in_range else "out of range"},
                    {"call": "kneel", "label": "Kneel", "group": "special"},
                    {"call": "spike", "label": "Spike", "group": "special",
                     "note": None if sit.clock_running else "clock is stopped"}]
        return options
    options = []
    for call in DEFENSE_CALLS:
        stops = [OFFENSE_LABELS[p].lower() for p in OFFENSE_PLAYS if MATCHUP[p][call] <= -3]
        weak = [OFFENSE_LABELS[p].lower() for p in OFFENSE_PLAYS if MATCHUP[p][call] >= 4]
        options.append({"call": call, "label": DEFENSE_LABELS[call], "group": "defense",
                        "stops": stops, "weak_against": weak})
    return options


def _threats(game: Game, sit: Situation) -> list[dict]:
    """The offense's matchups against our defense, strongest first."""
    out = []
    for call in OFFENSE_PLAYS:
        unit, against = UNITS[call]
        out.append({"play": OFFENSE_LABELS[call],
                    "edge": round(soften(game._unit(sit.offense, unit) - game._unit(sit.defense, against)), 1)})
    return sorted(out, key=lambda t: -t["edge"])


def _view(game: Game, row, level: str, first_new: int, final=None) -> dict:
    team = row["team_id"]
    view = {"game_id": row["game_id"], "week": row["week"], "team": team, "level": level,
            "home": game.home.team_id, "away": game.away.team_id, "over": game.over,
            "score": dict(game.score), "plays": game.plays, "drives": drives(game.plays), "first_new": first_new,
            "situation": None, "side": None, "options": [], "threats": []}
    if not game.over:
        sit = game.situation()
        view["situation"] = {"quarter": sit.quarter, "clock": sit.clock, "offense": sit.offense,
                             "defense": sit.defense, "down": sit.down, "distance": sit.distance,
                             "yardline": sit.yardline, "timeouts": sit.timeouts, "clock_running": sit.clock_running}
        view["side"] = "offense" if sit.offense == team else "defense"
        view["options"] = _options(game, sit, team)
        if view["side"] == "defense":
            view["threats"] = _threats(game, sit)
    return view


# ---- Actions -----------------------------------------------------------------------

def start(level: str = "key") -> dict:
    """Start calling our game this week: sim to the first moment that's ours to call."""
    if level not in LEVELS:
        raise ValueError(f"Unknown level {level!r}. Levels: {LEVELS}")

    def action(db):
        our = db.execute("SELECT json_extract(value, '$') FROM settings WHERE key = 'our_team'").fetchone()[0]
        week = db.execute("SELECT current_week FROM game").fetchone()[0]
        game_row = db.execute("SELECT * FROM games WHERE week = ? AND ? IN (home_team_id, away_team_id)",
                              (week, our)).fetchone()
        if game_row is None:
            raise ValueError("There's no game for us this week.")
        if game_row["home_score"] is not None:
            raise ValueError("This week's game has already been played.")
        if db.execute("SELECT 1 FROM live_games WHERE game_id = ?", (game_row["id"],)).fetchone():
            raise ValueError("This game is already being called. Carry on with it instead.")
        db.execute("INSERT INTO live_games VALUES (?, ?, ?, '[]')", (game_row["id"], our, level))
        row = _row(db, game_row["id"])
        game, inputs = _replay(db, row)
        _run_to_our_call(game, inputs, our, level)
        _store(db, row["game_id"], inputs, level)
        if game.over:
            _finish(db, row, game)
        return _view(game, row, level, 0), game.over

    return _transaction(action)


def state(game_id: int) -> dict:
    """The game in progress as it stands, ready for the owner's next call."""
    db = connect()
    try:
        row = _row(db, game_id)
        game, _ = _replay(db, row)
        return _view(game, row, row["level"], len(game.plays))
    finally:
        db.close()


def current() -> dict | None:
    """The game being called this week, if any: its id and level."""
    db = connect()
    try:
        row = db.execute("SELECT l.game_id, l.level FROM live_games l JOIN games g ON g.id = l.game_id "
                         "JOIN game ON g.week = game.current_week").fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def call(game_id: int, play: str, level: str | None = None) -> dict:
    """Make the owner's call (an offensive play or a defensive call, whichever side we're
    on), then sim to the next moment that's ours to call, or to the end of the game."""
    def action(db):
        row = _row(db, game_id)
        lvl = level or row["level"]
        if lvl not in LEVELS:
            raise ValueError(f"Unknown level {lvl!r}. Levels: {LEVELS}")
        game, inputs = _replay(db, row)
        if game.over:
            raise ValueError("The game is over.")
        sit = game.situation()
        first_new = len(game.plays)
        if sit.offense == row["team_id"]:
            game.step(offense_call=play)  # raises ValueError for an unknown play, before anything changes
            inputs.append([play, None])
        else:
            game.step(defense_call=play)
            inputs.append([None, play])
        _run_to_our_call(game, inputs, row["team_id"], lvl)
        _store(db, game_id, inputs, lvl)
        if game.over:
            _finish(db, row, game)
        return _view(game, row, lvl, first_new), game.over

    return _transaction(action)


def set_level(game_id: int, level: str) -> dict:
    """Switch between key moments and every snap. At key moments, the game sims on to the next one."""
    if level not in LEVELS:
        raise ValueError(f"Unknown level {level!r}. Levels: {LEVELS}")

    def action(db):
        row = _row(db, game_id)
        game, inputs = _replay(db, row)
        first_new = len(game.plays)
        _run_to_our_call(game, inputs, row["team_id"], level)
        _store(db, game_id, inputs, level)
        if game.over:
            _finish(db, row, game)
        return _view(game, row, level, first_new), game.over

    return _transaction(action)


def sim_rest(game_id: int) -> dict:
    """Hand the rest of the game to the AI and play it out."""
    def action(db):
        row = _row(db, game_id)
        game, inputs = _replay(db, row)
        first_new = len(game.plays)
        while not game.over:
            game.step()
            inputs.append([None, None])
        _finish(db, row, game)
        return _view(game, row, row["level"], first_new), True

    return _transaction(action)
