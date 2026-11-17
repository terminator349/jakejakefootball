"""Checks for the season simulator (task 3.1). No API key needed.

The engine tests build lineups straight from the league seed. The tuning tests
play a few hundred seeded games and check the averages land where real football
does; the seeds are fixed, so the numbers never change between runs.
"""

import json
import sqlite3
from collections import Counter

import pytest

from agents import league_db, season
from agents.simulator import DEFENSE_CALLS, OFFENSE_PLAYS, Game, build_lineup, soften

SEED = json.loads(league_db.SEED_FILE.read_text())
STARTERS = SEED["rules"]["starters_per_position"]
TEAMS = [t["id"] for t in SEED["teams"]]


def lineups(players=None):
    players = players or SEED["players"]
    return {t: build_lineup(t, [p for p in players if p["team_id"] == t], STARTERS) for t in TEAMS}


LINEUPS = lineups()


def matchups(n: int, prefix: str = "t"):
    """n seeded games covering every pairing, home and away."""
    pairs = [(h, a) for h in TEAMS for a in TEAMS if h != a]
    return [Game(LINEUPS[h], LINEUPS[a], seed=f"{prefix}-{i}").play() for i, (h, a) in
            ((i, pairs[i % len(pairs)]) for i in range(n))]


@pytest.fixture(scope="module")
def sample():
    return matchups(300)


def test_same_seed_same_game():
    a = Game(LINEUPS["HAR"], LINEUPS["MES"], seed=1).play()
    b = Game(LINEUPS["HAR"], LINEUPS["MES"], seed=1).play()
    c = Game(LINEUPS["HAR"], LINEUPS["MES"], seed=2).play()
    assert a.plays == b.plays and a.stats == b.stats
    assert a.plays != c.plays


def test_every_game_finishes_with_a_consistent_log(sample):
    for game in sample:
        last = game.plays[-1]
        assert game.over and game.quarter >= 4
        assert (last["home_score"], last["away_score"]) == (game.score[game.home.team_id],
                                                             game.score[game.away.team_id])
        assert [p["n"] for p in game.plays] == list(range(1, len(game.plays) + 1))
        assert all(0 <= p["clock"] <= 900 and 1 <= p["down"] <= 4 and 1 <= p["yardline"] <= 99 for p in game.plays)


def test_scores_add_up_from_the_plays_and_stats(sample):
    for game in sample:
        for team in game.score:
            lines = [line for line in game.player_stats() if line["team_id"] == team]
            total = lambda stat: sum(line.get(stat, 0) for line in lines)
            touchdowns = sum(1 for p in game.plays if p["result"] == "touchdown" and p["offense"] == team)
            safeties = sum(1 for p in game.plays if p["result"] == "safety" and p["offense"] != team)
            assert game.score[team] == 6 * touchdowns + total("xp_made") + 3 * total("fg_made") + 2 * safeties
            assert total("pass_cmp") == total("rec") and total("pass_yds") == total("rec_yds")
            assert total("pass_td") == total("rec_td")


def test_games_look_like_football(sample):
    """The tuning targets from the roadmap, plus the box-score rates they come from."""
    per_team = lambda f: sum(f(g, t) for g in sample for t in g.score) / (2 * len(sample))
    points = per_team(lambda g, t: g.score[t])
    plays = per_team(lambda g, t: sum(1 for p in g.plays if p["offense"] == t and p["call"] in OFFENSE_PLAYS + ("kneel",)))
    stats = Counter()
    for game in sample:
        for line in game.player_stats():
            stats.update({k: v for k, v in line.items() if isinstance(v, int)})
    assert 20 <= points <= 24
    assert 60 <= plays <= 66
    assert 0.60 <= stats["pass_cmp"] / stats["pass_att"] <= 0.68
    assert 3.8 <= stats["rush_yds"] / stats["rush_att"] <= 4.8
    assert 1.4 <= stats["sacked"] / (2 * len(sample)) <= 2.8
    ties = sum(1 for g in sample if len(set(g.score.values())) == 1)
    assert ties / len(sample) < 0.03


def test_better_teams_win_more_often(sample):
    wins, games = Counter(), Counter()
    for game in sample:
        (a, sa), (b, sb) = game.score.items()
        games.update([a, b])
        if sa != sb:
            wins[a if sa > sb else b] += 1
    rate = {t: wins[t] / games[t] for t in TEAMS}
    strength = {t: sum(LINEUPS[t].units[u] for u in ("inside_run", "short_pass", "deep_pass", "run_defense",
                                                         "short_coverage", "deep_coverage")) for t in TEAMS}
    best, worst = max(strength, key=strength.get), min(strength, key=strength.get)
    assert rate[best] > rate[worst] + 0.15
    assert 0.2 <= rate["HAR"] <= 0.45  # weak, but not hopeless


