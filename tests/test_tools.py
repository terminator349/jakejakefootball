"""Checks for the data and tools. These need no API key: run `pytest`."""

import json

from agents.analytics import build_analytics_agent
from agents.tools import compare_to_league, get_league_rules, get_roster, list_teams, load_league


def test_every_team_has_a_legal_roster():
    league = load_league()
    rules = league["rules"]
    for team in league["teams"]:
        roster = json.loads(get_roster(team["id"]))["players"]
        assert rules["roster_min"] <= len(roster) <= rules["roster_max"]


def test_every_team_can_field_its_starters():
    league = load_league()
    for team in league["teams"]:
        for position, starters in league["rules"]["starters_per_position"].items():
            players = json.loads(get_roster(team["id"], position))["players"]
            assert sum(p["starter"] for p in players) == starters


def test_every_team_is_under_the_hard_cap():
    data = json.loads(list_teams())
    assert data["our_team"] in [t["id"] for t in data["teams"]]
    assert all(t["payroll"] > 0 and t["cap_space"] >= 0 for t in data["teams"])


def test_get_roster_rejects_unknown_team_and_position():
    assert "error" in json.loads(get_roster("XYZ"))
    assert "error" in json.loads(get_roster("HAR", "PG"))


def test_get_roster_is_case_insensitive():
    data = json.loads(get_roster("har", "cb"))
    assert data["team_id"] == "HAR"
    assert {p["position"] for p in data["players"]} == {"CB"}


def test_get_roster_lists_best_players_first():
    players = json.loads(get_roster("HAR", "WR"))["players"]
    overalls = [p["overall"] for p in players]
    assert overalls == sorted(overalls, reverse=True)


def test_rules_are_american_football():
    rules = json.loads(get_league_rules())
    assert rules["cap_type"] == "hard"
    assert "luxury_tax_line" not in rules  # football has no tax overage, unlike basketball
    assert rules["season_games"] == 17
    assert sum(rules["starters_per_position"].values()) == 24  # 11 offense, 11 defense, K, P


def test_our_secondary_has_the_worst_pass_coverage():
    """The generator plants this weakness; the agent should be able to find it."""
    league = load_league()

    def secondary_coverage(team_id):
        ratings = [p["ratings"]["coverage"] for p in league["players"]
                   if p["team_id"] == team_id and p["position"] in ("CB", "S")]
        return sum(ratings) / len(ratings)

    ours = secondary_coverage(league["our_team"])
    others = [secondary_coverage(t["id"]) for t in league["teams"] if t["id"] != league["our_team"]]
    assert ours < min(others)


def test_compare_to_league_puts_our_biggest_weakness_first():
    data = json.loads(compare_to_league("HAR"))
    worst = data["comparisons"][0]
    assert worst["rating"] == "coverage"
    assert worst["position"] in ("CB", "S")
    assert worst["rank"] == data["teams_in_league"]
    assert worst["gap"] < 0


def test_compare_to_league_rows_are_consistent():
    league = load_league()
    rows = json.loads(compare_to_league("mes"))["comparisons"]
    expected = 0
    for position in league["rules"]["starters_per_position"]:
        sample = next(p for p in league["players"] if p["position"] == position)
        expected += len(sample["ratings"]) + 1  # each rating plus overall
    assert len(rows) == expected
    assert [r["gap"] for r in rows] == sorted(r["gap"] for r in rows)
    assert all(1 <= r["rank"] <= len(league["teams"]) for r in rows)


def test_compare_to_league_rejects_unknown_team():
    assert "error" in json.loads(compare_to_league("XYZ"))


def test_agent_builds_with_its_tools():
    agent = build_analytics_agent()
    assert agent.name == "Analytics"
    assert agent.model.id == "deepseek/deepseek-v4.1-flash-1017"
    assert len(agent.tools) == 4


def test_agent_has_loop_guards():
    """A run once looped on get_roster 65 times; these settings prevent that."""
    agent = build_analytics_agent()
    assert agent.tool_call_limit is not None and agent.tool_call_limit <= 10
    assert agent.parser_model is not None
