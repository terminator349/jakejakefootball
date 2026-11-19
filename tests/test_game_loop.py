"""Checks for the game loop (task G2): the week as the owner sees it. No API key
needed; every test uses a scratch database."""

from agents import game_loop, season


def test_week_one_before_the_games(scratch_db):
    week = game_loop.overview()
    assert (week["week"], week["season_over"], week["week_played"], week["last_week"]) == (1, False, False, None)
    team = week["team"]
    assert (team["id"], team["record"], team["cap_space"], team["roster_size"]) == ("HAR", "0-0", 5.5, 48)
    game = week["this_week"]
    assert game["week"] == 1 and not game["played"] and game["opponent"]["id"] != "HAR"
    notes = " ".join(week["notes"])
    assert "Weakest spot: safety coverage, 6th of 6" in notes
    assert "Trade deadline after week 9" in notes and "$5.5M" in notes


def test_play_the_week_then_move_on(scratch_db):
    before = game_loop.overview()["this_week"]
    played = game_loop.play_week()
    assert played["our_game_id"] == before["game_id"] and len(played["played"]) == 3
    after = game_loop.overview()
    game = after["this_week"]
    assert after["week_played"] and game["played"]
    assert game["outcome"] == ("win" if game["our_score"] > game["their_score"]
                               else "loss" if game["our_score"] < game["their_score"] else "tie")
    assert after["team"]["record"] in ("1-0", "0-1", "0-0-1")
    assert game_loop.play_week()["played"] == []  # nothing left to play

    season.advance_week()
    week2 = game_loop.overview()
    assert week2["week"] == 2 and not week2["week_played"]
    assert week2["last_week"]["game_id"] == game["game_id"]
    assert week2["notes"][0].startswith("Last week: ")


def test_the_regular_season_ends_after_week_17_then_the_playoffs(scratch_db):
    for _ in range(17):
        game_loop.play_week()
        season.advance_week()
    week = game_loop.overview()
    assert week["regular_season_over"] and not week["season_over"] and week["deadline_passed"]
    assert week["playoff_round"] == "Semifinals"
    assert sum(int(n) for n in week["team"]["record"].split("-")) == 17
    assert any(note.startswith("The playoffs, the semifinals") for note in week["notes"])
    in_it = "HAR" in season.seeds()
    assert (week["this_week"] is not None) == in_it  # our semifinal, if we made it

    for _ in range(2):
        game_loop.play_week()
        season.advance_week()
    week = game_loop.overview()
    assert week["season_over"] and week["this_week"] is None and week["playoff_round"] is None
    assert any(note.startswith("The season is over:") for note in week["notes"])
    assert sum(int(n) for n in week["team"]["record"].split("-")) == 17  # the playoffs don't count


def test_our_schedule(scratch_db):
    games = game_loop.our_schedule()
    assert [g["week"] for g in games] == list(range(1, 18))
    assert sum(g["home"] for g in games) in (8, 9)
    assert {g["opponent"]["id"] for g in games} == {"MES", "IRN", "LAK", "SUM", "DEL"}
