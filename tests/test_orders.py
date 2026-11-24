"""Checks for the owner's orders and approvals (task G4). No API key needed: the GM's
reading and search are replaced by stand-ins, and everything they would hand to plain
Python is checked here.

The order is the one from GAMEPLAY_EXAMPLE.md: "Upgrade safety. Stay under $5M a
year. Don't trade Okafor."
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from agno.tools.mcp import MCPTools
from starlette.testclient import TestClient

from agents import league_db, orders, rules, saves
from agents import trade_desk as desk
from agents.orders import MoveRefused, OrderError, OrderTerms
from agents.tools import load_league
from ui.server import app

EXAMPLE = "Upgrade safety. Stay under $5M a year. Don't trade Okafor."


def terms(**changes) -> OrderTerms:
    base = dict(summary="Upgrade safety with players under $5M a year, and keep Mateo Okafor.",
                wants_trades=True, positions=["S"], max_incoming_salary=5.0, max_added_payroll=None,
                protected_player_ids=["HAR-01"])
    return OrderTerms(**{**base, **changes})


def an_order(text: str = EXAMPLE, **changes) -> int:
    return orders.save_order(text, orders.ground_terms(terms(**changes), load_league()))


def set_week(week: int) -> None:
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


class Reader:
    """Stands in for the GM reading an order: returns the given terms (None = nothing parsed)."""

    def __init__(self, *results):
        self.results, self.prompts = list(results), []

    async def arun(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.results.pop(0), metrics=SimpleNamespace(
            input_tokens=100, output_tokens=20, cost=0.0001))


# ---- Reading the order ------------------------------------------------------------

def test_terms_are_grounded_in_the_league(scratch_db):
    grounded = orders.ground_terms(terms(positions=["s", "Safety", "cb", "S"], max_incoming_salary=-3,
                                         max_added_payroll=3.456, protected_player_ids=["har-01", "SUM-45", "X"]),
                                   load_league())
    assert grounded["positions"] == ["S", "CB"]                 # real codes only, once each
    assert grounded["protected_player_ids"] == ["HAR-01"]       # only our own players can be protected
    assert grounded["protected"] == ["Mateo Okafor (HAR-01)"]
    assert (grounded["max_incoming_salary"], grounded["max_added_payroll"]) == (None, 3.46)


def test_the_reader_sees_our_roster_and_retries(scratch_db):
    reader = Reader(None, terms())
    read, usage = asyncio.run(orders.read_order(EXAMPLE, load_league(), reader))
    assert read.protected_player_ids == ["HAR-01"] and len(usage) == 2
    assert "HAR-01 Mateo Okafor (QB)" in reader.prompts[0] and EXAMPLE in reader.prompts[0]
    with pytest.raises(OrderError, match="couldn't read that order"):
        asyncio.run(orders.read_order(EXAMPLE, load_league(), Reader(None, None)))


# ---- Checking moves against the rules and the orders --------------------------------

def test_a_move_must_follow_the_rules_and_the_order(scratch_db):
    oid = an_order()
    problems, _ = orders.check_move(oid, "LAK", ["HAR-46"], ["LAK-43"])   # Brennan
    assert problems == ["HAR's payroll would be $258.35M, $3.35M over the $255.0M hard cap.",
                        "Wade Brennan earns $9.87M, over the order's $5.00M limit."]
    problems, _ = orders.check_move(oid, "SUM", ["HAR-01"], ["SUM-45"])
    assert problems == [f"Mateo Okafor (HAR-01) can't be traded: your order #{oid} (\"{EXAMPLE}\") protects him."]
    problems, _ = orders.check_move(oid, "SUM", ["HAR-41"], ["SUM-01"])
    assert any("this move brings in nobody there" in p for p in problems)
    assert orders.check_move(oid, "HAR", [], ["SUM-45"])[0][0].startswith("A move needs another team")
    problems, evaluation = orders.check_move(oid, "SUM", ["HAR-46"], ["SUM-45"])
    assert problems == [] and evaluation["legal"]


def test_a_standing_order_protects_players_in_every_later_order(scratch_db):
    keep = an_order("Never trade Mateo Okafor.", wants_trades=False, positions=[], max_incoming_salary=None)
    later = an_order("Get us a quarterback.", positions=["QB"], max_incoming_salary=None, protected_player_ids=[])
    problems, _ = orders.check_move(later, "MES", ["HAR-01"], ["MES-01"])
    assert any(f"your order #{keep}" in p for p in problems)
    orders.cancel_order(keep)
    assert not any("protects him" in p for p in orders.check_move(later, "MES", ["HAR-01"], ["MES-01"])[0])


def test_payroll_limit(scratch_db):
    oid = an_order(max_incoming_salary=None, max_added_payroll=3.0)
    problems, _ = orders.check_move(oid, "SUM", ["HAR-46"], ["SUM-45"])   # +3.46M
    assert problems == ["Our payroll would grow $3.46M, over the order's $3.00M limit."]
    assert orders.check_move(oid, "SUM", ["HAR-46", "HAR-41"], ["SUM-45"])[0] == []   # +2.38M


def test_filing_moves(scratch_db):
    oid = an_order()
    with pytest.raises(MoveRefused) as refused:
        orders.file_move(oid, "LAK", ["HAR-46"], ["LAK-43"], "Brennan covers 88.")
    assert len(refused.value.problems) == 2
    with pytest.raises(MoveRefused, match="reason"):
        orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "  ")
    first = orders.file_move(oid, "sum", ["har-46"], ["sum-45"], "Odom covers 80.")
    with pytest.raises(MoveRefused, match=f"Move #{first} already proposes"):
        orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Again.")
    orders.file_move(oid, "DEL", ["HAR-45"], ["DEL-45"], "Pruitt covers 76.")
    orders.file_move(oid, "IRN", ["HAR-45"], ["IRN-46"], "Dubois covers 65.")
    with pytest.raises(MoveRefused, match="already proposed 3 moves"):
        orders.file_move(oid, "MES", ["HAR-45"], ["MES-44"], "Sato covers 68.")
    assert rules.move_log() == [] and desk.proposals(status="all") == []   # nothing left the building


def test_the_owner_sees_the_evaluation(scratch_db):
    oid = an_order()
    orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    view = orders.desk_view()
    assert view["waiting"] == 1 and [o["id"] for o in view["orders"]] == [oid]
    move = view["moves"][0]
    assert (move["status"], move["order"], move["problems_now"]) == ("waiting", EXAMPLE, [])
    ev = move["evaluation"]
    assert (ev["cap_space_after"], ev["roster_after"], ev["salary_change"]) == (2.06, 48, 3.46)
    assert ev["new_starters"] == [{"id": "SUM-45", "name": "Isaiah Odom"}]
    assert ev["benched"] == [{"id": "HAR-44", "name": "Nikola Kowalski"}]
    assert ev["unit_changes"][0]["unit"] == "deep_coverage"


# ---- The owner decides ---------------------------------------------------------------

def test_approving_sends_our_offer_to_the_trade_desk(scratch_db):
    oid = an_order()
    mid = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    result = orders.approve(mid, "Go.")
    assert result["sent"]
    move = result["move"]
    assert (move["status"], move["owner_note"], move["offer"]["status"]) == ("approved", "Go.", "open")
    offer = desk.proposal(move["desk_proposal_id"])
    assert (offer["from_team_id"], offer["to_team_id"], offer["note"]) == ("HAR", "SUM", "Odom covers 80.")
    assert rules.move_log() == []   # Summit hasn't answered: nothing has moved
    with pytest.raises(OrderError, match="is approved, not waiting"):
        orders.approve(mid)
    # When Summit accepts on the desk (2.2's rival GM, or the bench), the owner sees it.
    desk.respond(offer["id"], "SUM", "accept", "Deal.")
    done = orders.move(mid)
    assert done["offer"] == {"status": "accepted", "response": "Deal."}
    assert [p["name"] for p in done["gets"]] == ["Isaiah Odom"]


def test_veto_and_cancel(scratch_db):
    oid = an_order()
    a = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    b = orders.file_move(oid, "DEL", ["HAR-45"], ["DEL-45"], "Pruitt covers 76.")
    assert orders.veto(a, "Not Odom.")["move"]["status"] == "vetoed"
    cancelled = orders.cancel_order(oid)
    assert cancelled["status"] == "cancelled" and orders.orders() == []
    assert orders.move(b)["status"] == "void" and orders.move(b)["owner_note"] == "You cancelled the order."
    assert orders.move(a)["status"] == "vetoed"   # a decision stays as it was
    with pytest.raises(OrderError, match="already cancelled"):
        orders.cancel_order(oid)
    with pytest.raises(OrderError, match="no order #9"):
        orders.cancel_order(9)


def test_a_move_that_no_longer_passes_is_void_when_approved(scratch_db):
    oid = an_order()
    mid = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    set_week(10)
    assert orders.move(mid)["problems_now"][0].startswith("Trades closed after week 9")
    result = orders.approve(mid)
    assert not result["sent"] and result["move"]["status"] == "void"
    assert result["move"]["owner_note"].startswith("No longer passes: Trades closed")
    assert desk.proposals(status="all") == []


def test_a_new_standing_order_can_void_a_waiting_move(scratch_db):
    oid = an_order(protected_player_ids=[])
    mid = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    an_order("Keep Hunter Dubois.", wants_trades=False, positions=[], max_incoming_salary=None,
             protected_player_ids=["HAR-46"])
    assert not orders.approve(mid)["sent"] and "protects him" in orders.move(mid)["owner_note"]


# ---- Giving an order ------------------------------------------------------------------

def test_give_order_files_the_gms_moves(scratch_db):
    async def searcher(order, standing, league, week):
        assert order["terms"]["protected"] == ["Mateo Okafor (HAR-01)"] and week == 1
        orders.file_move(order["id"], "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
        return "I found one: Odom from Summit.", None
    result = asyncio.run(orders.give_order(f"  {EXAMPLE} ", reader=Reader(terms()), searcher=searcher))
    assert result["reply"] == "I found one: Odom from Summit."
    assert result["order"]["text"] == EXAMPLE and result["order"]["reply"] == result["reply"]
    assert [m["team_id"] for m in result["moves"]] == ["SUM"] and result["cost"] == 0.0001


def test_a_rule_only_order_needs_no_search(scratch_db):
    async def searcher(*args):
        raise AssertionError("no search for an order that only sets a rule")
    result = asyncio.run(orders.give_order("Never trade Okafor.", reader=Reader(terms(
        summary="Never trade Mateo Okafor.", wants_trades=False, positions=[], max_incoming_salary=None)),
        searcher=searcher))
    assert result["reply"] == "Understood: Never trade Mateo Okafor. That stands until you cancel it."
    assert result["order"]["status"] == "active" and result["moves"] == []


def test_no_search_after_the_deadline(scratch_db):
    set_week(10)

    async def searcher(*args):
        raise AssertionError("no search after the deadline")
    result = asyncio.run(orders.give_order(EXAMPLE, reader=Reader(terms()), searcher=searcher))
    assert "trades closed after week 9" in result["reply"] and "The order still stands" in result["reply"]


def test_an_empty_order():
    with pytest.raises(OrderError, match="Type an order"):
        asyncio.run(orders.give_order("   "))


# ---- The GM's tools ----------------------------------------------------------------

def test_propose_to_owner_reports_problems_to_the_gm(scratch_db):
    oid = an_order()
    [propose] = orders.build_tools(oid)
    refused = json.loads(propose("SUM", ["HAR-01"], ["SUM-45"], "Odom."))
    assert refused["filed"] is False and "protects him" in refused["problems"][0]
    filed = json.loads(propose("SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80."))
    assert filed == {"filed": True, "move_id": 1, "moves_left_for_this_order": 2}


def test_the_search_uses_read_tools_only():
    """The GM evaluates on the Trade Desk but can't propose there: only an approval does."""
    searcher = orders.build_searcher(orders.league_office_tools(), orders.trade_desk_tools(), order_id=1)
    mcp = [t for t in searcher.tools if isinstance(t, MCPTools)]
    assert [t.include_tools for t in mcp] == [orders.LEAGUE_OFFICE_TOOLS, ["evaluate_trade"]]
    # Finding targets is Scouting's job (4.1): the GM only files moves.
    assert [t.__name__ for t in searcher.tools if not isinstance(t, MCPTools)] == ["propose_to_owner"]
    assert searcher.tool_call_limit == orders.SEARCH_TOOL_LIMIT
    # The memo skill's rules for writing to the owner are always on, as for the GM's answers.
    assert any(i.startswith("How to answer the owner:\n") for i in searcher.instructions)
    assert "propose_trade" not in orders.TRADE_DESK_TOOLS


