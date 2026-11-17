"""Checks for calling the plays (task G8). No API key needed; every test uses a
scratch database."""

import json

import pytest

from agents import game_loop, league_db, live, season
from agents.simulator import Situation


def sit(offense="HAR", quarter=1, clock=600, down=1, yardline=50, lead=0):
    defense = "MES" if offense == "HAR" else "HAR"
    return Situation(quarter, clock, offense, defense, down, 10, yardline, {offense: 10 + lead, defense: 10},
                     {offense: 3, defense: 3})


def test_key_moments():
    assert not live.key_moment(sit(), "HAR")                              # a 1st down at midfield
    assert live.key_moment(sit(down=4), "HAR")                            # our 4th down
    assert live.key_moment(sit(yardline=85), "HAR")                       # our red zone
    assert live.key_moment(sit(quarter=2, clock=100), "HAR")              # our two-minute drill
    assert live.key_moment(sit(quarter=5), "HAR")                         # overtime
    assert not live.key_moment(sit(offense="MES", down=4), "HAR")         # their 4th down: they kick
    assert live.key_moment(sit(offense="MES", yardline=85), "HAR")        # they're in our red zone
    assert live.key_moment(sit(offense="MES", quarter=4, clock=90, lead=-3), "HAR")   # a close finish
    assert not live.key_moment(sit(offense="MES", quarter=4, clock=90, lead=-20), "HAR")


def play_out(first, pick):
    """Call a whole game with pick(view) -> call; return every view along the way."""
    views = [first]
    while not views[-1]["over"]:
        views.append(live.call(first["game_id"], pick(views[-1])))
    return views


def simple(view):
    if view["side"] == "defense":
        return "base"
    return "punt" if view["situation"]["down"] == 4 else "pass_short"


def test_call_a_game_at_key_moments(scratch_db):
    first = live.start("key")
    assert first["team"] == "HAR" and first["level"] == "key"
    assert game_loop.overview()["live"] == {"game_id": first["game_id"], "level": "key"}
    views = play_out(first, simple)
    assert len(views) > 10
    for view in views[:-1]:
        assert live.key_moment(Situation(**{k: view["situation"][k] for k in
                                            ("quarter", "clock", "offense", "defense", "down", "distance", "yardline")},
                                         score=view["score"], timeouts=view["situation"]["timeouts"]), "HAR")
    final = views[-1]
    # Saved like any simulated game, the rest of the week played, and the live game gone.
    week = season.games(1)
    assert all(g["home_score"] is not None for g in week)
    ours = next(g for g in week if g["id"] == final["game_id"])
    assert (ours["home_score"], ours["away_score"]) == (final["score"][ours["home_team_id"]],
                                                        final["score"][ours["away_team_id"]])
    box = season.box_score(final["game_id"])
    assert len(box["plays"]) == len(final["plays"])
    assert live.current() is None and game_loop.overview()["live"] is None
    called = [p for p in box["plays"] if p["offense_team_id"] == "HAR" and p["call"] == "pass_short"]
    assert called  # our calls are in the play log


def test_every_snap_hands_over_every_snap(scratch_db):
    view = live.start("every")
    for _ in range(40):
        before = len(view["plays"])
        view = live.call(view["game_id"], simple(view))
        # Between our calls the AI only runs plays where a defensive call does nothing.
        for play in view["plays"][before + 1:]:
            assert play["offense"] != "HAR" and play["call"] in ("punt", "field_goal", "kneel", "spike")


def test_a_game_in_progress_survives_a_restart(scratch_db):
    view = live.start("key")
    for _ in range(5):
        view = live.call(view["game_id"], simple(view))
    again = live.state(view["game_id"])  # rebuilt from the seed and the stored calls
    assert again["plays"] == view["plays"] and again["situation"] == view["situation"]
    assert again["score"] == view["score"]


def test_same_calls_same_game(tmp_path, monkeypatch):
    finals = []
    for name in ("a", "b"):
        monkeypatch.setattr(league_db, "DB_FILE", tmp_path / f"{name}.db")
        league_db.build(season_seed=7)
        finals.append(play_out(live.start("key"), simple)[-1]["plays"])
    assert finals[0] == finals[1]


def test_bad_calls_change_nothing(scratch_db):
    view = live.start("every")
    stored = lambda: json.loads(league_db.connect().execute("SELECT inputs FROM live_games").fetchone()[0])
    inputs = stored()
    with pytest.raises(ValueError):
        live.call(view["game_id"], "hail_mary")
    with pytest.raises(ValueError, match="Unknown level"):
        live.set_level(view["game_id"], "sometimes")
    assert stored() == inputs
    with pytest.raises(ValueError, match="already being called"):
        live.start("key")


def test_sim_the_rest_and_switch_levels(scratch_db):
    view = live.start("every")
    view = live.set_level(view["game_id"], "key")
    assert view["level"] == "key" and not view["over"]
    with pytest.raises(ValueError, match="being called"):
        game_loop.play_week()  # Sim it would throw the called game away
    final = live.sim_rest(view["game_id"])
    assert final["over"] and live.current() is None
    with pytest.raises(ValueError, match="already been played"):
        live.start("key")


def test_offense_options_show_matchups(scratch_db):
    view = live.start("every")
    while view["side"] != "offense":
        view = live.call(view["game_id"], "base")
    calls = [o["call"] for o in view["options"]]
    assert calls[:6] == ["run_inside", "run_outside", "pass_short", "pass_deep", "play_action", "screen"]
    assert {"punt", "field_goal", "kneel", "spike"} <= set(calls)
    assert all(isinstance(o["edge"], float) for o in view["options"][:6])
