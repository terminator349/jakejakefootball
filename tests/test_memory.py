"""Checks for the front office's memory (task 4.2). No API key needed: memory is plain
Python over the save, and the model runs that read it are stood in for."""

import asyncio
import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from agents import briefing, league_db, memory, orders, rivals, saves, scouting
from agents import trade_desk as desk
from agents.orders import MoveRefused, OrderTerms
from agents.tools import load_league
from ui.server import app


def an_order(text="Upgrade safety.", **changes) -> int:
    base = dict(summary="Upgrade safety.", wants_trades=True, positions=["S"], max_incoming_salary=None,
                max_added_payroll=None, protected_player_ids=[])
    terms = OrderTerms(**{**base, **changes})
    return orders.save_order(text, orders.ground_terms(terms, load_league()))


def set_week(week: int) -> None:
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


def kinds() -> list[str]:
    return [e["kind"] for e in memory.timeline()]


# ---- The timeline -------------------------------------------------------------------------------

def test_a_new_game_remembers_nothing(scratch_db):
    assert memory.timeline() == [] and memory.recall() == []
    assert memory.text([], 1) == ("What you remember from this season (it is week 1 now): nothing yet; this is "
                                  "the start of the season.")


def test_orders_and_the_owners_decisions(scratch_db):
    oid = an_order("Upgrade safety. Don't trade Okafor.", protected_player_ids=["HAR-01"])
    vetoed = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    orders.veto(vetoed, "Not Dubois, he's our special teams captain.")
    set_week(2)
    waiting = orders.file_move(oid, "SUM", ["HAR-41"], ["SUM-45"], "Odom for Strickland.")
    t = memory.timeline()
    assert [e["kind"] for e in t] == ["order", "vetoed", "proposed"]
    order, veto, proposed = t
    assert order["text"] == 'You gave order #1: "Upgrade safety. Don\'t trade Okafor." (it stands).'
    assert order["players"] == ["HAR-01"] and order["positions"] == ["S"]
    assert veto["week"] == 1 and veto["text"] == (
        "You vetoed my move #1, sending Hunter Dubois (S) to Summit for Isaiah Odom (S): \"Not Dubois, he's our "
        "special teams captain.\".")
    assert veto["owner_words"] == "Not Dubois, he's our special teams captain." and veto["teams"] == ["SUM"]
    assert proposed["week"] == 2 and f"(move #{waiting}); it waits for you." in proposed["text"]

    orders.cancel_order(oid)  # the waiting move goes void with it
    t = memory.timeline()
    assert "(since cancelled)" in t[0]["text"] and t[-1]["kind"] == "void"
    assert "went void: You cancelled the order." in t[-1]["text"]


def test_trades_and_offers(scratch_db):
    oid = an_order()
    move = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom.")
    sent = orders.approve(move, "Go get him.")
    desk.respond(sent["move"]["desk_proposal_id"], "SUM", "accept")
    offer = desk.propose("LAK", ["LAK-47"], "HAR", ["HAR-47"])["proposal"]["id"]
    rivals.reject_offer(offer, "We keep our punter.")
    ours = desk.propose("HAR", ["HAR-42"], "MES", ["MES-41"])["proposal"]["id"]
    desk.respond(ours, "MES", "reject", "Not enough for a starter.")
    t = memory.timeline()
    assert [e["kind"] for e in t] == ["order", "approved", "trade", "offer_to_us", "our_offer"]  # as it happened
    assert t[1]["text"].endswith(': "Go get him.".') and t[1]["owner_words"] == "Go get him."
    assert t[2]["text"] == "Trade made: Summit accepted our offer, so we got Isaiah Odom (S) for Hunter Dubois (S)."
    assert t[3]["text"].startswith("You turned down Lakeshore's offer of ") and t[3]["text"].endswith(
        ': "We keep our punter.".')
    assert t[4]["text"].startswith("Mesa Verde turned down our offer of ") and "Not enough for a starter." in t[4]["text"]


