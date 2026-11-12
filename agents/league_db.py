"""The league's SQLite database: teams, rosters, contracts and the season.

data/league.json is the generated start of the season. Every league database is
built from it: each save file (agents/saves.py) is one, and data/league.db is
the default league that run.py and the tools use when no game is loaded. Moves
change a database, never the seed.

Since task G1 a database also holds the game: the current week, the 17-week
schedule with results, and a log of every move. Standings are a view over the
results. Since task 3.1 it also keeps every simulated snap and each player's
stats per game.

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
DEFAULT_DB_FILE = DATA_DIR / "league.db"
DB_FILE = DEFAULT_DB_FILE  # the database the tools use; a loaded game points this at its save

# Raised whenever the schema changes, so an old database is never read as a new one.
# 0 (SQLite's default): tasks 1.1 - 1.2. 1: task G1 adds the game tables.
# 2: task 3.1 adds play logs and player game stats.
SCHEMA_VERSION = 2

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
    current_week INTEGER NOT NULL CHECK (current_week >= 1),  -- season_games + 1 once the season is over
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
CREATE VIEW standings AS
WITH sides AS (
    SELECT home_team_id AS team_id, home_score AS pf, away_score AS pa FROM games WHERE home_score IS NOT NULL
    UNION ALL
    SELECT away_team_id, away_score, home_score FROM games WHERE home_score IS NOT NULL
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

# How to bring an older database up to date, by the version it is at. A version not
# listed here can't be upgraded: data/league.db is rebuilt, and a save is refused.
MIGRATIONS = {1: GAME_LOG_SCHEMA}

# The MCP server runs tool calls in parallel threads; only one may build a missing database.
_build_lock = threading.Lock()


class OutdatedDatabase(Exception):
    """The database was made by an older version of this code."""


def build(db_file: Path | None = None, seed_file: Path | None = None, season_seed: int | None = None) -> None:
    """Create the database from the seed, at week 1 with a fresh schedule, replacing
    any database already there."""
    from agents.season import make_schedule  # season imports this module


    # Paths are read at call time, so tests can point DB_FILE at a scratch database.
    db_file, seed_file = db_file or DB_FILE, seed_file or SEED_FILE
    if not seed_file.exists():
        raise FileNotFoundError(f"{seed_file} not found. Run: python data/generate_league.py")
    seed = json.loads(seed_file.read_text())

    # Build beside the real file and swap it in at the end, so nobody reads a half-built league.
    tmp_file = db_file.with_name(db_file.name + ".tmp")
    tmp_file.unlink(missing_ok=True)
    with sqlite3.connect(tmp_file) as db:
        db.executescript(SCHEMA + GAME_LOG_SCHEMA)
        db.executemany("INSERT INTO settings VALUES (?, ?)",
                       [("sport", json.dumps(seed["sport"])), ("our_team", json.dumps(seed["our_team"]))])
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


if __name__ == "__main__":
    build(DEFAULT_DB_FILE)
    print(f"Built {DEFAULT_DB_FILE} from {SEED_FILE}")