def test_rivals_attack_our_secondary():
    """In the same situation, every offense throws more against the Herons, the league's
    worst coverage team, than against anyone else. (Over whole games this is partly
    hidden: teams ahead of the Herons run the ball to use up the clock.)"""
    import random
    from agents.simulator import PASSES, Situation, call_offense
    for offense in TEAMS[1:]:
        share = {}
        for defense in (t for t in TEAMS if t != offense):
            sit = Situation(1, 600, offense, defense, 1, 10, 45, {offense: 7, defense: 7}, {offense: 3, defense: 3})
            rng = random.Random(f"{offense}-{defense}")
            calls = [call_offense(sit, LINEUPS[offense], LINEUPS[defense], rng) for _ in range(4000)]
            share[defense] = sum(c in PASSES for c in calls) / len(calls)
        assert max(share, key=share.get) == "HAR", (offense, share)


def test_fixing_the_secondary_helps():
    """Trading for Isaiah Odom (task 1.2's example trade) should win the Herons more games."""
    def har_win_rate(lineup_set):
        wins = 0
        for i in range(400):
            opp = TEAMS[1 + i % 5]
            home, away = (lineup_set["HAR"], lineup_set[opp]) if i % 2 else (lineup_set[opp], lineup_set["HAR"])
            game = Game(home, away, seed=f"odom-{i}").play()
            wins += game.score["HAR"] > game.score[opp]
        return wins / 400
    traded = lineups([dict(p, team_id={"HAR-46": "SUM", "SUM-45": "HAR"}.get(p["id"], p["team_id"]))
                      for p in SEED["players"]])
    assert har_win_rate(traded) > har_win_rate(LINEUPS) + 0.02


def test_called_plays_are_run_as_called():
    game = Game(LINEUPS["HAR"], LINEUPS["MES"], seed=3)
    while game.offense != "HAR" or game.down == 4:
        game.step()
    play = game.step(offense_call="pass_deep", defense_call="cover_2")
    assert (play["offense"], play["call"], play["defense_call"]) == ("HAR", "pass_deep", "cover_2")
    with pytest.raises(ValueError, match="Unknown play"):
        game.step(offense_call="hail_mary")
    with pytest.raises(ValueError, match="Unknown defensive call"):
        game.step(offense_call="run_inside", defense_call="prevent")
    assert set(DEFENSE_CALLS) >= {"blitz", "deep_zone"}
    game.play()
    with pytest.raises(ValueError, match="over"):
        game.step()


def test_soften_caps_mismatches():
    assert soften(0) == 0 and abs(soften(3) - 3) < 0.1
    assert 9 < soften(17) < 10 and soften(100) <= 10 and soften(-17) == -soften(17)


# ---- Saving games to the league database -------------------------------------

def test_play_week_saves_scores_plays_and_stats(scratch_db):
    played = season.play_week()
    assert len(played) == 3
    db = league_db.connect()
    for game in played:
        row = db.execute("SELECT * FROM games WHERE id = ?", (game["game_id"],)).fetchone()
        assert (row["home_score"], row["away_score"]) == (game["home_score"], game["away_score"])
        assert db.execute("SELECT COUNT(*) FROM plays WHERE game_id = ?", (game["game_id"],)).fetchone()[0] == game["plays"]
        assert db.execute("SELECT COUNT(*) FROM player_game_stats WHERE game_id = ?", (game["game_id"],)).fetchone()[0] > 20
    db.close()
    assert season.play_week() == []  # nothing left to play this week
    assert season.advance_week() == 2


def test_box_score_matches_the_final(scratch_db):
    game = season.play_week()[0]
    box = season.box_score(game["game_id"])
    assert box["simulated"] and box["plays"][-1]["home_score"] == game["home_score"]
    home = box["teams"][game["home_team_id"]]
    assert home["total_yds"] == home["pass_yds"] + home["rush_yds"]
    assert {line["team_id"] for line in box["players"]} == {game["home_team_id"], game["away_team_id"]}


def test_same_season_seed_same_results(tmp_path):
    results = []
    for name in ("a", "b"):
        path = tmp_path / f"{name}.db"
        league_db.build(path, season_seed=99)
        results.append([(g["home_score"], g["away_score"]) for g in season.play_week(path)])
    assert results[0] == results[1]


def test_a_trade_changes_who_plays(scratch_db):
    """Games use the rosters as they stand when they're played."""
    from agents.rules import Trade, make_trade

    def starting_safeties():
        db = league_db.connect()
        try:
            return [p["id"] for p in season._lineup(db, "HAR").starters("S", 2)]
        finally:
            db.close()

    assert "SUM-45" not in starting_safeties()
    make_trade(Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"]))
    assert starting_safeties()[0] == "SUM-45"  # Odom (73) starts ahead of Strickland (70)


def test_play_game_only_this_week(scratch_db):
    later = season.games(2)[0]
    with pytest.raises(ValueError, match="in week 2"):
        season.play_game(later["id"])
    first = season.games(1)[0]
    season.play_game(first["id"])
    with pytest.raises(ValueError, match="already been played"):
        season.play_game(first["id"])


def test_g1_saves_are_upgraded_not_refused(tmp_path):
    path = tmp_path / "g1.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:  # turn it back into a G1 database
        db.executescript("DROP TABLE plays; DROP TABLE player_game_stats; PRAGMA user_version = 1;")
    db.close()
    played = season.play_week(path)
    assert len(played) == 3
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()
