"""Checks for the test bench's API (ui/server.py). No API key needed; every test
uses scratch databases and a scratch saves folder."""

import pytest
from starlette.testclient import TestClient

from agents import league_db, saves
from ui.server import app


@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)  # "default league" = the scratch database
    return TestClient(app)


def test_page_and_status(client):
    assert "Front Office" in client.get("/").text
    status = client.get("/api/status").json()
    assert (status["save"], status["week"], status["our_team"], status["trade_deadline_week"]) == (None, 1, "HAR", 9)


def test_league_views(client):
    assert len(client.get("/api/teams").json()["teams"]) == 6
    assert {p["position"] for p in client.get("/api/roster?team=HAR&position=S").json()["players"]} == {"S"}
    assert client.get("/api/compare?team=HAR").json()["comparisons"][0]["rating"] == "coverage"
    assert client.get("/api/rules").json()["cap_type"] == "hard"


def test_play_a_week(client):
    season = client.get("/api/season").json()
    assert len(season["games"]) == 3
    assert client.post("/api/season/advance", json={}).status_code == 400  # games not played yet
    played = client.post("/api/season/sim", json={}).json()["played"]
    assert len(played) == 3
    assert client.post("/api/season/advance", json={}).json() == {"week": 2}
    box = client.get(f"/api/game?id={played[0]['game_id']}").json()
    assert box["simulated"] and box["plays"][-1]["home_score"] == played[0]["home_score"]
    standings = client.get("/api/season").json()["standings"]
    assert sum(r["wins"] + r["losses"] + r["ties"] for r in standings) == 6


def test_record_one_result(client):
    game = client.get("/api/season").json()["games"][0]
    assert client.post("/api/season/result", json={"game_id": game["id"], "home_score": 21,
                                                    "away_score": 14}).json() == {"ok": True}
    again = client.post("/api/season/result", json={"game_id": game["id"], "home_score": 0, "away_score": 0})
    assert again.status_code == 400 and "already been played" in again.json()["error"]


def test_trades_check_make_and_log(client):
    trade = {"team_a": "HAR", "a_sends": ["HAR-46"], "team_b": "SUM", "b_sends": ["SUM-45"]}
    assert client.post("/api/trade/check", json=trade).json()["legal"] is True
    made = client.post("/api/trade/make", json=trade).json()
    assert made["move_id"] == 1
    assert len(client.get("/api/moves").json()["moves"]) == 1

    refused = client.post("/api/trade/make", json={"team_a": "HAR", "a_sends": ["HAR-45"],
                                                   "team_b": "LAK", "b_sends": ["LAK-43"]})
    assert refused.status_code == 400
    assert [v["rule"] for v in refused.json()["violations"]] == ["hard_cap"]


def test_new_game_loads_it(client, monkeypatch):
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)  # put the active league back afterwards
    assert client.post("/api/saves/new", json={"name": "bench", "seed": "3"}).json() == {"loaded": "bench"}
    assert client.get("/api/status").json()["save"] == "bench"
    assert [s["name"] for s in client.get("/api/saves").json()["saves"]] == ["bench"]
    assert client.post("/api/saves/new", json={"name": "bench"}).status_code == 400  # no overwrite by default
    assert client.post("/api/league/rebuild", json={}).status_code == 400  # only the default league
    client.post("/api/league/default", json={})
    assert client.get("/api/status").json()["save"] is None


def test_league_office_over_stdio(client):
    tools = client.get("/api/mcp/tools").json()["tools"]
    assert {t["name"] for t in tools} >= {"list_teams", "check_trade"}
    result = client.post("/api/mcp/call", json={"tool": "get_roster",
                                                 "arguments": {"team_id": "HAR", "position": "K"}}).json()
    assert result["is_error"] is False and result["json"]["team_id"] == "HAR"


def test_agent_needs_a_key(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    response = client.post("/api/agent/analytics", json={"question": "Where are we weakest?"})
    assert response.status_code == 400 and "OPENROUTER_API_KEY" in response.json()["error"]
