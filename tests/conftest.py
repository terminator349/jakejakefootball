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
