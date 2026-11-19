"""Checks for the data and tools. These need no API key: run `pytest`."""

import asyncio
import json

import pytest
from agno.tools.mcp import MCPTools

from agents import league_db
from agents.analytics import build_analytics_agent, league_office_tools
from agents.tools import (check_cap_fit, compare_to_league, get_depth_chart, get_injury_report,
                          get_league_rules, get_roster, get_team_tendencies, list_teams,
                          load_league, set_depth_chart, validate_cap_compliance)


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


def test_the_cap_is_255_million_and_every_team_is_compliant():
    data = json.loads(validate_cap_compliance())
    assert data["salary_cap"] == 255.0
    assert data["all_teams_compliant"] is True
    assert data["teams_over_cap"] == []
    assert all(not t["over_cap"] for t in data["teams"])


def test_check_cap_fit_within_cap_space():
    team = next(t for t in json.loads(list_teams())["teams"] if t["id"] == "HAR")
    data = json.loads(check_cap_fit("HAR", team["cap_space"]))
    assert data["fits_under_cap"] is True
    assert data["salary_to_clear"] == 0.0
    assert data["cap_space_after"] == pytest.approx(0.0, abs=0.05)  # team["cap_space"] is rounded to 0.1


def test_check_cap_fit_reports_salary_to_clear_when_over():
    team = next(t for t in json.loads(list_teams())["teams"] if t["id"] == "HAR")
    data = json.loads(check_cap_fit("har", team["cap_space"] + 3))
    assert data["team_id"] == "HAR"
    assert data["fits_under_cap"] is False
    assert data["salary_to_clear"] == pytest.approx(3.0, abs=0.05)  # team["cap_space"] is rounded to 0.1


def test_check_cap_fit_rejects_unknown_team():
    assert "error" in json.loads(check_cap_fit("XYZ", 5.0))


def test_agent_builds_with_its_tools():
    agent = build_analytics_agent(league_office_tools())
    assert agent.name == "Analytics"
    assert agent.model.id == "deepseek/deepseek-v4.1-flash-1017"
    assert len(agent.tools) == 1 and isinstance(agent.tools[0], MCPTools)


def test_agent_sees_the_league_office_tools():
    """Starts the League Office server the way run.py does and lists what the agent gets."""
    async def go():
        async with league_office_tools() as league_office:
            return set(league_office.functions)
    assert asyncio.run(go()) == {"list_teams", "get_roster", "compare_to_league", "get_league_rules"}


def test_agent_has_loop_guards():
    """A run once looped on get_roster 65 times; these settings prevent that. The limit
    leaves room for 3-5 League Office calls plus loading a skill and running its script."""
    agent = build_analytics_agent(league_office_tools())
    assert agent.tool_call_limit is not None and agent.tool_call_limit <= 18
    assert agent.parser_model is not None


def test_parser_has_its_own_prompt():
    """With Agno's generic parser prompt, `answer` once came back as a reply to the parser's own task."""
    agent = build_analytics_agent(league_office_tools())
    assert "owner's question" in agent.parser_model_prompt


def test_ground_report_takes_facts_from_the_league():
    """Live runs gave team_id 'Harbor City Herons' and payroll 249500000; the league's numbers win."""
    from agents.analytics import RosterReport, ground_report

    report = RosterReport(team_id="Harbor City Herons", answer="a", weakest_area="w", evidence=["e"],
                          target_profile="t", payroll=249500000.0, cap_space=-1.0)
    grounded = ground_report(report)
    assert (grounded.team_id, grounded.payroll, grounded.cap_space) == ("HAR", 249.5, 5.5)
    assert grounded.answer == "a"
    assert ground_report(report.model_copy(update={"team_id": "nobody"})).team_id == "nobody"


# ---- Depth chart, injuries and tendencies (task 3.2) ------------------------

