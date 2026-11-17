"""Checks for the league rules (task 1.2). No API key needed.

Every test uses a scratch database built from the seed (conftest.py), so trades
made here never touch data/league.db. Players are picked by salary from the
database rather than hard-coded, so the tests follow the generated league.
"""

import json

import pytest

from agents import league_db
from agents.rules import IllegalMove, Trade, check_trade, make_trade, move_log
from agents.tools import list_teams


def by_salary(team_id: str) -> list[dict]:
    """A team's players, cheapest first."""
    db = league_db.connect()
    try:
        return [dict(row) for row in db.execute(
            "SELECT p.id, p.team_id, c.salary FROM players p JOIN contracts c ON c.player_id = p.id "
            "WHERE p.team_id = ? ORDER BY c.salary, p.id", (team_id,))]
    finally:
        db.close()


def cap_space(team_id: str) -> float:
    return next(t["cap_space"] for t in json.loads(list_teams())["teams"] if t["id"] == team_id)


def set_week(week: int) -> None:
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


def team_of(player_id: str) -> str:
    db = league_db.connect()
    try:
        return db.execute("SELECT team_id FROM players WHERE id = ?", (player_id,)).fetchone()[0]
    finally:
        db.close()


def rules_broken(result: dict) -> list[tuple[str, str | None]]:
    return [(v["rule"], v["team_id"]) for v in result["violations"]]


def test_even_swap_is_legal_and_moves_the_players(scratch_db):
    ours, theirs = by_salary("HAR")[0]["id"], by_salary("MES")[0]["id"]
    trade = Trade("HAR", [ours], "MES", [theirs])
    assert check_trade(trade)["legal"] is True

    result = make_trade(trade)
    assert result["legal"] is True and result["violations"] == []
    assert (team_of(ours), team_of(theirs)) == ("MES", "HAR")
    assert result["teams_after"]["HAR"]["roster_size"] == 48
    assert result["teams_after"]["HAR"]["payroll"] == pytest.approx(
        next(t["payroll"] for t in json.loads(list_teams())["teams"] if t["id"] == "HAR"), abs=0.06)


def test_check_trade_changes_nothing(scratch_db):
    before = league_db.load_league()
    check_trade(Trade("HAR", [by_salary("HAR")[0]["id"]], "MES", [by_salary("MES")[0]["id"]]))
    assert league_db.load_league() == before


def test_trade_over_the_hard_cap_is_rejected(scratch_db):
    """We have $5.5M of space; taking Summit's top contract for our cheapest player breaks the cap."""
    cheap, star = by_salary("HAR")[0], by_salary("SUM")[-1]
    assert star["salary"] - cheap["salary"] > cap_space("HAR")

    result = check_trade(Trade("HAR", [cheap["id"]], "SUM", [star["id"]]))
    assert rules_broken(result) == [("hard_cap", "HAR")]
    assert "over the $255.0M hard cap" in result["violations"][0]["message"]
    assert result["teams_after"]["HAR"]["cap_space"] < 0


def test_filling_the_cap_exactly_is_legal(scratch_db):
    """The cap is a limit we may reach, not one we must stay under by a margin."""
    cheap, target = by_salary("HAR")[0], by_salary("MES")[-1]
    exact = round(cheap["salary"] + 255.0 - sum(p["salary"] for p in by_salary("HAR")), 2)
    db = league_db.connect()
    with db:
        db.execute("UPDATE contracts SET salary = ? WHERE player_id = ?", (exact, target["id"]))
    db.close()

    trade = Trade("HAR", [cheap["id"]], "MES", [target["id"]])
    assert check_trade(trade)["legal"] is True

    db = league_db.connect()
    with db:
        db.execute("UPDATE contracts SET salary = ? WHERE player_id = ?", (exact + 0.01, target["id"]))
    db.close()
    assert rules_broken(check_trade(trade)) == [("hard_cap", "HAR")]


def test_roster_below_the_minimum_is_rejected(scratch_db):
    """48 players, minimum 46: giving away three for nothing leaves 45."""
    given = [p["id"] for p in by_salary("SUM")[:3]]
    result = check_trade(Trade("SUM", given, "DEL", []))
    assert rules_broken(result) == [("roster_min", "SUM")]
    assert result["violations"][0]["message"] == "SUM would have 45 players; the roster minimum is 46."


