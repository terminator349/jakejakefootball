"""Checks for the real league (task 4.4): data/league_real.json, the builder's rules,
and starting a game with real players. No API key and no download needed: the
builder's raw nflverse files are not in the repository, so its functions are
checked on small made-up players, and its output on the committed league_real.json."""

import importlib.util
import json
import statistics
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from agents import league_db, saves, tools

DATA_DIR = Path(__file__).parent.parent / "data"
REAL = json.loads((DATA_DIR / "league_real.json").read_text())
GENERATED = json.loads((DATA_DIR / "league.json").read_text())

sys.path.insert(0, str(DATA_DIR))  # real_league imports generate_league beside it
import generate_league as gen  # noqa: E402
import real_league  # noqa: E402


@pytest.fixture
def saves_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)  # load_game changes it; put it back after
    return tmp_path / "saves"


def _team(team_id: str) -> list[dict]:
    return [p for p in REAL["players"] if p["team_id"] == team_id]


# ---- The committed league -----------------------------------------------------------

def test_the_real_league_has_the_generated_leagues_shape():
    assert REAL["league"] == "real" and REAL["our_team"] == "HAR"
    assert REAL["rules"] == GENERATED["rules"] and REAL["teams"] == GENERATED["teams"]
    assert len({p["id"] for p in REAL["players"]}) == len(REAL["players"]) == 288
    for team in REAL["teams"]:
        roster = _team(team["id"])
        assert {pos: sum(p["position"] == pos for p in roster) for pos in gen.ROSTER_COUNTS} == gen.ROSTER_COUNTS
        assert all(p["id"].startswith(team["id"] + "-") for p in roster)


def test_every_player_is_rated_on_his_positions_skills():
    for p in REAL["players"]:
        assert list(p["ratings"]) == gen.POSITION_RATINGS[p["position"]]
        assert all(25 <= v <= 99 for v in p["ratings"].values())
        assert p["overall"] == round(sum(p["ratings"].values()) / len(p["ratings"]))
        assert 20 <= p["age"] <= 45 and 0 <= p["games_missed_last_season"] <= 17
        assert 1 <= p["contract_years"] <= 5 and p["salary"] >= gen.MIN_SALARY
        assert p["nfl_team"]


def test_real_stars_are_where_they_should_be():
    """Ratings come from real stats, so the league's best players are real stars."""
    def best(position, skill):
        return max((p for p in REAL["players"] if p["position"] == position), key=lambda p: p["ratings"][skill])["name"]
    names = {p["name"] for p in REAL["players"]}
    assert {"Josh Allen", "Myles Garrett", "Ja'Marr Chase", "Bijan Robinson"} <= names
    assert best("DL", "pass_rush") == "Myles Garrett"


def test_payrolls_match_the_generated_league_so_the_herons_have_5_5m():
    cap = REAL["rules"]["salary_cap"]
    for team in REAL["teams"]:
        real = sum(p["salary"] for p in _team(team["id"]))
        generated = sum(p["salary"] for p in GENERATED["players"] if p["team_id"] == team["id"])
        assert real == pytest.approx(generated, abs=0.1) and real <= cap
    assert cap - sum(p["salary"] for p in _team("HAR")) == pytest.approx(5.5, abs=0.1)


def test_the_teams_come_out_even():
    averages = [statistics.fmean(p["overall"] for p in _team(t["id"])) for t in REAL["teams"]]
    assert max(averages) - min(averages) < 2


def test_the_herons_have_the_weakest_secondary_coverage(tmp_path):
    db = tmp_path / "real.db"
    league_db.build(db, league="real")
    league_db_file, league_db.DB_FILE = league_db.DB_FILE, db
    try:
        rows = json.loads(tools.compare_to_league("HAR"))["comparisons"]
    finally:
        league_db.DB_FILE = league_db_file
    coverage = {r["position"]: r for r in rows if r["rating"] == "coverage" and r["position"] in ("CB", "S")}
    assert coverage["CB"]["rank"] == coverage["S"]["rank"] == 6


# ---- The builder's rules, on made-up players ------------------------------------------

def test_ranks_are_given_the_scales_values():
    assert real_league.on_scale([0.3, -1.0, 2.0], [60, 90, 75]) == [75, 60, 90]
    assert real_league.on_scale([5.0], [60, 70, 80]) == [70]  # one player gets the middle


def test_rate_stats_on_few_attempts_count_for_less():
    def stat(p):
        return p["value"], p["n"]
    stat.k = 10
    pool = [{"value": 1.0, "n": 90}, {"value": 0.0, "n": 10}, {"value": None, "n": 0}]
    column = real_league.stat_column(pool, stat)
    prior = (1.0 * 90 + 0.0 * 10) / 100
    assert column[0] == pytest.approx((90 + prior * 10) / 100)
    assert column[1] == pytest.approx(prior * 10 / 20)   # ten attempts: halfway to the average
    assert column[2] == pytest.approx(prior)              # no attempts: the average


