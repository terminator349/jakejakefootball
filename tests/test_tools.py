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


def test_list_teams_includes_our_team_and_payrolls():
    data = json.loads(list_teams())
    ids = [t["id"] for t in data["teams"]]
    assert data["our_team"] in ids
    assert all(t["payroll"] > 0 for t in data["teams"])


def test_get_roster_rejects_unknown_team():
    assert "error" in json.loads(get_roster("XYZ"))


def test_get_roster_is_case_insensitive():
    assert json.loads(get_roster("har"))["team_id"] == "HAR"


def test_rules_have_a_hard_cap_and_no_tax_line():
    """Football uses a hard cap, not basketball's cap + luxury tax."""
    rules = json.loads(get_league_rules())
    assert "salary_cap" in rules
    assert "luxury_tax_line" not in rules
    assert rules["roster_min"] <= rules["roster_max"]


def test_every_team_is_legal_under_the_hard_cap():
    league = load_league()
    cap = league["rules"]["salary_cap"]
    for team in league["teams"]:
        payroll = sum(p["salary"] for p in league["players"] if p["team_id"] == team["id"])
        assert payroll <= cap, f"{team['id']} is over the hard cap: ${payroll:.1f}M > ${cap:.1f}M"


def test_our_team_is_worst_at_secondary_coverage():
    """The generator plants this weakness; the agent should be able to find it."""
    league = load_league()
    secondary = ("CB", "S")

    def avg_coverage(team_id):
        ratings = [p["ratings"]["coverage"] for p in league["players"]
                   if p["team_id"] == team_id and p["position"] in secondary]
        return sum(ratings) / len(ratings)

    ours = avg_coverage(league["our_team"])
    others = [avg_coverage(t["id"]) for t in league["teams"] if t["id"] != league["our_team"]]
    assert ours < min(others)


def test_compare_to_league_puts_our_biggest_weakness_first():
    data = json.loads(compare_to_league("HAR"))
    worst = data["comparisons"][0]
    assert worst["rating"] == "coverage"
    assert worst["group"] == "secondary"
    assert worst["rank"] == data["teams_in_league"]
    assert worst["gap"] < 0


def test_compare_to_league_rows_are_consistent():
    data = json.loads(compare_to_league("mes"))
    rows = data["comparisons"]
    assert len(rows) == 4 * 9  # four position groups x nine ratings
    assert [r["gap"] for r in rows] == sorted(r["gap"] for r in rows)
    assert all(1 <= r["rank"] <= data["teams_in_league"] for r in rows)


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
