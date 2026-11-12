"""The league's SQLite database: teams, rosters and contracts.

data/league.json is the generated start of the season; data/league.db is the
league as it stands, built from that seed. From task 1.2 on, moves change the
database, never the seed.

    python -m agents.league_db    # rebuild league.db from league.json (undoes all moves)

connect() builds the database the first time it is needed.
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SEED_FILE = DATA_DIR / "league.json"
DB_FILE = DATA_DIR / "league.db"

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
"""

# The MCP server runs tool calls in parallel threads; only one may build a missing database.
_build_lock = threading.Lock()


def build(db_file: Path | None = None, seed_file: Path | None = None) -> None:
    """Create the database from the seed, replacing any database already there."""
    # Paths are read at call time, so tests can point DB_FILE at a scratch database.
    db_file, seed_file = db_file or DB_FILE, seed_file or SEED_FILE
    if not seed_file.exists():
        raise FileNotFoundError(f"{seed_file} not found. Run: python data/generate_league.py")
    seed = json.loads(seed_file.read_text())

    # Build beside the real file and swap it in at the end, so nobody reads a half-built league.
    tmp_file = db_file.with_name(db_file.name + ".tmp")
    tmp_file.unlink(missing_ok=True)
    with sqlite3.connect(tmp_file) as db:
        db.executescript(SCHEMA)
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
    db.close()
    os.replace(tmp_file, db_file)


def connect(db_file: Path | None = None) -> sqlite3.Connection:
    db_file = db_file or DB_FILE
    if not db_file.exists():
        with _build_lock:
            if not db_file.exists():  # another thread may have built it while we waited
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
    build()
    print(f"Built {DB_FILE} from {SEED_FILE}")