def test_roster_above_the_maximum_is_rejected(scratch_db):
    """Maximum 53: taking six players for nothing gives 54 (and leaves the other team with 42)."""
    given = [p["id"] for p in by_salary("SUM")[:6]]
    result = check_trade(Trade("SUM", given, "IRN", []))
    assert rules_broken(result) == [("roster_min", "SUM"), ("roster_max", "IRN")]
    assert result["teams_after"]["IRN"]["roster_size"] == 54


def test_trade_deadline_closes_trades_after_week_9(scratch_db):
    trade = Trade("HAR", [by_salary("HAR")[0]["id"]], "MES", [by_salary("MES")[0]["id"]])
    set_week(9)
    assert check_trade(trade)["legal"] is True
    set_week(10)
    result = check_trade(trade)
    assert rules_broken(result) == [("trade_deadline", None)]
    assert "after week 9" in result["violations"][0]["message"]


def test_every_broken_rule_is_reported_at_once(scratch_db):
    cheap, star = by_salary("HAR")[0], by_salary("SUM")[-1]
    extra = [p["id"] for p in by_salary("HAR")[1:4]]  # 48 - 4 + 1 = 45, one under the minimum
    set_week(12)
    result = check_trade(Trade("HAR", [cheap["id"], *extra], "SUM", [star["id"]]))
    assert set(rules_broken(result)) == {("trade_deadline", None), ("roster_min", "HAR"), ("hard_cap", "HAR")}


@pytest.mark.parametrize("trade, reason", [
    (Trade("HAR", ["HAR-01"], "XYZ", []), "Unknown team id 'XYZ'"),
    (Trade("HAR", ["HAR-01"], "HAR", ["HAR-02"]), "two different teams"),
    (Trade("HAR", [], "MES", []), "moves no players"),
    (Trade("HAR", ["MES-01"], "MES", []), "plays for MES, not HAR"),
    (Trade("HAR", ["HAR-99"], "MES", []), "no player with id 'HAR-99'"),
    (Trade("HAR", ["HAR-01", "HAR-01"], "MES", []), "listed more than once"),
])
def test_impossible_trades_are_rejected(scratch_db, trade, reason):
    result = check_trade(trade)
    assert result["legal"] is False
    assert any(v["rule"] == "invalid_trade" and reason in v["message"] for v in result["violations"])
    assert result["teams_after"] == {}


def test_ids_are_case_insensitive(scratch_db):
    result = check_trade(Trade("har", ["har-01"], " mes", ["mes-01"]))
    assert result["legal"] is True
    assert result["trade"] == {"team_a": "HAR", "a_sends": ["HAR-01"], "team_b": "MES", "b_sends": ["MES-01"]}


def test_illegal_trade_is_refused_and_changes_nothing(scratch_db):
    before = league_db.load_league()
    cheap, star = by_salary("HAR")[0], by_salary("SUM")[-1]
    with pytest.raises(IllegalMove) as refused:
        make_trade(Trade("HAR", [cheap["id"]], "SUM", [star["id"]]))
    assert [v.rule for v in refused.value.violations] == ["hard_cap"]
    assert "hard cap" in str(refused.value)
    assert league_db.load_league() == before


def test_a_trade_cannot_be_made_twice(scratch_db):
    """After the first trade the players have moved, so the same trade no longer makes sense."""
    trade = Trade("HAR", [by_salary("HAR")[0]["id"]], "MES", [by_salary("MES")[0]["id"]])
    make_trade(trade)
    with pytest.raises(IllegalMove) as refused:
        make_trade(trade)
    assert {v.rule for v in refused.value.violations} == {"invalid_trade"}


def test_trades_are_logged_with_the_week(scratch_db):
    ours, theirs = by_salary("HAR")[0], by_salary("MES")[0]
    set_week(4)
    result = make_trade(Trade("HAR", [ours["id"]], "MES", [theirs["id"]]))
    assert result["week"] == 4
    log = move_log()
    assert [(m["id"], m["week"], m["kind"]) for m in log] == [(result["move_id"], 4, "trade")]
    assert {(p["player_id"], p["from_team_id"], p["to_team_id"]) for p in log[0]["players"]} == {
        (ours["id"], "HAR", "MES"), (theirs["id"], "MES", "HAR")}


def test_refused_trades_are_not_logged(scratch_db):
    with pytest.raises(IllegalMove):
        make_trade(Trade("HAR", [by_salary("HAR")[0]["id"]], "SUM", [by_salary("SUM")[-1]["id"]]))
    assert move_log() == []
