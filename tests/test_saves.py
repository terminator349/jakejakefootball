"""Checks for save files (task G1). No API key needed. Saves go to a scratch
folder, never the real saves/."""

import json
import sqlite3

import pytest

from agents import league_db, saves, season
from agents.rules import Trade, make_trade, move_log
from agents.tools import get_roster


@pytest.fixture
def saves_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)  # load_game changes it; put it back after
    return tmp_path / "saves"


def test_new_game_copies_the_seed(saves_dir):
    path = saves.new_game("herons", season_seed=11)
    assert path == saves_dir / "herons.db"
    seed = json.loads(league_db.SEED_FILE.read_text())
    assert league_db.load_league(path) == seed
    assert season.current_week(path) == 1


def test_same_season_seed_same_schedule(saves_dir):
    a = saves.new_game("a", season_seed=11)
    b = saves.new_game("b", season_seed=11)
    c = saves.new_game("c", season_seed=12)
    schedule = lambda path: [(g["week"], g["home_team_id"], g["away_team_id"]) for g in season.games(db_file=path)]
    assert schedule(a) == schedule(b) != schedule(c)


def test_new_game_without_a_seed_picks_one(saves_dir):
    db = league_db.connect(saves.new_game("random"))
    assert isinstance(db.execute("SELECT seed FROM game").fetchone()[0], int)
    db.close()


def test_new_game_will_not_overwrite_a_save(saves_dir):
    path = saves.new_game("herons", season_seed=1)
    make_trade(Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"]), db_file=path)
    with pytest.raises(FileExistsError):
        saves.new_game("herons")
    assert len(move_log(path)) == 1
    saves.new_game("herons", season_seed=1, overwrite=True)
    assert move_log(path) == []


@pytest.mark.parametrize("name", ["", "../escape", "a/b", "with space", "x" * 41, ".hidden"])
def test_save_names_stay_inside_the_saves_folder(saves_dir, name):
    with pytest.raises(ValueError):
        saves.new_game(name)


def test_load_game_points_the_tools_at_the_save(saves_dir):
    path = saves.new_game("herons", season_seed=1)
    make_trade(Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"]), db_file=path)
    assert saves.load_game("herons") == path
    assert "SUM-45" in {p["id"] for p in json.loads(get_roster("HAR", "S"))["players"]}


def test_a_loaded_game_continues_where_it_stopped(saves_dir):
    path = saves.new_game("herons", season_seed=1)
    for game in season.games(1, db_file=path):
        season.record_result(game["id"], 13, 10, db_file=path)
    season.advance_week(db_file=path)

    saves.load_game("herons")
    assert season.current_week() == 2
    assert sum(row["wins"] for row in season.standings()) == 3


def test_load_game_refuses_missing_and_outdated_saves(saves_dir):
    with pytest.raises(FileNotFoundError):
        saves.load_game("nothing")
    path = saves.new_game("old", season_seed=1)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 0")  # as the 1.1 - 1.2 code left databases
    db.close()
    with pytest.raises(league_db.OutdatedDatabase):
        saves.load_game("old")


def test_list_saves_shows_week_and_record(saves_dir):
    assert saves.list_saves() == []  # no saves folder yet
    path = saves.new_game("herons", season_seed=1)
    for game in season.games(1, db_file=path):
        season.record_result(game["id"], 13, 10, db_file=path)
    season.advance_week(db_file=path)

    [entry] = saves.list_saves()
    assert (entry["name"], entry["week"], entry["team_id"], entry["outdated"]) == ("herons", 2, "HAR", False)
    assert entry["wins"] + entry["losses"] + entry["ties"] == 1


def test_default_league_is_rebuilt_when_outdated(tmp_path, monkeypatch):
    """data/league.db is not a save, so an old one is rebuilt instead of refused."""
    default = tmp_path / "league.db"
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", default)
    monkeypatch.setattr(league_db, "DB_FILE", default)
    league_db.build(default)
    with sqlite3.connect(default) as db:
        db.execute("PRAGMA user_version = 0")
    db.close()
    assert season.current_week() == 1
    with sqlite3.connect(default) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()
