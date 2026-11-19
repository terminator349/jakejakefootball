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


def test_injuries_and_depth_chart_are_tables(scratch_db):
    db = league_db.connect()
    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"injuries", "depth_chart"} <= tables
    assert db.execute("SELECT COUNT(*) FROM injuries").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM depth_chart").fetchone()[0] == 0
    db.close()


def test_depth_chart_order_is_empty_with_no_custom_order(scratch_db):
    db = league_db.connect()
    assert league_db.depth_chart_order(db, "HAR") == {}
    db.close()


def test_write_depth_chart_then_read_it_back(scratch_db):
    db = league_db.connect()
    roster = [row["id"] for row in db.execute("SELECT id FROM players WHERE team_id = 'HAR' AND position = 'S'")]
    db.close()
    new_order = list(reversed(roster))
    league_db.write_depth_chart("HAR", "S", new_order)
    db = league_db.connect()
    assert league_db.depth_chart_order(db, "HAR") == {"S": new_order}
    db.close()


def test_save_injury_then_read_current_injuries(scratch_db):
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = 3")
        league_db.save_injury(db, "HAR-01", "HAR", since_week=2, games_out=1, description="Hamstring.")
    assert league_db.injured_player_ids(db, "HAR", week=3) == {"HAR-01"}
    assert league_db.injured_player_ids(db, "HAR", week=4) == set()  # back the week after
    db.close()

    injuries = league_db.current_injuries("HAR")
    assert len(injuries) == 1 and injuries[0]["games_remaining"] == 1
    assert league_db.current_injuries("MES") == []
    assert {i["player_id"] for i in league_db.current_injuries()} == {"HAR-01"}  # no team filter


def test_save_injury_overwrites_the_same_player(scratch_db):
    db = league_db.connect()
    with db:
        league_db.save_injury(db, "HAR-01", "HAR", since_week=1, games_out=1, description="Minor.")
        league_db.save_injury(db, "HAR-01", "HAR", since_week=1, games_out=6, description="Re-injured, worse.")
    db.close()
    injuries = league_db.current_injuries("HAR")
    assert len(injuries) == 1 and injuries[0]["description"] == "Re-injured, worse."


def test_parallel_first_calls_build_the_database_once(tmp_path, monkeypatch):
    """The server runs tool calls in parallel; a missing database once made one of them crash."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(league_db, "DB_FILE", tmp_path / "league.db")
    with ThreadPoolExecutor(max_workers=8) as pool:
        leagues = list(pool.map(lambda _: league_db.load_league(), range(8)))
    assert all(len(league["players"]) == 288 for league in leagues)
    assert not (tmp_path / "league.db.tmp").exists()


@pytest.mark.parametrize("dropped", [
    "DROP TABLE gm_proposals; DROP TABLE orders; DROP TABLE injuries; DROP TABLE depth_chart;",  # 2.1's version 5
    "DROP TABLE gm_proposals; DROP TABLE orders; DROP TABLE trade_proposals;",                   # 3.2's version 5
])
def test_either_branchs_version_5_saves_come_up_to_date(tmp_path, dropped):
    """Version 5 meant the Trade Desk on one branch and injuries on the other."""
    path = tmp_path / "v5.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:
        db.executescript(dropped + " PRAGMA user_version = 5;")
    db.close()
    league_db.connect(path).close()
    with sqlite3.connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION == 8
    db.close()
    assert {"trade_proposals", "orders", "gm_proposals", "injuries", "depth_chart"} <= tables
