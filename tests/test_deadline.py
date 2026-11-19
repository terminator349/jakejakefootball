"""Checks for the trade deadline in the game (task 2.3). No API key needed: the deadline
is worked by the rules' search, or by a stand-in for the GM's.

The trade is the one from GAMEPLAY_EXAMPLE.md: Isaiah Odom (SUM-45) for Hunter Dubois
(HAR-46) and Bryce Strickland (HAR-41), after which our safeties' coverage is up from
48.5 to 66.0, 4 points behind Mesa Verde instead of 21.5.
"""

import asyncio
import json

import pytest
from starlette.testclient import TestClient

from agents import briefing, deadline, league_db, memo, orders, rivals, saves, tools
from agents import trade_desk as desk
from agents.tools import load_league
from ui.server import app


def set_week(week: int) -> None:
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


def trade_for_odom() -> None:
    pid = desk.propose("HAR", ["HAR-46", "HAR-41"], "SUM", ["SUM-45"])["proposal"]["id"]
    assert desk.respond(pid, "SUM", "accept")["accepted"]


def protect(*player_ids: str) -> int:
    terms = orders.OrderTerms(summary="Keep them.", wants_trades=False, positions=[], max_incoming_salary=None,
                              max_added_payroll=None, protected_player_ids=list(player_ids))
    return orders.save_order("Keep them.", orders.ground_terms(terms, load_league()))


# ---- Where the season is ---------------------------------------------------------------

def test_the_deadline_phases():
    assert [deadline.phase(w, 9) for w in (1, 6, 7, 8, 9, 10, 17)] == [
        "open", "open", "approaching", "approaching", "deadline_week", "closed", "closed"]


def test_comparisons_match_the_league_office(scratch_db):
    ours = [{k: v for k, v in r.items() if k != "averages"} for r in deadline.comparisons(load_league())]
    assert ours == json.loads(tools.compare_to_league("HAR"))["comparisons"]


def test_the_deadline_card_two_weeks_out(scratch_db):
    set_week(7)
    st = deadline.status()
    assert (st["phase"], st["weeks_left_after_this_one"], st["cap_space"]) == ("approaching", 2, 5.52)
    assert st["weakness"] == {"position": "S", "unit": "safety coverage", "rank": "6th of 6",
                              "our_rating": 48.5, "league_average": 71.8}
    assert (st["trades"], st["since"], st["worked"]) == ([], [], None)


# ---- What our trades changed -----------------------------------------------------------------

def test_since_the_odom_trade(scratch_db):
    trade_for_odom()
    assert deadline.our_trades() == [
        "Week 1: Isaiah Odom (S) from Summit for Hunter Dubois (S) and Bryce Strickland (CB)"]
    assert deadline.since_our_trades() == [{
        "unit": "safety coverage", "position": "S", "before": 48.5, "now": 66.0,
        "rank_before": "6th of 6", "rank_now": "6th of 6",
        "against": {"team": "Mesa Verde", "before": "21.5 behind", "now": "4.0 behind"}}]


def test_rival_trades_dont_count_as_ours(scratch_db):
    made = desk.propose("MES", ["MES-44"], "LAK", ["LAK-44"])
    desk.respond(made["proposal"]["id"], "LAK", "accept")
    assert deadline.our_trades() == [] and deadline.since_our_trades() == []


def test_the_briefing_warns_and_can_say_what_the_trade_did(scratch_db):
    set_week(8)
    assert deadline.briefing_facts()["trade_deadline"] == {
        "after_week": 9, "weeks_left_after_this_one": 1, "warning": "The trade deadline is close."}
    set_week(9)
    trade_for_odom()
    facts = deadline.briefing_facts()
    assert facts["trade_deadline"]["warning"].startswith("Last chance to trade")
    assert facts["our_trades"][0].startswith("Week 9: Isaiah Odom (S) from Summit")
    # The example's sentence passes G3's number check against these facts.
    text = ("Since the Odom trade, our safeties' coverage is up from 48.5 to 66.0. That's still 6th of 6, "
            "but now 4 points behind Mesa Verde instead of 21.5. The Trade Desk closes after week 9.")
    assert memo.unknown_numbers(text, facts) == []
    set_week(10)
    assert deadline.briefing_facts()["trade_deadline"] == "passed"


def test_the_weekly_facts_carry_them(scratch_db):
    trade_for_odom()
    facts = briefing.facts()
    assert facts["trade_deadline"] == {"after_week": 9, "weeks_left_after_this_one": 8}  # no warning yet
    assert facts["since_our_trades"][0]["now"] == 66.0 and len(facts["our_trades"]) == 1