def test_search_prompt_names_standing_orders(scratch_db):
    keep = an_order("Never trade Mateo Okafor.", wants_trades=False, positions=[], max_incoming_salary=None)
    oid = an_order()
    standing = orders.orders()
    prompt = orders.search_prompt(next(o for o in standing if o["id"] == oid), standing, load_league(), 3)
    assert "It is week 3; trades close after week 9." in prompt
    assert "Our payroll is $249.48M, cap space $5.52M." in prompt
    assert f"#{keep}: \"Never trade Mateo Okafor.\" (protects Mateo Okafor (HAR-01))" in prompt


# ---- Storage and the game's API -----------------------------------------------------------

def test_trade_desk_saves_get_the_orders_tables(tmp_path):
    import sqlite3
    path = tmp_path / "v5.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:  # turn it back into a 2.1 (schema 5) database
        db.executescript("DROP TABLE gm_proposals; DROP TABLE orders; PRAGMA user_version = 5;")
    db.close()
    assert orders.orders(db_file=path) == []
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()


@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_orders_and_approvals_in_the_game(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert "Start or load" in client.post("/api/hub/order", json={"order": EXAMPLE}).json()["error"]
    client.post("/api/saves/new", json={"name": "ordering", "seed": "1"})
    assert client.get("/api/hub").json()["desk"] == {"orders": [], "moves": [], "waiting": 0}
    assert "OPENROUTER_API_KEY" in client.post("/api/hub/order", json={"order": EXAMPLE}).json()["error"]

    # What the GM would have done, then the owner's decisions over the API (no key needed).
    oid = an_order()
    a = orders.file_move(oid, "SUM", ["HAR-46"], ["SUM-45"], "Odom covers 80.")
    b = orders.file_move(oid, "DEL", ["HAR-45"], ["DEL-45"], "Pruitt covers 76.")
    desk_view = client.get("/api/hub").json()["desk"]
    assert desk_view["waiting"] == 2 and desk_view["orders"][0]["text"] == EXAMPLE
    sent = client.post("/api/hub/move/approve", json={"move_id": a}).json()
    assert sent["sent"] and sent["move"]["offer"]["status"] == "open"
    assert client.post("/api/hub/move/veto", json={"move_id": b, "note": "No."}).json()["move"]["status"] == "vetoed"
    assert "not waiting" in client.post("/api/hub/move/veto", json={"move_id": b}).json()["error"]
    assert client.post("/api/hub/order/cancel", json={"order_id": oid}).json()["status"] == "cancelled"
    assert client.get("/api/hub").json()["desk"]["orders"] == []
    assert "Give an order" in client.get("/").text and "data-approve" in client.get("/").text


def test_the_search_knows_each_teams_name(scratch_db):
    """Without the names the GM guessed them from the ids ("Delaware" for DEL)."""
    oid = an_order()
    order = next(o for o in orders.orders() if o["id"] == oid)
    prompt = orders.search_prompt(order, [order], load_league(), 7)
    assert "DEL = Delta Bay Gators" in prompt and "SUM = Summit Sherpas" in prompt


def test_the_reply_is_the_gms_last_message():
    """Not the notes it wrote between tool calls, which the run's content runs together."""
    msg = lambda role, content: SimpleNamespace(role=role, content=content)
    run = SimpleNamespace(content="Let me check the roster.Here is my answer.", messages=[
        msg("user", "the order"), msg("assistant", "Let me check the roster."), msg("tool", "{}"),
        msg("assistant", "Here is my answer."), msg("tool", "{}"), msg("assistant", None)])
    assert orders.final_message(run) == "Here is my answer."
    assert orders.final_message(SimpleNamespace(content=" Only this. ", messages=[])) == "Only this."
