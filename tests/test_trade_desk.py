"""Checks for the Trade Desk (task 2.1): proposals, evaluation and the MCP server.
No API key needed.

The trades are the ones from GAMEPLAY_EXAMPLE.md: Dubois (HAR-46) for Odom
(SUM-45), Summit's counter asking for Bryce Strickland (HAR-41) too, and
Brennan (LAK-43), who doesn't fit under our cap.
"""

import asyncio
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agents import league_db, rules, saves
from agents import trade_desk as desk
from agents.trade_desk import TradeDeskError
from servers.trade_desk import trade_desk

PROJECT_ROOT = Path(__file__).parent.parent
ODOM = rules.Trade("HAR", ["HAR-46"], "SUM", ["SUM-45"])


def team_of(player_id: str) -> str:
    db = league_db.connect()
    try:
        return db.execute("SELECT team_id FROM players WHERE id = ?", (player_id,)).fetchone()[0]
    finally:
        db.close()


def set_week(week: int) -> None:
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


def offer_odom(note: str = "") -> int:
    made = desk.propose("HAR", ["HAR-46"], "SUM", ["SUM-45"], note)
    assert made["proposed"], made
    return made["proposal"]["id"]


# ---- Evaluating ----------------------------------------------------------------

def test_evaluate_shows_both_sides_of_the_odom_trade(scratch_db):
    result = desk.evaluate(ODOM)
    assert result["legal"] and result["rules"]["teams_after"]["HAR"]["cap_space"] == 2.06
    ours, theirs = result["teams"]["HAR"], result["teams"]["SUM"]
    assert [p["id"] for p in ours["gets"]] == ["SUM-45"] and [p["id"] for p in ours["gives"]] == ["HAR-46"]
    assert ours["salary_change"] == 3.46 and theirs["salary_change"] == -3.46
    # Odom starts for us, pushing Kowalski (coverage 45) to the bench; for Summit he was a backup.
    assert ours["new_starters"] == ["SUM-45"] and ours["benched"] == ["HAR-44"]
    assert theirs["starters_lost"] == [] and theirs["unit_changes"] == []
    coverage = {u["unit"]: u for u in ours["unit_changes"]}
    assert coverage["deep_coverage"]["change"] > 0 and coverage["short_coverage"]["change"] > 0
    assert abs(ours["unit_changes"][0]["change"]) >= abs(ours["unit_changes"][-1]["change"])  # biggest first


def test_evaluate_prices_players_with_the_valuation_skill(scratch_db):
    path = PROJECT_ROOT / "skills" / "player-valuation" / "scripts" / "value_player.py"
    spec = importlib.util.spec_from_file_location("value_player_check", path)
    skill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skill)
    odom = desk.evaluate(ODOM)["teams"]["HAR"]["gets"][0]
    expected = skill.value("S", 73, 4.46, 29, 5)
    assert (odom["market_value"], odom["surplus_per_season"], odom["verdict"]) == \
        (expected["market_value"], expected["surplus_per_season"], expected["verdict"])


def test_evaluate_of_an_impossible_trade_only_reports_the_rules(scratch_db):
    result = desk.evaluate(rules.Trade("HAR", ["SUM-45"], "SUM", []))
    assert not result["legal"] and "teams" not in result
    assert result["rules"]["violations"][0]["rule"] == "invalid_trade"


# ---- Proposing -----------------------------------------------------------------

def test_a_legal_proposal_is_stored_open_and_moves_nobody(scratch_db):
    made = desk.propose("har", ["har-46"], "sum", ["sum-45"], "Odom for Dubois?")
    assert made["proposed"]
    proposal = made["proposal"]
    assert (proposal["from_team_id"], proposal["to_team_id"], proposal["status"], proposal["week"]) == \
        ("HAR", "SUM", "open", 1)
    assert [p["name"] for p in proposal["sends"]] == ["Hunter Dubois"]
    assert [p["name"] for p in proposal["receives"]] == ["Isaiah Odom"]
    assert proposal["note"] == "Odom for Dubois?"
    assert team_of("SUM-45") == "SUM" and rules.move_log() == []


def test_an_illegal_proposal_is_refused_and_not_stored(scratch_db):
    made = desk.propose("HAR", ["HAR-46"], "LAK", ["LAK-43"])
    assert not made["proposed"]
    assert made["rules"]["violations"][0]["message"] == \
        "HAR's payroll would be $258.35M, $3.35M over the $255.0M hard cap."
    assert desk.proposals(status="all") == []


def test_no_proposals_after_the_deadline(scratch_db):
    set_week(10)
    made = desk.propose("HAR", ["HAR-46"], "SUM", ["SUM-45"])
    assert not made["proposed"]
    assert made["rules"]["violations"][0]["message"] == \
        "Trades closed after week 9, the trade deadline; it is week 10."


def test_the_same_offer_cant_be_open_twice(scratch_db):
    first = offer_odom()
    with pytest.raises(TradeDeskError, match=f"#{first} already offers SUM"):
        desk.propose("HAR", ["HAR-46"], "SUM", ["SUM-45"])


