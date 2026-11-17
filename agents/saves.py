"""Save files (task G1): one SQLite database per game, in saves/.

"New game" builds a fresh league database from the data/league.json seed, with
its own season seed, so a save holds everything about one game: rosters,
contracts, the current week, the schedule and results, and the move log.
"Load game" checks a save and makes it the league the tools read.

The same season seed gives the same schedule (and, from task 3.1, the same
games), so tests and the demo can replay a season exactly.
"""

import re
import secrets
from pathlib import Path

from agents import league_db

SAVES_DIR = Path(__file__).parent.parent / "saves"

# Letters, digits, - and _ only, so a name can never point outside saves/.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")


def save_path(name: str) -> Path:
    if not _NAME.fullmatch(name):
        raise ValueError(f"Save names use letters, digits, - and _ (up to 40 characters); got {name!r}.")
    return SAVES_DIR / f"{name}.db"


def new_game(name: str, season_seed: int | None = None, overwrite: bool = False) -> Path:
    """Start a new game in saves/<name>.db, at week 1 of a fresh season. Picks a random
    season seed unless one is given. Refuses to replace an existing save unless told to."""
    path = save_path(name)
    if path.exists() and not overwrite:
        raise FileExistsError(f"There is already a save called {name!r}.")
    SAVES_DIR.mkdir(exist_ok=True)
    league_db.build(path, season_seed=secrets.randbelow(2**31) if season_seed is None else season_seed)
    return path


def load_game(name: str) -> Path:
    """Make saves/<name>.db the league every tool reads, and return its path.
    Raises FileNotFoundError for a missing save and OutdatedDatabase for one made by
    an older version."""
    path = save_path(name)
    if not path.exists():
        raise FileNotFoundError(f"There is no save called {name!r}.")
    league_db.connect(path).close()  # raises OutdatedDatabase for an old save
    league_db.DB_FILE = path
    return path


def list_saves() -> list[dict]:
    """Every save, most recently played first: its name, week, and our team's record.
    A save from an older version is listed with outdated=True."""
    saves = []
    for path in sorted(SAVES_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not _NAME.fullmatch(path.stem):
            continue
        try:
            db = league_db.connect(path)
        except league_db.OutdatedDatabase:
            saves.append({"name": path.stem, "outdated": True})
            continue
        try:
            our_team = db.execute("SELECT json_extract(value, '$') FROM settings "
                                  "WHERE key = 'our_team'").fetchone()[0]
            week = db.execute("SELECT current_week FROM game").fetchone()[0]
            record = db.execute("SELECT wins, losses, ties FROM standings WHERE team_id = ?",
                                (our_team,)).fetchone()
        finally:
            db.close()
        saves.append({"name": path.stem, "outdated": False, "week": week, "team_id": our_team,
                      "wins": record["wins"], "losses": record["losses"], "ties": record["ties"]})
    return saves
