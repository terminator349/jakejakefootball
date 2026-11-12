"""Checks for the league's SQLite database. No API key needed.

Each test builds its own scratch database from the seed (the scratch_db fixture
in conftest.py), so none of them touch data/league.db.
"""

import json
import sqlite3

import pytest

from agents import league_db
from agents.tools import get_roster, list_teams


def test_database_holds_exactly_the_seed(scratch_db):
    seed = json.loads(league_db.SEED_FILE.read_text())
    assert league_db.load_league() == seed


def test_rosters_and_contracts_are_tables(scratch_db):
    db = league_db.connect()
    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"teams", "players", "ratings", "contracts", "positions", "rules"} <= tables
    assert db.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 288
    assert db.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 288
    db.close()


def test_connect_builds_a_missing_database(tmp_path, monkeypatch):
    db_file = tmp_path / "new.db"
    monkeypatch.setattr(league_db, "DB_FILE", db_file)
    assert league_db.load_league()["our_team"] == "HAR"
    assert db_file.exists()


def test_tools_read_the_database_not_the_seed(scratch_db):
    """A salary changed in the database shows up in the tools' answers."""
    before = next(t for t in json.loads(list_teams())["teams"] if t["id"] == "HAR")
    player = json.loads(get_roster("HAR", "S"))["players"][0]
    db = league_db.connect()
    with db:
        db.execute("UPDATE contracts SET salary = salary + 2 WHERE player_id = ?", (player["id"],))
    db.close()

    after = next(t for t in json.loads(list_teams())["teams"] if t["id"] == "HAR")
    assert after["payroll"] == pytest.approx(before["payroll"] + 2, abs=0.11)
    assert json.loads(get_roster("HAR", "S"))["players"][0]["salary"] == pytest.approx(player["salary"] + 2)


def test_database_rejects_bad_rows(scratch_db):
    db = league_db.connect()
    with pytest.raises(sqlite3.IntegrityError):  # a contract for a player who does not exist
        db.execute("INSERT INTO contracts VALUES ('NOBODY', 1.0, 1)")
    with pytest.raises(sqlite3.IntegrityError):  # ratings run from 25 to 99
        db.execute("UPDATE ratings SET value = 100 WHERE rowid = 1")
    with pytest.raises(sqlite3.IntegrityError):  # a player on a team that does not exist
        db.execute("UPDATE players SET team_id = 'XYZ' WHERE id = 'HAR-01'")
    db.close()


def test_parallel_first_calls_build_the_database_once(tmp_path, monkeypatch):
    """The server runs tool calls in parallel; a missing database once made one of them crash."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(league_db, "DB_FILE", tmp_path / "league.db")
    with ThreadPoolExecutor(max_workers=8) as pool:
        leagues = list(pool.map(lambda _: league_db.load_league(), range(8)))
    assert all(len(league["players"]) == 288 for league in leagues)
    assert not (tmp_path / "league.db.tmp").exists()
