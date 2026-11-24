"""Checks for the playoffs and the end of the season (task G6). No API key needed.

The regular season is filled in with record_result (the home team wins 24-17) so
the tests are quick; the playoff games themselves are simulated.
"""

import sqlite3

import pytest
from starlette.testclient import TestClient

from agents import game_loop, league_db, orders, playoffs, saves, season
from agents import trade_desk as desk
from agents.simulator import MAX_OVERTIMES, Game, _elapsed, drives
from ui.server import app


def finish_regular_season() -> None:
    while season.current_week() <= 17:
        for game in season.games(season.current_week()):
            season.record_result(game["id"], 24, 17)
        season.advance_week()


def lineups():
    db = league_db.connect()
    try:
        return season._lineup(db, "HAR", 18), season._lineup(db, "SUM", 18)
    finally:
        db.close()


# ---- Overtime: a playoff game always has a winner --------------------------------------------

def test_playoff_games_never_end_in_a_tie(scratch_db):
    home, away = lineups()
    periods = []
    for i in range(150):
        game = Game(home, away, seed=f"ot-{i}", playoff=True)
        while not game.over:
            game.step()
        assert game.score["HAR"] != game.score["SUM"]
        periods.append(game.quarter)
    assert any(q >= 5 for q in periods)  # some went to overtime, and were settled there


def test_more_than_one_overtime_keeps_time_in_order(scratch_db):
    home, away = lineups()
    for i in range(400):
        game = Game(home, away, seed=f"ot-{i}", playoff=True)
        while not game.over:
            game.step()
        if game.quarter >= 6:
            break
    else:
        pytest.skip("no double overtime in these seeds")
    assert game.quarter <= 4 + MAX_OVERTIMES and game.score["HAR"] != game.score["SUM"]
    times = [_elapsed(p["quarter"], p["clock"]) for p in game.plays]
    assert times == sorted(times)  # the second overtime comes after the first
    assert drives(game.plays)[-1]["quarter"] == game.quarter


def test_a_tie_after_every_overtime_goes_to_the_better_seed():
    seeded = ["IRN", "HAR", "SUM", "LAK"]
    tied = {"home_team_id": "SUM", "away_team_id": "HAR", "home_score": 20, "away_score": 20}
    assert season.winner(tied, seeded) == "HAR"
    assert season.winner({**tied, "away_score": 17}, seeded) == "SUM"
    assert season.winner({**tied, "home_score": None, "away_score": None}, seeded) is None


# ---- The bracket ---------------------------------------------------------------------------

def test_no_bracket_in_the_regular_season(scratch_db):
    assert playoffs.bracket() is None


def test_the_bracket_through_the_final(scratch_db):
    finish_regular_season()
    b = playoffs.bracket()
    seeded = season.seeds()
    assert b["round_now"] == "Semifinals" and [s["team_id"] for s in b["seeds"]] == seeded
    assert [s["seed"] for s in b["seeds"]] == [1, 2, 3, 4]
    semis = b["rounds"][0]["games"]
    assert [(g["home"]["seed"], g["away"]["seed"]) for g in semis] == [(1, 4), (2, 3)]
    assert b["rounds"][1]["games"] == [] and b["champion"] is None

    season.play_week()
    season.advance_week()
    b = playoffs.bracket()
    assert b["round_now"] == "Final"
    winners = [g["winner"] for g in b["rounds"][0]["games"]]
    [final] = b["rounds"][1]["games"]
    assert {final["home"]["team_id"], final["away"]["team_id"]} == set(winners)
    assert final["home"]["seed"] < final["away"]["seed"]  # the better seed at home

    season.play_week()
    season.advance_week()
    b = playoffs.bracket()
    assert b["round_now"] is None and b["champion"]["team_id"] == b["rounds"][1]["games"][0]["winner"]
    assert b["our_result"] is not None


@pytest.mark.parametrize("seeds, games, champion, expected", [
    (["IRN", "SUM", "LAK", "DEL"], [], None, "missed the playoffs"),
    (["HAR", "SUM", "LAK", "DEL"], [("Semifinals", "HAR", "DEL", None)], None, None),
    (["HAR", "SUM", "LAK", "DEL"], [("Semifinals", "HAR", "DEL", "DEL")], None, "lost in the semifinals to Delta Bay"),
    (["HAR", "SUM", "LAK", "DEL"], [("Semifinals", "HAR", "DEL", "HAR"), ("Final", "HAR", "SUM", "SUM")], "SUM",
     "lost in the final to Summit"),
    (["HAR", "SUM", "LAK", "DEL"], [("Semifinals", "HAR", "DEL", "HAR"), ("Final", "HAR", "SUM", "HAR")], "HAR",
     "won the championship"),
])
def test_how_far_we_went(seeds, games, champion, expected):
    city = {"HAR": "Harbor City", "SUM": "Summit", "LAK": "Lakeshore", "DEL": "Delta Bay", "IRN": "Iron Falls"}

    def side(t):
        return {"team_id": t, "city": city[t]}
    rounds = [{"name": name, "games": [{"home": side(h), "away": side(a), "winner": w}
                                       for n, h, a, w in games if n == name]} for name in season.PLAYOFF_ROUNDS]
    b = {"we_made_it": "HAR" in seeds, "rounds": rounds, "champion": champion and side(champion)}
    assert playoffs.our_result(b) == expected