def test_the_briefing_skill_says_how_to_use_it():
    assert "since_our_trades" in " ".join(briefing.INSTRUCTIONS)


# ---- Working the deadline -------------------------------------------------------------------

def test_the_rules_work_the_deadline(scratch_db):
    set_week(7)
    result = asyncio.run(deadline.work(use_model=False))
    assert result["by"] == "rules" and result["cost"] is None
    order = result["order"]
    assert order["text"] == "Work the deadline: upgrade safety coverage (S) before trades close after week 9."
    assert order["terms"]["positions"] == ["S"]
    moves = result["moves"]
    assert len(moves) == orders.MAX_PROPOSALS
    assert len({m["sends"][0] for m in moves}) == len({m["receives"][0] for m in moves}) == len(moves)
    league = {p["id"]: p for p in load_league()["players"]}
    for m in moves:
        assert league[m["receives"][0]]["position"] == "S" and m["problems_now"] == []
        theirs = desk.evaluate(desk.rules.Trade("HAR", m["sends"], m["team_id"], m["receives"]))["teams"]
        assert theirs[m["team_id"]]["appraisal"]["verdict"] == "accept"  # they'll say yes
        assert theirs["HAR"]["appraisal"]["verdict"] == "accept"         # and it's worth it to us
        assert "would start for us" in m["reason"]
    assert deadline.status()["worked"]["order_id"] == order["id"]

    # The owner approves one, and the rival's GM takes it.
    sent = orders.approve(moves[0]["id"])
    assert rivals.answer_by_rules(sent["move"]["desk_proposal_id"])["decision"] == "accept"
    assert len(deadline.status()["trades"]) == 1


def test_the_deadline_search_keeps_standing_orders(scratch_db):
    set_week(8)
    first = asyncio.run(deadline.work(use_model=False))["moves"]
    sent = [m["sends"][0] for m in first]
    for m in first:
        orders.veto(m["id"])
    protect(*sent)
    again = asyncio.run(deadline.work(use_model=False))["moves"]
    assert not {m["sends"][0] for m in again} & set(sent)


def test_the_gms_search_gets_the_deadline_order(scratch_db):
    set_week(9)
    seen = []

    async def searcher(order, standing, league, week):
        seen.append((order["terms"]["positions"], week))
        return "Nothing worth doing.", None
    result = asyncio.run(deadline.work(use_model=True, searcher=searcher))
    assert seen == [(["S"], 9)] and result["reply"] == "Nothing worth doing."


@pytest.mark.parametrize("week, message", [(3, "works it from week 7"), (10, "Trades closed after week 9")])
def test_only_in_the_deadline_window(scratch_db, week, message):
    set_week(week)
    with pytest.raises(orders.OrderError, match=message):
        asyncio.run(deadline.work(use_model=False))


def test_past_the_deadline_the_desk_closes(scratch_db):
    set_week(9)
    moves = asyncio.run(deadline.work(use_model=False))["moves"]
    set_week(10)
    [news] = deadline.close()
    assert news == ("The trade deadline has passed: trades are closed for the season. "
                    f"{len(moves)} moves waiting for you went with it.")
    assert {m["status"] for m in orders.moves()} == {"void"}
    assert orders.moves()[0]["owner_note"] == "The trade deadline passed: trades closed after week 9."
    set_week(11)
    assert deadline.close() == []


# ---- In the game -------------------------------------------------------------------------

@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_the_deadline_in_the_game(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client.post("/api/saves/new", json={"name": "deadline", "seed": "1"})
    assert client.get("/api/hub").json()["deadline"]["phase"] == "open"
    assert "works it from week 7" in client.post("/api/hub/deadline", json={}).json()["error"]

    for week in range(1, 9):  # play up to the deadline week
        client.post("/api/hub/play", json={})
        client.post("/api/hub/advance", json={})
    worked = client.post("/api/hub/deadline", json={}).json()  # no key: the rules' search
    assert worked["by"] == "rules" and worked["moves"]
    hub = client.get("/api/hub").json()
    assert hub["deadline"]["phase"] == "deadline_week" and hub["desk"]["waiting"] == len(worked["moves"])

    client.post("/api/hub/play", json={})
    news = client.post("/api/hub/advance", json={}).json()["news"]
    assert any(line.startswith("The trade deadline has passed") for line in news)
    hub = client.get("/api/hub").json()
    assert hub["deadline"]["phase"] == "closed" and hub["desk"]["waiting"] == 0
    assert "Work the deadline" in client.get("/").text