# ---- Answering -----------------------------------------------------------------

def test_only_the_right_team_can_answer_or_withdraw(scratch_db):
    pid = offer_odom()
    with pytest.raises(TradeDeskError, match="Only SUM can answer"):
        desk.respond(pid, "HAR", "accept")
    with pytest.raises(TradeDeskError, match="Only SUM can answer"):
        desk.counter(pid, "MES", [], ["HAR-46"])
    with pytest.raises(TradeDeskError, match="Only HAR can withdraw"):
        desk.withdraw(pid, "SUM")
    with pytest.raises(TradeDeskError, match="no trade proposal #99"):
        desk.respond(99, "SUM", "accept")
    with pytest.raises(TradeDeskError, match="'accept' or 'reject'"):
        desk.respond(pid, "SUM", "maybe")
    assert desk.proposal(pid)["status"] == "open"


def test_reject_and_withdraw_close_a_proposal(scratch_db):
    pid = offer_odom()
    rejected = desk.respond(pid, "SUM", "reject", "Odom is our insurance at safety.")
    assert not rejected["accepted"]
    assert (rejected["proposal"]["status"], rejected["proposal"]["response"]) == \
        ("rejected", "Odom is our insurance at safety.")
    with pytest.raises(TradeDeskError, match="is rejected, not open"):
        desk.respond(pid, "SUM", "accept")

    pid = offer_odom()  # the same offer again is fine once the first is closed
    assert desk.withdraw(pid, "HAR")["proposal"]["status"] == "withdrawn"
    assert team_of("SUM-45") == "SUM"


def test_accepting_makes_the_trade_and_logs_it(scratch_db):
    pid = offer_odom()
    result = desk.respond(pid, "SUM", "accept", "Deal.")
    assert result["accepted"] and result["voided"] == []
    assert result["proposal"]["status"] == "accepted" and result["proposal"]["move_id"] == result["trade"]["move_id"]
    assert (team_of("SUM-45"), team_of("HAR-46")) == ("HAR", "SUM")
    [move] = rules.move_log()
    assert move["id"] == result["trade"]["move_id"]
    assert {p["player_id"]: p["to_team_id"] for p in move["players"]} == {"HAR-46": "SUM", "SUM-45": "HAR"}


def test_the_counter_from_the_example_season(scratch_db):
    pid = offer_odom()
    countered = desk.counter(pid, "SUM", ["SUM-45"], ["HAR-46", "HAR-41"],
                             "Add Bryce Strickland and you have a deal.")
    assert countered["proposed"]
    new = countered["proposal"]
    assert (new["from_team_id"], new["to_team_id"], new["counter_of"], new["status"]) == ("SUM", "HAR", pid, "open")
    original = desk.proposal(pid)
    assert (original["status"], original["response"]) == ("countered", f"Countered with proposal #{new['id']}.")
    assert "rules_now" not in original  # only open proposals are re-checked

    assert desk.proposal(new["id"])["rules_now"]["legal"]
    accepted = desk.respond(new["id"], "HAR", "accept")
    assert accepted["trade"]["teams_after"]["HAR"] == {"roster_size": 47, "payroll": 251.86, "cap_space": 3.14}


def test_an_illegal_counter_is_refused_and_the_offer_stays_open(scratch_db):
    pid = offer_odom()
    # Summit offers three safeties for nothing: $14.08M more puts us over the cap,
    # and Summit would be down to 45 players, under the minimum of 46.
    refused = desk.counter(pid, "SUM", ["SUM-45", "SUM-43", "SUM-44"], [])
    assert not refused["proposed"]
    assert {v["rule"] for v in refused["rules"]["violations"]} == {"roster_min", "hard_cap"}
    assert desk.proposal(pid)["status"] == "open"
    assert len(desk.proposals(status="all")) == 1


def test_a_trade_voids_other_offers_for_the_same_players(scratch_db):
    ours = offer_odom()
    mesa = desk.propose("MES", ["MES-44"], "SUM", ["SUM-45"])["proposal"]["id"]   # Sato for Odom
    other = desk.propose("MES", ["MES-01"], "LAK", ["LAK-01"])["proposal"]["id"]  # nothing to do with Odom
    result = desk.respond(ours, "SUM", "accept")
    assert result["voided"] == [mesa]
    voided = desk.proposal(mesa)
    assert voided["status"] == "void" and "Isaiah Odom (SUM-45)" in voided["response"]
    assert f"proposal #{ours}" in voided["response"]
    assert desk.proposal(other)["status"] == "open"


def test_accepting_after_the_deadline_voids_the_offer(scratch_db):
    pid = offer_odom()
    set_week(10)
    assert desk.proposal(pid)["rules_now"]["legal"] is False
    result = desk.respond(pid, "SUM", "accept")
    assert not result["accepted"] and result["violations"][0]["rule"] == "trade_deadline"
    assert result["proposal"]["status"] == "void"
    assert result["proposal"]["response"].startswith("Broke the league rules when accepted: Trades closed")
    assert team_of("SUM-45") == "SUM" and rules.move_log() == []