def test_get_depth_chart_defaults_to_sorting_by_overall():
    data = json.loads(get_depth_chart("har", "cb"))
    cbs = data["depth_chart"]["CB"]["players"]
    assert data["depth_chart"]["CB"]["custom_order"] is False
    assert [p["overall"] for p in cbs] == sorted((p["overall"] for p in cbs), reverse=True)
    assert [p["starter"] for p in cbs] == [True, True] + [False] * (len(cbs) - 2)


def test_get_depth_chart_rejects_unknown_team_or_position():
    assert "error" in json.loads(get_depth_chart("XYZ"))
    assert "error" in json.loads(get_depth_chart("HAR", "PG"))


def test_set_depth_chart_changes_the_order(scratch_db):
    before = json.loads(get_depth_chart("HAR", "S"))["depth_chart"]["S"]["players"]
    new_order = [p["id"] for p in reversed(before)]
    result = json.loads(set_depth_chart("HAR", "S", new_order))
    safeties = result["depth_chart"]["S"]["players"]
    assert [p["id"] for p in safeties] == new_order
    assert safeties[0]["starter"] is True
    assert result["depth_chart"]["S"]["custom_order"] is True
    # The new order sticks for later reads too.
    assert [p["id"] for p in json.loads(get_depth_chart("HAR", "S"))["depth_chart"]["S"]["players"]] == new_order


def test_set_depth_chart_rejects_an_incomplete_or_foreign_roster(scratch_db):
    current = [p["id"] for p in json.loads(get_depth_chart("HAR", "S"))["depth_chart"]["S"]["players"]]
    assert "error" in json.loads(set_depth_chart("HAR", "S", current[:-1]))  # leaves someone out
    assert "error" in json.loads(set_depth_chart("HAR", "S", current + ["MES-01"]))  # not a HAR safety
    assert "error" in json.loads(set_depth_chart("XYZ", "S", current))


def test_a_stale_depth_chart_falls_back_to_overall(scratch_db):
    """A trade changes who plays a position; an order set before the trade no longer
    names exactly that roster, so it's ignored rather than used anyway."""
    from agents.rules import Trade, make_trade

    before = [p["id"] for p in json.loads(get_depth_chart("HAR", "S"))["depth_chart"]["S"]["players"]]
    set_depth_chart("HAR", "S", list(reversed(before)))
    make_trade(Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"]))
    assert json.loads(get_depth_chart("HAR", "S"))["depth_chart"]["S"]["custom_order"] is False


def test_get_injury_report_starts_empty(scratch_db):
    assert json.loads(get_injury_report())["injuries"] == []
    assert json.loads(get_injury_report("HAR"))["injuries"] == []


def test_get_injury_report_shows_games_remaining(scratch_db):
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = 5")
        league_db.save_injury(db, "HAR-01", "HAR", since_week=4, games_out=2, description="Ankle sprain.")
    db.close()
    injuries = json.loads(get_injury_report("HAR"))["injuries"]
    assert len(injuries) == 1
    assert injuries[0] == {"player_id": "HAR-01", "name": injuries[0]["name"], "position": injuries[0]["position"],
                           "team_id": "HAR", "since_week": 4, "games_remaining": 2, "description": "Ankle sprain."}
    assert json.loads(get_injury_report("MES"))["injuries"] == []


def test_get_injury_report_rejects_unknown_team():
    assert "error" in json.loads(get_injury_report("XYZ"))


def test_get_team_tendencies_before_any_games(scratch_db):
    data = json.loads(get_team_tendencies("HAR"))
    assert data == {"team_id": "HAR", "plays_sampled": 0, "offense_play_mix": {},
                    "offense_mix_3rd_4th_and_7_plus": {}, "defense_call_mix": {}}


def test_get_team_tendencies_after_a_week_of_games(scratch_db):
    from agents import season
    season.play_week()
    data = json.loads(get_team_tendencies("HAR"))
    assert data["plays_sampled"] > 0
    assert abs(sum(data["offense_play_mix"].values()) - 1.0) < 0.01
    assert abs(sum(data["defense_call_mix"].values()) - 1.0) < 0.01


def test_get_team_tendencies_rejects_unknown_team():
    assert "error" in json.loads(get_team_tendencies("XYZ"))
