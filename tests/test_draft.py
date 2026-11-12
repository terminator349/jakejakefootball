"""Checks for the draft engine. These need no API key: run `pytest`.

A full heuristic (--no-llm) draft runs in-process here to check the engine
end to end; the LLM-agent path (draft/agent.py) isn't exercised without an
OPENROUTER_API_KEY and isn't covered by these tests.
"""

from draft.engine import DraftEngine, build_teams, random_draft_order, snake_pick_order
from draft.players import build_player_pool
from draft.roster_rules import ROSTER_TEMPLATE, SALARY_CAP, TEAMS, rookie_salary
from draft.valuation import market_value, need_score, pick_score


def test_roster_template_sums_to_53():
    assert sum(ROSTER_TEMPLATE.values()) == 53


def test_player_pool_has_enough_depth_for_every_position():
    pool = build_player_pool()
    needed_per_position = {pos: target * len(TEAMS) for pos, target in ROSTER_TEMPLATE.items()}
    counts = {}
    for p in pool:
        counts[p.position] = counts.get(p.position, 0) + 1
    for position, needed in needed_per_position.items():
        assert counts.get(position, 0) >= needed, f"{position}: pool has {counts.get(position, 0)}, needs {needed}"


def test_player_pool_ids_are_unique():
    pool = build_player_pool()
    ids = [p.id for p in pool]
    assert len(ids) == len(set(ids))


def test_player_ratings_are_in_range():
    for p in build_player_pool():
        assert 25 <= p.overall <= 99


def test_rookie_salary_decreases_with_pick_number():
    assert rookie_salary(1, "QB") > rookie_salary(300, "QB")
    assert rookie_salary(318, "QB") >= 0.9


def test_market_value_rewards_premium_positions_over_league_average():
    assert market_value(80, "QB") > market_value(80, "C")


def test_need_score_is_zero_once_position_is_full():
    counts = {"K": ROSTER_TEMPLATE["K"]}
    assert need_score(counts, "K") == 0.0


def test_need_score_favors_a_position_with_zero_players():
    zero = need_score({}, "WR")
    partial = need_score({"WR": ROSTER_TEMPLATE["WR"] - 1}, "WR")
    assert zero > partial > 0


def test_pick_score_increases_with_need_weight_for_a_needed_position():
    low_need_weight = pick_score(70, "WR", {}, need_weight=0.0)
    high_need_weight = pick_score(70, "WR", {}, need_weight=1.0)
    assert high_need_weight > low_need_weight


def test_snake_pick_order_reverses_every_other_round():
    teams = build_teams(None, __import__("random").Random(1))
    order = random_draft_order(teams, __import__("random").Random(1))
    picks = list(snake_pick_order(order, rounds=4))
    round1 = [team.id for (r, _, _, team) in picks if r == 1]
    round2 = [team.id for (r, _, _, team) in picks if r == 2]
    round3 = [team.id for (r, _, _, team) in picks if r == 3]
    assert round1 == [t.id for t in order]
    assert round2 == list(reversed(round1))
    assert round3 == round1


def test_snake_pick_order_overall_pick_is_sequential():
    teams = build_teams(None, __import__("random").Random(2))
    order = random_draft_order(teams, __import__("random").Random(2))
    overall_numbers = [overall for (_, _, overall, _) in snake_pick_order(order, rounds=3)]
    assert overall_numbers == list(range(1, len(order) * 3 + 1))


def test_full_heuristic_draft_fills_every_roster_legally():
    """End-to-end: 6 teams, 53 rounds, no LLM calls - checks the whole engine.

    The pool is built with spare depth at every position (see
    test_player_pool_has_enough_depth_for_every_position), so some players
    are always left undrafted once every roster hits its template exactly -
    that's expected, not a bug.
    """
    engine = DraftEngine(user_team_id=None, seed=3, use_llm=False)
    engine.run()

    assert len(engine.log) == 53 * len(TEAMS)
    for team in engine.teams:
        assert len(team.roster) == 53
        assert team.position_counts() == ROSTER_TEMPLATE
        assert team.payroll() <= SALARY_CAP, f"{team.id} is over the hard cap: ${team.payroll():.1f}M"


def test_random_draft_order_uses_every_team_once():
    teams = build_teams(None, __import__("random").Random(5))
    order = random_draft_order(teams, __import__("random").Random(5))
    assert sorted(t.id for t in order) == sorted(t.id for t in teams)


def test_user_team_is_marked():
    teams = build_teams("HAR", __import__("random").Random(0))
    user_teams = [t for t in teams if t.is_user]
    assert len(user_teams) == 1
    assert user_teams[0].id == "HAR"
    assert user_teams[0].philosophy == ""