def test_list_proposals_filters_by_team_and_status(scratch_db):
    a = offer_odom()
    b = desk.propose("MES", ["MES-01"], "LAK", ["LAK-01"])["proposal"]["id"]
    desk.respond(b, "LAK", "reject")
    assert [p["id"] for p in desk.proposals()] == [a]
    assert [p["id"] for p in desk.proposals("lak", "all")] == [b]
    assert [p["id"] for p in desk.proposals(status="all")] == [a, b]
    assert [p["id"] for p in desk.proposals("SUM", "rejected")] == []
    with pytest.raises(TradeDeskError, match="status must be"):
        desk.proposals(status="pending")


# ---- Storage -------------------------------------------------------------------

def test_g3_saves_get_the_proposals_table(tmp_path):
    path = tmp_path / "g3.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:  # turn it back into a G3 (schema 4) database
        db.executescript("DROP INDEX open_proposals; DROP TABLE trade_proposals; PRAGMA user_version = 4;")
    db.close()
    assert desk.proposals(db_file=path) == []
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()


# ---- The MCP server ---------------------------------------------------------------

def call(tool: str, arguments: dict | None = None, server=trade_desk) -> dict:
    async def go():
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments or {})
            assert not result.is_error, result.content
            return json.loads(result.content[0].text)
    return asyncio.run(go())


def list_tools(server=trade_desk):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools
    return asyncio.run(go())


def test_serves_the_trade_tools_with_honest_annotations():
    tools = {t.name: t.annotations for t in list_tools()}
    assert set(tools) == {"evaluate_trade", "propose_trade", "list_proposals", "get_proposal",
                          "respond_to_proposal", "counter_proposal", "withdraw_proposal", "trade_log"}
    for name in ("evaluate_trade", "list_proposals", "get_proposal", "trade_log"):
        assert tools[name].read_only_hint is True
    for name in ("propose_trade", "counter_proposal", "withdraw_proposal"):
        assert tools[name].read_only_hint is False and tools[name].destructive_hint is False
    assert tools["respond_to_proposal"].destructive_hint is True  # the one that moves players


def test_docstrings_become_tool_descriptions():
    propose = next(t for t in list_tools() if t.name == "propose_trade")
    assert "Nothing" in propose.description and "moves until to_team accepts" in propose.description
    assert propose.input_schema["required"] == ["from_team", "sends", "to_team", "receives"]


def test_a_whole_trade_over_mcp(scratch_db):
    evaluated = call("evaluate_trade", {"team_a": "HAR", "a_sends": ["HAR-46"], "team_b": "SUM", "b_sends": ["SUM-45"]})
    assert evaluated == desk.evaluate(ODOM)
    made = call("propose_trade", {"from_team": "HAR", "sends": ["HAR-46"], "to_team": "SUM",
                                  "receives": ["SUM-45"], "note": "Odom for Dubois"})
    pid = made["proposal"]["id"]
    assert [p["id"] for p in call("list_proposals", {"team_id": "SUM"})] == [pid]
    assert call("get_proposal", {"proposal_id": pid})["rules_now"]["legal"]
    assert call("respond_to_proposal", {"proposal_id": pid, "team_id": "SUM", "decision": "accept"})["accepted"]
    assert call("trade_log")["moves"][0]["players"][0]["player_id"] == "HAR-46"


def test_mistakes_come_back_as_error_json(scratch_db):
    assert "no trade proposal #7" in call("get_proposal", {"proposal_id": 7})["error"]
    assert "status must be" in call("list_proposals", {"status": "pending"})["error"]
    pid = call("propose_trade", {"from_team": "HAR", "sends": ["HAR-46"], "to_team": "SUM",
                                 "receives": ["SUM-45"]})["proposal"]["id"]
    assert "Only SUM can answer" in call("respond_to_proposal", {"proposal_id": pid, "team_id": "HAR",
                                                                 "decision": "accept"})["error"]
    assert "Only HAR can withdraw" in call("withdraw_proposal", {"proposal_id": pid, "team_id": "SUM"})["error"]


def test_trades_over_stdio_land_in_the_save(tmp_path, monkeypatch):
    """The game will start the server with --db pointing at the loaded save."""
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path)
    save = saves.new_game("desk", season_seed=5)
    server = StdioServerParameters(command=sys.executable, args=["-m", "servers.trade_desk", "--db", str(save)],
                                   cwd=PROJECT_ROOT)
    pid = call("propose_trade", {"from_team": "HAR", "sends": ["HAR-46"], "to_team": "SUM",
                                 "receives": ["SUM-45"]}, server=server)["proposal"]["id"]
    assert call("respond_to_proposal", {"proposal_id": pid, "team_id": "SUM", "decision": "accept"},
                server=server)["accepted"]
    assert [m["id"] for m in rules.move_log(save)] == [1]
    assert desk.proposal(pid, save)["status"] == "accepted"
