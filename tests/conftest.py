"""Shared fixtures. No API key needed."""

import pytest

from agents import league_db


@pytest.fixture
def scratch_db(tmp_path, monkeypatch):
    """A fresh database built from the seed, used in place of data/league.db."""
    db_file = tmp_path / "league.db"
    monkeypatch.setattr(league_db, "DB_FILE", db_file)
    league_db.build()
    return db_file


@pytest.fixture(autouse=True)
def no_loaded_save_for_scripts(monkeypatch):
    """Loading a save tells the skills' scripts which league to read (task 4.4); undo
    that after each test, so no test leaves a scratch save behind for the next."""
    monkeypatch.delenv(league_db.DB_ENV, raising=False)