# ---- The season summary -----------------------------------------------------------------------

def test_the_season_summary(scratch_db):
    # A trade, an order to the GM, and an offer we turned down during the season.
    pid = desk.propose("HAR", ["HAR-46", "HAR-41"], "SUM", ["SUM-45"])["proposal"]["id"]
    desk.respond(pid, "SUM", "accept")
    terms = orders.OrderTerms(summary="Upgrade CB.", wants_trades=True, positions=["CB"], max_incoming_salary=None,
                              max_added_payroll=None, protected_player_ids=[])
    orders.save_order("Upgrade CB.", orders.ground_terms(terms, league_db.load_league()))
    offer = desk.propose("LAK", ["LAK-47"], "HAR", ["HAR-47"])["proposal"]["id"]
    desk.respond(offer, "HAR", "reject")

    finish_regular_season()
    for _ in season.PLAYOFF_ROUNDS:
        season.play_week()
        season.advance_week()
    s = playoffs.summary()
    assert s["team"] == "Harbor City Herons" and s["record"].count("-") >= 1
    assert s["standing"].endswith("of 6") and s["playoffs"] in (
        "missed the playoffs", "won the championship") or s["playoffs"].startswith("lost in the")
    assert s["trades"] == ["Week 1: Isaiah Odom (S) from Summit for Hunter Dubois (S) and Bryce Strickland (CB)"]
    assert s["orders_given"] == 1 and s["offers_to_us"]["rejected"] == 1
    assert s["cap"] == {"payroll": 251.86, "cap_space": 3.14, "hard_cap": 255.0, "roster": 47, "under_the_cap": True}
    # Only the playoff games were simulated, so the leaders' stats come from them, if we played.
    assert all(l["total"] > 0 for l in s["leaders"])


def test_the_overview_through_the_playoffs(scratch_db):
    finish_regular_season()
    week = game_loop.overview()
    assert week["playoff_round"] == "Semifinals" and week["regular_season_over"] and not week["season_over"]
    note = next(n for n in week["notes"] if n.startswith("The playoffs"))
    assert ("seed" in note) == ("HAR" in season.seeds())
    for _ in season.PLAYOFF_ROUNDS:
        game_loop.play_week()
        season.advance_week()
    week = game_loop.overview()
    assert week["season_over"] and any(n.startswith("The season is over") for n in week["notes"])


# ---- Saves from before G6 -----------------------------------------------------------------------

def test_older_saves_leave_the_playoffs_out_of_the_standings(tmp_path):
    path = tmp_path / "v7.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:  # put back the old view, which counted every game
        db.executescript("""DROP VIEW standings;
            CREATE VIEW standings AS SELECT t.id AS team_id, 0 AS wins, 0 AS losses, 0 AS ties,
                0 AS points_for, 0 AS points_against FROM teams t; PRAGMA user_version = 7;""")
    db.close()
    league_db.connect(path).close()
    with sqlite3.connect(path) as db:
        view = db.execute("SELECT sql FROM sqlite_master WHERE name = 'standings'").fetchone()[0]
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()
    assert "season_games" in view


# ---- In the game -----------------------------------------------------------------------------

@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_the_playoffs_in_the_game(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client.post("/api/saves/new", json={"name": "playoffs", "seed": "3"})
    hub = client.get("/api/hub").json()
    assert hub["playoffs"] is None and hub["summary"] is None and hub["playoff_round"] is None

    finish_regular_season()
    hub = client.get("/api/hub").json()
    assert hub["playoff_round"] == "Semifinals" and len(hub["playoffs"]["rounds"][0]["games"]) == 2
    assert hub["briefing"] is None and hub["deadline"] is None
    played = client.post("/api/hub/play", json={}).json()["played"]
    assert len(played) == 2 and all(g["home_score"] != g["away_score"] for g in played)
    assert client.post("/api/hub/advance", json={}).json()["week"] == 19
    assert len(client.post("/api/hub/play", json={}).json()["played"]) == 1
    assert client.post("/api/hub/advance", json={}).json()["week"] == 20

    hub = client.get("/api/hub").json()
    assert hub["season_over"] and hub["summary"]["playoffs"] and hub["playoffs"]["champion"]
    assert client.get("/api/status").json()["season_over"] is True
    assert "season is over" in client.post("/api/hub/play", json={}).json()["error"]
    page = client.get("/").text
    assert "Season summary" in page and "Playoff bracket" in page