def test_reports_briefings_and_answers(scratch_db):
    oid = an_order()
    found = {"S": scouting.targets("S")}
    scouting.save_report(scouting.rules_report(found), oid)
    db = league_db.connect()
    with db:
        db.execute("INSERT INTO briefings VALUES (1, ?, '2026-11-24', NULL)",
                   (json.dumps({"headline": "Season opens at Summit", "paragraphs": [], "watch": ""}),))
    db.close()
    memory.remember_answer("Where are we weakest?", "Safety coverage, 6th of 6.", "Trade for a safety.",
                           ["Analytics"], 0.001)
    memory.remember_answer("Who's our QB?", "Mateo Okafor.", "None.")
    t = memory.timeline()
    assert [e["kind"] for e in t] == ["briefing", "answer", "answer", "order", "scouting"]  # within a week, by kind
    assert t[0]["text"] == "My briefing: Season opens at Summit"
    assert t[1]["text"] == ('You asked: "Where are we weakest?" I answered: Safety coverage, 6th of 6. '
                            "I recommended: Trade for a safety.")
    assert "I recommended" not in t[2]["text"]
    first = found["S"]["players"][0]
    assert t[4]["text"].startswith("Scouting reported on S: Found ") and f"{first['name']} (S, {first['team']})" in t[4]["text"]
    assert first["id"] in t[4]["players"]


def test_a_long_answer_is_cut(scratch_db):
    memory.remember_answer("Tell me everything.", "word " * 200)
    [e] = memory.timeline()
    assert e["text"].endswith("...") and len(e["text"]) < memory.LONG + 80


# ---- Recalling what matters ----------------------------------------------------------------------

def test_recall_keeps_decisions_and_whats_relevant(scratch_db):
    oid = an_order()
    move = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom.")
    orders.veto(move, "No.")
    for i in range(6):
        memory.remember_answer(f"Question {i}?", f"Answer {i}.")
    cb = an_order("Find a corner.", positions=["CB"])
    assert [e["kind"] for e in memory.recall(limit=1)] == ["vetoed"]  # the owner's decisions always come
    every = memory.timeline()
    recalled = memory.recall(limit=4)
    assert len(recalled) == 4 and recalled[-3:] == every[-3:]  # then the most recent
    assert len(memory.recall(limit=0)) == 1
    about_s = memory.recall(positions=["S"], limit=1)
    assert {e["kind"] for e in about_s} == {"order", "vetoed"} and all("S" in e["positions"] for e in about_s)
    assert memory.recall(players=["SUM-45"], limit=1)[0]["players"] == ["HAR-46", "SUM-45"]
    weeks = [e["week"] for e in memory.recall()]
    assert weeks == sorted(weeks)
    lines = memory.text(memory.recall(), 1).splitlines()
    assert lines[:2] == ["What you remember from this season (it is week 1 now):",
                         '(In these notes "You" is the owner and "I" is you, the GM.)']
    # The questions come last, in the order asked, after everything else.
    split = lines.index("The owner's questions to you, oldest first (the last is the most recent):")
    assert all("You asked" not in line for line in lines[:split])
    assert [line.split('"')[1] for line in lines[split + 1:]] == [f"Question {i}?" for i in range(6)]
    assert cb