def _fake(position, i, coverage=None):
    ratings = {k: 60 + i for k in gen.POSITION_RATINGS[position]}
    if coverage is not None:
        ratings["coverage"] = coverage
    return {"name": f"{position} {i}", "position": position, "ratings": ratings,
            "overall": round(sum(ratings.values()) / len(ratings))}


def test_the_split_deals_even_rosters_and_the_herons_the_worst_coverage():
    chosen = {pos: [_fake(pos, i, coverage=90 - i if pos in ("CB", "S") else None)
                    for i in range(6 * count)] for pos, count in gen.ROSTER_COUNTS.items()}
    rosters = real_league.split(chosen)
    for team, roster in rosters.items():
        assert {pos: sum(p["position"] == pos for p in roster) for pos in gen.ROSTER_COUNTS} == gen.ROSTER_COUNTS
    starters = gen.STARTERS["CB"] * 6
    ranked = sorted(chosen["CB"], key=lambda p: -p["overall"])[:starters]
    worst = sorted(ranked, key=lambda p: p["ratings"]["coverage"])[:gen.STARTERS["CB"]]
    assert all(p in rosters["HAR"] for p in worst)


def test_young_players_are_on_rookie_deals_by_draft_position():
    import random
    rng = random.Random(1)
    star = {"position": "QB", "overall": 90, "rookie_year": 2024, "draft_number": 1}
    late = {"position": "QB", "overall": 90, "rookie_year": 2024, "draft_number": 200}
    veteran = {"position": "QB", "overall": 90, "rookie_year": 2015, "draft_number": 1}
    assert real_league.contract(star, rng) == (3.0, 3)
    assert real_league.contract(late, rng)[0] == 0.5
    assert real_league.contract(veteran, rng)[0] == pytest.approx(gen.TOP_SALARY["QB"])


def test_every_rating_says_where_it_comes_from():
    assert {pos: set(skills) for pos, skills in real_league.RATING_SOURCES.items()} == \
        {pos: set(skills) for pos, skills in gen.POSITION_RATINGS.items()}
    assert {pos: set(skills) for pos, skills in real_league.SKILLS.items()} == \
        {pos: set(skills) for pos, skills in gen.POSITION_RATINGS.items()}


# ---- Playing it -----------------------------------------------------------------------

def test_a_database_knows_which_league_it_was_started_from(tmp_path):
    league_db.build(tmp_path / "gen.db")
    league_db.build(tmp_path / "real.db", league="real")
    assert league_db.league_kind(tmp_path / "gen.db") == "generated"
    assert league_db.league_kind(tmp_path / "real.db") == "real"
    names = {p["name"] for p in league_db.load_league(tmp_path / "real.db")["players"]}
    assert "Josh Allen" in names
    with pytest.raises(ValueError):
        league_db.build(tmp_path / "x.db", league="madeup")


def test_a_save_from_before_4_4_is_the_generated_league(tmp_path):
    db = tmp_path / "old.db"
    league_db.build(db)
    conn = league_db.connect(db)
    with conn:
        conn.execute("DELETE FROM settings WHERE key = 'league'")
    conn.close()
    assert league_db.league_kind(db) == "generated"


def test_new_game_with_real_players(saves_dir):
    saves.new_game("realdeal", season_seed=4, league="real")
    saves.new_game("madeup", season_seed=4)
    by_name = {s["name"]: s["league"] for s in saves.list_saves()}
    assert by_name == {"realdeal": "real", "madeup": "generated"}
    with pytest.raises(ValueError):
        saves.new_game("nope", league="nfl")


def test_the_valuation_script_prices_on_the_loaded_league(saves_dir, monkeypatch):
    path = Path(__file__).parent.parent / "skills" / "player-valuation" / "scripts" / "value_player.py"
    spec = importlib.util.spec_from_file_location("value_player_real", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.players_in_play() is None  # nothing loaded: the generated seed

    saves.new_game("realdeal", season_seed=4, league="real")
    saves.load_game("realdeal")
    in_play = script.players_in_play()
    assert len(in_play) == 288
    assert sorted(p["salary"] for p in in_play) == sorted(p["salary"] for p in REAL["players"])
    saves.use_default()
    assert script.players_in_play() is None


def test_the_game_page_starts_a_real_players_game(scratch_db, tmp_path, monkeypatch):
    from ui.server import app
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    client = TestClient(app)
    assert client.post("/api/saves/new", json={"name": "real", "seed": "2", "league": "real"}).json() == {"loaded": "real"}
    hub = client.get("/api/hub").json()
    assert hub["league"] == "real" and hub["league_name"] == "Real 2025 players"
    assert client.get("/api/saves").json()["saves"][0]["league"] == "real"
    assert client.post("/api/saves/new", json={"name": "bad", "league": "nfl"}).status_code == 400
    client.post("/api/league/default", json={})
