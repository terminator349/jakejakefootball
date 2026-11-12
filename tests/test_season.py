"""Checks for the season: schedule, current week, results and standings (task G1).
No API key needed; every test uses a scratch database (conftest.py)."""

import sqlite3
from collections import Counter

import pytest

from agents import league_db, season

TEAMS = ["HAR", "MES", "IRN", "LAK", "SUM", "DEL"]


def play_week(scores=(24, 17)) -> None:
    for game in season.games(season.current_week()):
        season.record_result(game["id"], *scores)
    season.advance_week()


@pytest.mark.parametrize("seed", range(200))
def test_schedule_is_fair(seed):
    schedule = season.make_schedule(TEAMS, 17, seed)
    assert len(schedule) == 51  # 3 games a week

    for week in range(1, 18):
        playing = [team for w, home, away in schedule if w == week for team in (home, away)]
        assert sorted(playing) == sorted(TEAMS)  # everyone plays exactly once a week

    meetings = Counter(frozenset((home, away)) for _, home, away in schedule)
    assert sorted(meetings.values()) == [3] * 9 + [4] * 6  # each rival three or four times
    for team in TEAMS:
        assert sorted(n for pair, n in meetings.items() if team in pair) == [3, 3, 3, 4, 4]

    home_games = Counter(home for _, home, _ in schedule)
    assert all(home_games[team] in (8, 9) for team in TEAMS)
    hosted = Counter((home, away) for _, home, away in schedule)
    assert all(abs(hosted[(a, b)] - hosted[(b, a)]) <= 1 for a in TEAMS for b in TEAMS)

    by_week = {w: {frozenset((h, a)) for x, h, a in schedule if x == w} for w in range(1, 18)}
    assert not any(by_week[w] & by_week[w + 1] for w in range(1, 17))  # no back-to-back rematches


def test_same_seed_same_schedule():
    assert season.make_schedule(TEAMS, 17, 7) == season.make_schedule(TEAMS, 17, 7)
    assert season.make_schedule(TEAMS, 17, 7) != season.make_schedule(TEAMS, 17, 8)


def test_new_league_starts_at_week_1_with_no_results(scratch_db):
    assert season.current_week() == 1
    games = season.games()
    assert len(games) == 51 and all(g["home_score"] is None for g in games)
    assert all(row["wins"] + row["losses"] + row["ties"] == 0 for row in season.standings())


def test_week_moves_on_only_when_every_game_is_played(scratch_db):
    first, *rest = season.games(1)
    season.record_result(first["id"], 21, 14)
    with pytest.raises(ValueError, match="2 game"):
        season.advance_week()
    for game in rest:
        season.record_result(game["id"], 10, 3)
    assert season.advance_week() == 2
    assert season.current_week() == 2


def test_results_only_for_this_weeks_unplayed_games(scratch_db):
    first = season.games(1)[0]
    season.record_result(first["id"], 21, 14)
    with pytest.raises(ValueError, match="already been played"):
        season.record_result(first["id"], 0, 0)
    with pytest.raises(ValueError, match="in week 2"):
        season.record_result(season.games(2)[0]["id"], 7, 3)
    with pytest.raises(ValueError, match="no game"):
        season.record_result(9999, 7, 3)
    with pytest.raises(ValueError, match="negative"):
        season.record_result(season.games(1)[1]["id"], -1, 3)


def test_database_rejects_half_a_score(scratch_db):
    db = league_db.connect()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE games SET home_score = 7 WHERE id = 1")
    db.close()


def test_standings_follow_the_results(scratch_db):
    play_week((24, 17))  # every home team wins week 1
    winners = {g["home_team_id"] for g in season.games(1)}
    table = season.standings()
    assert {row["team_id"] for row in table[:3]} == winners
    assert all((row["wins"], row["losses"], row["point_diff"]) == (1, 0, 7) for row in table[:3])
    assert all((row["wins"], row["losses"], row["point_diff"]) == (0, 1, -7) for row in table[3:])
    assert [row["rank"] for row in table] == [1, 2, 3, 4, 5, 6]


def test_ties_count_as_half_a_win(scratch_db):
    play_week((20, 20))
    table = season.standings()
    assert all((row["ties"], row["win_pct"]) == (1, 0.5) for row in table)


def test_season_ends_after_week_17(scratch_db):
    for _ in range(17):
        play_week()
    assert season.current_week() == 18 and season.season_over()
    assert all(row["wins"] + row["losses"] == 17 for row in season.standings())
    with pytest.raises(ValueError, match="over"):
        season.advance_week()
