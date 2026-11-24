"""The league's SQLite database: teams, rosters, contracts and the season.

data/league.json is the generated start of the season. Every league database is
built from it: each save file (agents/saves.py) is one, and data/league.db is
the default league that run.py and the tools use when no game is loaded. Moves
change a database, never the seed.

Since task G1 a database also holds the game: the current week, the 17-week
schedule with results, and a log of every move. Standings are a view over the
results. Since task 3.1 it also keeps every simulated snap and each player's
stats per game, since task 2.1 the Trade Desk's trade proposals, and since G4 the owner's
orders and the GM's proposed moves.

    python -m agents.league_db    # rebuild data/league.db from league.json (undoes all moves)

connect() builds the database the first time it is needed and upgrades an older
one where it can (MIGRATIONS). Otherwise it rebuilds data/league.db, but never
a save.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SEED_FILE = DATA_DIR / "league.json"
# The leagues a new game can start from (task 4.4): the generated one, or the six
# franchises filled with real NFL players from 2025 (data/real_league.py).
LEAGUES = {"generated": "Generated league", "real": "Real 2025 players"}
SEED_FILES = {"generated": SEED_FILE, "real": DATA_DIR / "league_real.json"}
# Set to the loaded save's path, so the skills' scripts (run in their own process)
# read the same league as the game.
DB_ENV = "FRONT_OFFICE_DB"
DEFAULT_DB_FILE = DATA_DIR / "league.db"
DB_FILE = DEFAULT_DB_FILE  # the database the tools use; a loaded game points this at its save

# Raised whenever the schema changes, so an old database is never read as a new one.
# 0 (SQLite's default): tasks 1.1 - 1.2. 1: task G1 adds the game tables.
# 2: task 3.1 adds play logs and player game stats.
# 3: task G8 adds games in progress, where the owner calls the plays.
# 4: task G3 adds the GM's weekly briefings.
# 5: task 2.1 adds the Trade Desk's trade proposals.
# 6: task G4 adds the owner's orders and the moves the GM proposes for approval.
# 7: task 3.2 adds injuries and the depth chart. (3.2 was built on a branch where it
#    was version 5; MIGRATIONS below brings those databases up to date too.)
# 8: task G6 leaves the playoffs out of the standings.
# 9: task 4.1 adds the scouting team's reports.
# 10: task 4.2 keeps the GM's answers to the owner's questions, for its memory.
SCHEMA_VERSION = 10

# The season seed for data/league.db. A new game picks its own (agents/saves.py).
DEFAULT_SEASON_SEED = 2026

SCHEMA = """
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL              -- JSON
);
CREATE TABLE rules (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL              -- JSON
);
CREATE TABLE positions (
    position   TEXT PRIMARY KEY,
    starters   INTEGER NOT NULL,
    sort_order INTEGER NOT NULL
);
CREATE TABLE teams (
    id   TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE players (
    id                       TEXT PRIMARY KEY,
    team_id                  TEXT NOT NULL REFERENCES teams(id),
    name                     TEXT NOT NULL,
    position                 TEXT NOT NULL REFERENCES positions(position),
    age                      INTEGER NOT NULL,
    overall                  INTEGER NOT NULL,
    games_missed_last_season INTEGER NOT NULL
);
CREATE TABLE ratings (
    player_id TEXT NOT NULL REFERENCES players(id),
    rating    TEXT NOT NULL,
    value     INTEGER NOT NULL CHECK (value BETWEEN 25 AND 99),
    PRIMARY KEY (player_id, rating)
);
CREATE TABLE contracts (
    player_id  TEXT PRIMARY KEY REFERENCES players(id),
    salary     REAL NOT NULL CHECK (salary > 0),   -- $M per season
    years_left INTEGER NOT NULL CHECK (years_left >= 0)
);
CREATE INDEX players_by_team ON players (team_id, position);

-- The game (task G1). One row.
CREATE TABLE game (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    current_week INTEGER NOT NULL CHECK (current_week >= 1),  -- after season_games, the playoffs (G6)
    seed         INTEGER NOT NULL,                            -- the schedule and simulator draw from this
    created_at   TEXT NOT NULL
);
CREATE TABLE games (
    id           INTEGER PRIMARY KEY,
    week         INTEGER NOT NULL CHECK (week >= 1),
    home_team_id TEXT NOT NULL REFERENCES teams(id),
    away_team_id TEXT NOT NULL REFERENCES teams(id),
    home_score   INTEGER CHECK (home_score >= 0),             -- NULL until the game is played
    away_score   INTEGER CHECK (away_score >= 0),
    CHECK (home_team_id <> away_team_id),
    CHECK ((home_score IS NULL) = (away_score IS NULL))
);
CREATE INDEX games_by_week ON games (week);
CREATE TABLE moves (
    id   INTEGER PRIMARY KEY,
    week INTEGER NOT NULL CHECK (week >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('trade'))
);
CREATE TABLE move_players (
    move_id      INTEGER NOT NULL REFERENCES moves(id),
    player_id    TEXT NOT NULL REFERENCES players(id),
    from_team_id TEXT NOT NULL REFERENCES teams(id),
    to_team_id   TEXT NOT NULL REFERENCES teams(id),
    PRIMARY KEY (move_id, player_id)
);
"""

# The regular season's standings. Playoff games (weeks after season_games, task G6) don't
# count: the seeds come from these, and a record is the regular season's.
STANDINGS_VIEW = """
CREATE VIEW standings AS
WITH regular AS (
    SELECT * FROM games WHERE home_score IS NOT NULL
                          AND week <= (SELECT CAST(value AS INTEGER) FROM rules WHERE key = 'season_games')
), sides AS (
    SELECT home_team_id AS team_id, home_score AS pf, away_score AS pa FROM regular
    UNION ALL
    SELECT away_team_id, away_score, home_score FROM regular
)
SELECT t.id                       AS team_id,
       COALESCE(SUM(s.pf > s.pa), 0) AS wins,
       COALESCE(SUM(s.pf < s.pa), 0) AS losses,
       COALESCE(SUM(s.pf = s.pa), 0) AS ties,
       COALESCE(SUM(s.pf), 0)        AS points_for,
       COALESCE(SUM(s.pa), 0)        AS points_against
FROM teams t LEFT JOIN sides s ON s.team_id = t.id
GROUP BY t.id;
"""

# G6: the standings view, rebuilt to leave the playoffs out.
PLAYOFF_SCHEMA = "DROP VIEW IF EXISTS standings;\n" + STANDINGS_VIEW

GAME_LOG_SCHEMA = """
-- Simulated games (task 3.1): every snap, and each player's stats per game.
CREATE TABLE plays (
    game_id         INTEGER NOT NULL REFERENCES games(id),
    n               INTEGER NOT NULL,              -- snap number in the game
    drive           INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,              -- 5 = overtime
    clock           INTEGER NOT NULL,              -- seconds left in the quarter at the snap
    offense_team_id TEXT NOT NULL REFERENCES teams(id),
    down            INTEGER NOT NULL,
    distance        INTEGER NOT NULL,
    yardline        INTEGER NOT NULL,              -- from the offense's own goal line
    call            TEXT NOT NULL,
    defense_call    TEXT,
    result          TEXT NOT NULL,
    yards           INTEGER NOT NULL,
    text            TEXT NOT NULL,
    home_score      INTEGER NOT NULL,              -- after the play
    away_score      INTEGER NOT NULL,
    PRIMARY KEY (game_id, n)
);
CREATE TABLE player_game_stats (
    game_id   INTEGER NOT NULL REFERENCES games(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    team_id   TEXT NOT NULL REFERENCES teams(id),  -- the player's team in that game
    stat      TEXT NOT NULL,                       -- e.g. pass_yds, rush_att, def_sacks
    value     INTEGER NOT NULL,
    PRIMARY KEY (game_id, player_id, stat)
);
"""

LIVE_SCHEMA = """
-- A game the owner is calling (task G8). Only the calls are kept: the game is
-- rebuilt by replaying its seed with them, so it carries on after a restart.
CREATE TABLE IF NOT EXISTS live_games (
    game_id INTEGER PRIMARY KEY REFERENCES games(id),
    team_id TEXT NOT NULL REFERENCES teams(id),    -- the team the owner calls for
    level   TEXT NOT NULL,                         -- 'key' (key moments) or 'every' (every snap)
    inputs  TEXT NOT NULL                          -- JSON: [offense_call, defense_call] per step, null = the AI's
);
"""

BRIEFING_SCHEMA = """
-- The GM's briefing for each week (task G3), written once and kept, so the owner
-- reads the same one every time. Only briefings whose numbers checked out are kept.
CREATE TABLE IF NOT EXISTS briefings (
    week     INTEGER PRIMARY KEY,
    briefing TEXT NOT NULL,                        -- JSON: headline, paragraphs, watch
    written  TEXT NOT NULL,                        -- when, in UTC
    cost     REAL                                  -- what the model calls cost, in $
);
"""

TRADE_DESK_SCHEMA = """
-- Trade proposals on the Trade Desk (task 2.1). A proposal is one team's offer to
-- another; it is checked against the 1.2 rules when it is made and again when the
-- other team accepts it, and only an accepted proposal moves players (via moves).
CREATE TABLE IF NOT EXISTS trade_proposals (
    id           INTEGER PRIMARY KEY,
    week         INTEGER NOT NULL CHECK (week >= 1),       -- the week it was proposed
    from_team_id TEXT NOT NULL REFERENCES teams(id),        -- the team making the offer
    to_team_id   TEXT NOT NULL REFERENCES teams(id),        -- the team that answers it
    sends        TEXT NOT NULL,                             -- JSON: player ids from_team gives up
    receives     TEXT NOT NULL,                             -- JSON: player ids to_team gives up
    note         TEXT NOT NULL DEFAULT '',                  -- the proposer's pitch
    status       TEXT NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'accepted', 'rejected', 'countered', 'withdrawn', 'void')),
    counter_of   INTEGER REFERENCES trade_proposals(id),    -- the proposal this one answers
    response     TEXT,                                      -- the answer's reason, or why it was voided
    decided_week INTEGER,
    move_id      INTEGER REFERENCES moves(id),              -- set once accepted
    CHECK (from_team_id <> to_team_id)
);
CREATE INDEX IF NOT EXISTS open_proposals ON trade_proposals (status, to_team_id);
"""

ORDERS_SCHEMA = """
-- The owner's orders and the GM's proposed moves (task G4). An order stands until the
-- owner cancels it. The GM reads it into terms that plain Python enforces, and each move
-- it proposes waits here for the owner: approved, it goes to the Trade Desk as our offer.
CREATE TABLE IF NOT EXISTS orders (
    id      INTEGER PRIMARY KEY,
    week    INTEGER NOT NULL CHECK (week >= 1),
    text    TEXT NOT NULL,                              -- the owner's words
    terms   TEXT NOT NULL,                              -- JSON: what the GM understood (OrderTerms)
    reply   TEXT,                                       -- the GM's answer to the owner
    status  TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
    cost    REAL                                        -- what the model calls cost, in $
);
CREATE TABLE IF NOT EXISTS gm_proposals (
    id               INTEGER PRIMARY KEY,
    order_id         INTEGER NOT NULL REFERENCES orders(id),
    week             INTEGER NOT NULL CHECK (week >= 1),
    team_id          TEXT NOT NULL REFERENCES teams(id), -- the other team
    sends            TEXT NOT NULL,                      -- JSON: our player ids
    receives         TEXT NOT NULL,                      -- JSON: their player ids
    reason           TEXT NOT NULL,                      -- the GM's case for it
    status           TEXT NOT NULL DEFAULT 'waiting'
                     CHECK (status IN ('waiting', 'approved', 'vetoed', 'void')),
    owner_note       TEXT,                               -- the owner's note, or why it was voided
    decided_week     INTEGER,
    desk_proposal_id INTEGER REFERENCES trade_proposals(id)  -- our offer on the Trade Desk, once approved
);
"""

SCOUTING_SCHEMA = """
-- The scouting team's reports (task 4.1): the trade targets it found for an order (or
-- the deadline), graded, with plain Python's numbers. Kept for the week screen and the
-- org chart (4.3).
CREATE TABLE IF NOT EXISTS scouting_reports (
    id        INTEGER PRIMARY KEY,
    week      INTEGER NOT NULL CHECK (week >= 1),
    order_id  INTEGER REFERENCES orders(id),             -- the order it was for, if any
    by        TEXT NOT NULL CHECK (by IN ('scouts', 'rules')),  -- graded by the model's scouts, or the rules
    positions TEXT NOT NULL,                             -- JSON: the positions scouted
    summary   TEXT NOT NULL,
    targets   TEXT NOT NULL,                             -- JSON: the graded targets, best first
    cost      REAL                                       -- what the model calls cost, in $
);
"""

MEMORY_SCHEMA = """
-- The GM's answers to the owner's questions (task 4.2). Everything else the front
-- office remembers is already in the save (orders, moves, trade proposals, scouting
-- reports, briefings); agents/memory.py reads it all back into one timeline.
CREATE TABLE IF NOT EXISTS gm_answers (
    id             INTEGER PRIMARY KEY,
    week           INTEGER NOT NULL CHECK (week >= 1),
    question       TEXT NOT NULL,                        -- the owner's words
    answer         TEXT NOT NULL,                        -- the GM's answer
    recommendation TEXT,
    consulted      TEXT NOT NULL DEFAULT '[]',           -- JSON: the specialists it asked
    cost           REAL                                  -- what the model calls cost, in $
);
"""

INJURY_SCHEMA = """
-- Injuries and the depth chart (task 3.2).
CREATE TABLE IF NOT EXISTS injuries (
    player_id   TEXT PRIMARY KEY REFERENCES players(id),
    team_id     TEXT NOT NULL REFERENCES teams(id),
    since_week  INTEGER NOT NULL,   -- the week the injury happened
    return_week INTEGER NOT NULL,   -- the first week the player is available again
    description TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS injuries_by_team ON injuries (team_id);
-- An explicit playing order the Coaching staff set for one team at one position. A
-- position with no rows here, or whose rows no longer match the roster there exactly
-- (a trade or a cut moved on), falls back to sorting by overall rating.
CREATE TABLE IF NOT EXISTS depth_chart (
    team_id   TEXT NOT NULL REFERENCES teams(id),
    position  TEXT NOT NULL REFERENCES positions(position),
    player_id TEXT NOT NULL REFERENCES players(id),
    rank      INTEGER NOT NULL,
    PRIMARY KEY (team_id, position, player_id)
);
"""

# How to bring an older database up to date, by the version it is at. A version not
# listed here can't be upgraded: data/league.db is rebuilt, and a save is refused.
# Every step is safe to run again (IF NOT EXISTS). That matters for version 5: 2.1 made
# it the Trade Desk, but on the 3.2 branch it meant injuries, so the step from 5 adds
# the Trade Desk's table too, and the step from 6 adds injuries whichever way it came.
MIGRATIONS = {1: GAME_LOG_SCHEMA, 2: LIVE_SCHEMA, 3: BRIEFING_SCHEMA, 4: TRADE_DESK_SCHEMA,
              5: TRADE_DESK_SCHEMA + ORDERS_SCHEMA, 6: INJURY_SCHEMA, 7: PLAYOFF_SCHEMA, 8: SCOUTING_SCHEMA,
              9: MEMORY_SCHEMA}

# The MCP server runs tool calls in parallel threads; only one may build a missing database.
_build_lock = threading.Lock()


class OutdatedDatabase(Exception):
    """The database was made by an older version of this code."""


def build(db_file: Path | None = None, seed_file: Path | None = None, season_seed: int | None = None,
          league: str | None = None) -> None:
    """Create the database from the seed, at week 1 with a fresh schedule, replacing
    any database already there. `league` picks the seed from LEAGUES (default: the
    generated league)."""
    from agents.season import make_schedule  # season imports this module


    # Paths are read at call time, so tests can point DB_FILE at a scratch database.
    if league is not None and league not in SEED_FILES:
        raise ValueError(f"Unknown league {league!r}. Valid: {list(SEED_FILES)}")
    db_file = db_file or DB_FILE
    seed_file = seed_file or (SEED_FILES[league] if league else SEED_FILE)
    if not seed_file.exists():
        raise FileNotFoundError(f"{seed_file} not found. Run: python data/generate_league.py")
    seed = json.loads(seed_file.read_text())

    # Build beside the real file and swap it in at the end, so nobody reads a half-built league.
    tmp_file = db_file.with_name(db_file.name + ".tmp")
    tmp_file.unlink(missing_ok=True)
    with sqlite3.connect(tmp_file) as db:
        db.executescript(SCHEMA + STANDINGS_VIEW + GAME_LOG_SCHEMA + LIVE_SCHEMA + BRIEFING_SCHEMA + TRADE_DESK_SCHEMA + ORDERS_SCHEMA
                         + INJURY_SCHEMA + SCOUTING_SCHEMA + MEMORY_SCHEMA)
        db.executemany("INSERT INTO settings VALUES (?, ?)",
                       [("sport", json.dumps(seed["sport"])), ("our_team", json.dumps(seed["our_team"])),
                        ("league", json.dumps(seed.get("league", "generated")))])
        rules = {k: v for k, v in seed["rules"].items() if k != "starters_per_position"}
        db.executemany("INSERT INTO rules VALUES (?, ?)", [(k, json.dumps(v)) for k, v in rules.items()])
        db.executemany("INSERT INTO positions VALUES (?, ?, ?)",
                       [(pos, n, i) for i, (pos, n) in enumerate(seed["rules"]["starters_per_position"].items())])
        db.executemany("INSERT INTO teams VALUES (:id, :city, :name)", seed["teams"])
        db.executemany("INSERT INTO players VALUES (:id, :team_id, :name, :position, :age, :overall, "
                       ":games_missed_last_season)", seed["players"])
        db.executemany("INSERT INTO ratings VALUES (?, ?, ?)",
                       [(p["id"], k, v) for p in seed["players"] for k, v in p["ratings"].items()])
        db.executemany("INSERT INTO contracts VALUES (:id, :salary, :contract_years)", seed["players"])

        season_seed = DEFAULT_SEASON_SEED if season_seed is None else season_seed
        db.execute("INSERT INTO game VALUES (1, 1, ?, ?)",
                   (season_seed, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        schedule = make_schedule([t["id"] for t in seed["teams"]], seed["rules"]["season_games"], season_seed)
        db.executemany("INSERT INTO games (week, home_team_id, away_team_id) VALUES (?, ?, ?)", schedule)
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.close()
    os.replace(tmp_file, db_file)


def _schema_version(db_file: Path) -> int:
    with sqlite3.connect(db_file) as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    return version


def _migrate(db_file: Path) -> None:
    """Apply each upgrade in turn, each in its own transaction, until the database is current."""
    while (version := _schema_version(db_file)) in MIGRATIONS:
        with sqlite3.connect(db_file) as db:
            db.executescript(f"BEGIN; {MIGRATIONS[version]} PRAGMA user_version = {version + 1}; COMMIT;")
        db.close()


def connect(db_file: Path | None = None) -> sqlite3.Connection:
    db_file = db_file or DB_FILE
    if not db_file.exists():
        with _build_lock:
            if not db_file.exists():  # another thread may have built it while we waited
                build(db_file)
    if _schema_version(db_file) in MIGRATIONS:
        with _build_lock:
            _migrate(db_file)
    if _schema_version(db_file) != SCHEMA_VERSION:
        if db_file.resolve() != DEFAULT_DB_FILE.resolve():
            raise OutdatedDatabase(f"{db_file} was made by an older version of Front Office "
                                   "and cannot be loaded. Start a new game.")
        with _build_lock:  # data/league.db is only the default league, so rebuild it
            if _schema_version(db_file) != SCHEMA_VERSION:
                build(db_file)
    db = sqlite3.connect(db_file)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def load_league(db_file: Path | None = None) -> dict:
    """The whole league as one dict, in the same shape as the seed file."""
    db = connect(db_file)
    try:
        settings = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM settings")}
        rules = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM rules ORDER BY rowid")}
        rules["starters_per_position"] = {
            row["position"]: row["starters"] for row in db.execute("SELECT * FROM positions ORDER BY sort_order")}

        ratings: dict[str, dict] = {}
        for row in db.execute("SELECT * FROM ratings ORDER BY rowid"):
            ratings.setdefault(row["player_id"], {})[row["rating"]] = row["value"]

        players = [
            {"id": row["id"], "name": row["name"], "team_id": row["team_id"], "position": row["position"],
             "age": row["age"], "overall": row["overall"], "contract_years": row["years_left"],
             "games_missed_last_season": row["games_missed_last_season"], "ratings": ratings[row["id"]],
             "salary": row["salary"]}
            for row in db.execute("SELECT p.*, c.salary, c.years_left FROM players p "
                                  "JOIN contracts c ON c.player_id = p.id ORDER BY p.rowid")
        ]
        teams = [dict(row) for row in db.execute("SELECT id, city, name FROM teams ORDER BY rowid")]
    finally:
        db.close()

    return {"sport": settings["sport"], "our_team": settings["our_team"], "rules": rules,
            "teams": teams, "players": players}


def league_kind(db_file: Path | None = None) -> str:
    """Which league the database was started from: "generated" or "real" (LEAGUES).
    A database from before task 4.4 is the generated league."""
    db = connect(db_file)
    try:
        row = db.execute("SELECT value FROM settings WHERE key = 'league'").fetchone()
    finally:
        db.close()
    return json.loads(row["value"]) if row else "generated"


# ---- Injuries and the depth chart (task 3.2) -------------------------------

def depth_chart_order(db: sqlite3.Connection, team_id: str) -> dict[str, list[str]]:
    """Every position where this team has an explicit order the Coaching staff set that
    still matches its roster there exactly, best first. A position left out means fall
    back to sorting by overall rating. Takes an open connection: callers (the simulator,
    mid-transaction) already have one."""
    by_position: dict[str, list[str]] = {}
    for row in db.execute("SELECT position, player_id FROM depth_chart WHERE team_id = ? ORDER BY position, rank",
                          (team_id,)):
        by_position.setdefault(row["position"], []).append(row["player_id"])

    valid = {}
    for position, order in by_position.items():
        roster = {row["id"] for row in db.execute(
            "SELECT id FROM players WHERE team_id = ? AND position = ?", (team_id, position))}
        if set(order) == roster:
            valid[position] = order
    return valid


def write_depth_chart(team_id: str, position: str, player_ids: list[str], db_file: Path | None = None) -> None:
    """Replace one team's playing order at one position. Does not check it against the
    roster; callers validate that first."""
    db = connect(db_file)
    try:
        with db:
            db.execute("DELETE FROM depth_chart WHERE team_id = ? AND position = ?", (team_id, position))
            db.executemany("INSERT INTO depth_chart (team_id, position, player_id, rank) VALUES (?, ?, ?, ?)",
                           [(team_id, position, pid, rank) for rank, pid in enumerate(player_ids)])
    finally:
        db.close()


def injured_player_ids(db: sqlite3.Connection, team_id: str, week: int) -> set[str]:
    """This team's players still out hurt in the given week. Takes an open connection."""
    return {row["player_id"] for row in db.execute(
        "SELECT player_id FROM injuries WHERE team_id = ? AND return_week > ?", (team_id, week))}


def save_injury(db: sqlite3.Connection, player_id: str, team_id: str, since_week: int, games_out: int,
               description: str) -> None:
    """Record (or update) a player's injury: out for `games_out` games starting the week
    after `since_week`. Takes an open connection: the season simulator calls this inside
    the transaction that saves a game."""
    return_week = since_week + games_out + 1
    db.execute(
        "INSERT INTO injuries (player_id, team_id, since_week, return_week, description) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(player_id) DO UPDATE SET team_id = excluded.team_id, since_week = excluded.since_week, "
        "return_week = excluded.return_week, description = excluded.description",
        (player_id, team_id, since_week, return_week, description))


def current_injuries(team_id: str | None = None, db_file: Path | None = None) -> list[dict]:
    """Every player still out hurt as of the current week: team, name, position, since
    which week, how many more games they'll miss, and a plain-English description.
    Optionally filtered to one team."""
    db = connect(db_file)
    try:
        week = db.execute("SELECT current_week FROM game").fetchone()[0]
        sql = ("SELECT i.*, p.name, p.position FROM injuries i JOIN players p ON p.id = i.player_id "
              "WHERE i.return_week > ?" + (" AND i.team_id = ?" if team_id else "") + " ORDER BY i.team_id, p.rowid")
        rows = db.execute(sql, (week, team_id) if team_id else (week,)).fetchall()
    finally:
        db.close()
    return [{"player_id": row["player_id"], "name": row["name"], "position": row["position"],
            "team_id": row["team_id"], "since_week": row["since_week"], "games_remaining": row["return_week"] - week,
            "description": row["description"]} for row in rows]


if __name__ == "__main__":
    build(DEFAULT_DB_FILE)
    print(f"Built {DEFAULT_DB_FILE} from {SEED_FILE}")