def test_since_last_week_is_for_the_briefing(scratch_db):
    oid = an_order()
    orders.veto(orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom."), "No.")
    memory.remember_answer("Q?", "A.")
    set_week(3)
    assert memory.since_last_week(3) == []  # week 1 is too long ago
    assert [line.split(": ", 1)[1].split(" ")[1] for line in memory.since_last_week(2)] == ["gave", "vetoed"]


# ---- What the agents do with it -----------------------------------------------------------------

def test_a_vetoed_trade_isnt_proposed_again(scratch_db):
    oid = an_order()
    orders.veto(orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom."), "Keep Dubois.")
    assert memory.vetoed("SUM", ["HAR-46"], ["SUM-45"]) == {"week": 1, "note": "Keep Dubois."}
    with pytest.raises(MoveRefused) as refused:
        orders.file_move(an_order(), "SUM", ["HAR-46"], ["SUM-45"], "Odom again.")
    assert refused.value.problems == ['You vetoed this exact trade in week 1 ("Keep Dubois."); it won\'t be '
                                      "proposed again."]
    assert orders.file_move(oid, "SUM", ["HAR-41"], ["SUM-45"], "A different deal.")  # another deal is fine


def test_the_gms_search_remembers(scratch_db):
    oid = an_order()
    orders.veto(orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom."), "Keep Dubois.")
    order = next(o for o in orders.orders() if o["id"] == oid)
    prompt = orders.search_prompt(order, orders.orders(), load_league(), 1)
    assert "What you remember from this season (it is week 1 now):" in prompt
    assert 'You vetoed my move #1, sending Hunter Dubois (S) to Summit for Isaiah Odom (S): "Keep Dubois."' in prompt
    assert any("owner's earlier decisions" in i for i in orders.SEARCH_INSTRUCTIONS)


def test_the_scouts_see_each_targets_history(scratch_db):
    target = scouting.targets("S")["players"][0]
    send = target["offer"]["we_send"][0]["id"] if target["offer"] else "HAR-46"
    oid = an_order()
    move = orders.file_move(oid, target["team_id"], [send], [target["id"]], "Him.")
    orders.veto(move, "Too old for us.")
    again = next(p for p in scouting.targets("S")["players"] if p["id"] == target["id"])
    assert len(again["history"]) == 1 and "Too old for us." in again["history"][0]
    assert scouting.rules_note(again).endswith(f"Before: {again['history'][0]}")
    report = scouting.rules_report({"S": scouting.targets("S")})
    entry = next(t for t in report["targets"] if t["player_id"] == target["id"])
    assert entry["history"] == again["history"] and f"[{again['history'][0]}]" in scouting.report_text(report)
    assert "the owner vetoed a trade for him" in scouting.skills.section("scouting", "Grades")


def test_the_briefing_hears_what_was_decided(scratch_db):
    assert "front_office_since_last_week" not in briefing.facts()
    oid = an_order()
    orders.veto(orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom."), "Keep Dubois.")
    facts = briefing.facts()
    assert any("You vetoed my move #1" in line for line in facts["front_office_since_last_week"])
    assert "front_office_since_last_week" in briefing.skills.section("front-office-memo", "The weekly briefing")


def test_the_gm_keeps_only_real_answers(scratch_db):
    from agents import gm
    gm.keep("Q?", {"report": None, "text": "  ", "consulted": [], "cost": None})
    gm.keep("Q?", {"report": None, "text": "Plain text answer.", "consulted": ["Analytics"], "cost": 0.01})
    [e] = memory.timeline()
    assert e["text"] == 'You asked: "Q?" I answered: Plain text answer.'


# ---- Saves ---------------------------------------------------------------------------------------

def test_older_saves_get_the_answers_table(tmp_path):
    path = tmp_path / "v9.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:
        db.executescript("DROP TABLE gm_answers; PRAGMA user_version = 9;")
    db.close()
    league_db.connect(path).close()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM gm_answers").fetchone()[0] == 0
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION == 10
    db.close()


@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_memory_lives_in_the_save(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client.post("/api/saves/new", json={"name": "first", "seed": "3"})
    assert client.get("/api/hub").json()["memory"] == []
    move = orders.file_move(an_order(), "SUM", ["HAR-46"], ["SUM-45"], "Odom.")
    client.post("/api/hub/move/veto", json={"move_id": move, "note": "Keep Dubois."})
    [order, veto] = client.get("/api/hub").json()["memory"]
    assert veto["kind"] == "vetoed" and veto["owner_words"] == "Keep Dubois."

    client.post("/api/saves/new", json={"name": "second", "seed": "3"})  # a new game starts with none
    assert client.get("/api/hub").json()["memory"] == []
    client.post("/api/saves/load", json={"name": "first"})  # and loading the first brings it back
    assert [e["kind"] for e in client.get("/api/hub").json()["memory"]] == ["order", "vetoed"]
    page = client.get("/").text
    assert "Front office memory" in page and "your GM remembers" in page
