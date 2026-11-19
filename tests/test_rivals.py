"""Checks for the rival GMs (task 2.2) and what they do between weeks (task G5). No
API key needed: where a rival's GM would answer with the model, a stand-in does.

The offer is the one from GAMEPLAY_EXAMPLE.md: Dubois (HAR-46) for Odom (SUM-45).
Summit scores it -2.35 and counters, asking for Jalen Gaines (HAR-24) as well.
"""

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from agents import league_db, negotiation, orders, rivals, rules, saves, skills
from agents import trade_desk as desk
from agents.tools import load_league
from ui.server import app

ODOM = (["HAR-46"], ["SUM-45"])              # we send Dubois, we get Odom
ODOM_AND_GAINES = (["HAR-46", "HAR-24"], ["SUM-45"])
FOR_THEIR_KICKER = (["HAR-46"], ["SUM-47"])  # Dubois for Summit's 78-overall kicker: no chance


def offer(sends_gets=ODOM, to="SUM") -> int:
    sends, gets = sends_gets
    made = desk.propose("HAR", sends, to, gets)
    assert made["proposed"], made
    return made["proposal"]["id"]


def set_week(week: int, db_file=None) -> None:
    db = league_db.connect(db_file)
    with db:
        db.execute("UPDATE game SET current_week = ?", (week,))
    db.close()


class RivalGM:
    """Stands in for a rival's GM: returns the given decision."""

    def __init__(self, decision, option=None, message="Fine by us."):
        self.content = rivals.RivalDecision(decision=decision, option=option, message=message)
        self.prompts = []

    async def arun(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.content, metrics=SimpleNamespace(
            input_tokens=300, output_tokens=40, cost=0.0002))


# ---- The appraisal: how every GM scores a trade ----------------------------------------

def test_the_appraisal_formula_and_verdicts():
    side = {"market_value_change": 4.08, "salary_change": 3.46,
            "unit_changes": [{"unit": "deep_coverage", "change": 9.63}, {"unit": "tackling", "change": 50}]}
    ours = negotiation.appraise(side)
    assert ours["score"] == round(4.08 - 0.5 * 3.46 + 0.3 * 9.63, 2) == 5.24   # tackling doesn't count
    assert (ours["margin"], ours["verdict"]) == (0.25, "accept")
    theirs = negotiation.appraise({"market_value_change": -4.08, "salary_change": -3.46, "unit_changes": []})
    assert (theirs["score"], theirs["verdict"]) == (-2.35, "counter")
    assert negotiation.appraise({"market_value_change": -10, "salary_change": 0, "unit_changes": []})["verdict"] == "reject"
    assert negotiation.appraise(side, "hard")["margin"] == 1.0


def test_evaluate_gives_each_side_its_appraisal(scratch_db):
    ev = desk.evaluate(rules.Trade("HAR", *ODOM[:1], "SUM", ODOM[1]))
    assert ev["teams"]["HAR"]["appraisal"]["verdict"] == "accept"
    assert ev["teams"]["SUM"]["appraisal"] == {
        "score": -2.35, "margin": 0.25, "verdict": "counter",
        "parts": {"market_value_change": -4.08, "salary_change": -3.46, "unit_points": 0}}
    assert "appraisal" in ev["note"]


def test_the_negotiation_skill_script_matches():
    folder = skills.SKILLS_DIR / "negotiation"
    run = subprocess.run([sys.executable, "scripts/appraise.py", "--market-value-change", "-4.08",
                          "--salary-change", "-3.46"], cwd=folder, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {"score": -2.35, "margin": 0.25, "verdict": "counter",
                                           "parts": {"market_value_change": -4.08, "salary_change": -3.46,
                                                     "unit_points": 0}}


def test_our_gms_search_has_the_negotiation_skill():
    searcher = orders.build_searcher(orders.league_office_tools(), orders.trade_desk_tools(), order_id=1)
    assert "negotiation" in [s.name for s in searcher.skills.get_all_skills()]
    assert any("appraisal" in i for i in searcher.instructions)


# ---- Counteroffers and the rules' answer ----------------------------------------------------

def test_counter_options_ask_for_one_more_player(scratch_db):
    options = rivals.counter_options(load_league(), "HAR", ["HAR-46"], "SUM", ["SUM-45"])
    assert len(options) == rivals.COUNTER_OPTIONS
    first = options[0]
    assert (first["add"]["id"], first["rival_score"], first["proposer_score"]) == ("HAR-24", 0.28, 2.11)
    assert all(o["rival_score"] >= negotiation.margin() for o in options)       # each one they'd take
    assert len({o["add"]["id"] for o in options}) == len(options) and "HAR-46" not in {o["add"]["id"] for o in options}


def test_the_policy():
    accept = {"score": 1.0, "margin": 0.25, "verdict": "accept"}
    short = {"score": -2.35, "margin": 0.25, "verdict": "counter"}
    hopeless = {"score": -18.0, "margin": 0.25, "verdict": "reject"}
    some = [{"add": {"name": "A", "position": "DL"}, "rival_score": 0.3, "proposer_score": 2}]
    assert rivals.policy(accept, some) == ("accept", None)
    assert rivals.policy(short, some) == ("counter", 0)
    assert rivals.policy(short, []) == ("reject", None)       # nothing to ask for
    assert rivals.policy(hopeless, some) == ("reject", None)
    assert rivals.policy_message("counter", some[0]) == "Close. Add A (DL) and you have a deal."


def test_summit_counters_dubois_for_odom(scratch_db):
    pid = offer()
    answer = rivals.answer_by_rules(pid)
    assert (answer["decision"], answer["by"], answer["message"]) == (
        "counter", "rules", "Close. Add Jalen Gaines (DL) and you have a deal.")
    counter = answer["counter"]
    assert (counter["from_team_id"], counter["to_team_id"], counter["counter_of"]) == ("SUM", "HAR", pid)
    assert [p["id"] for p in counter["receives"]] == ["HAR-46", "HAR-24"]
    assert desk.proposal(pid)["status"] == "countered"


def test_a_good_enough_offer_is_accepted(scratch_db):
    answer = rivals.answer_by_rules(offer(ODOM_AND_GAINES))
    assert answer["decision"] == "accept" and answer["trade"]["move_id"]
    assert {p["id"]: p["team_id"] for p in load_league()["players"] if p["id"] in ("SUM-45", "HAR-24")} == \
        {"SUM-45": "HAR", "HAR-24": "SUM"}


def test_a_hopeless_offer_is_rejected(scratch_db):
    pid = offer(FOR_THEIR_KICKER)
    answer = rivals.answer_by_rules(pid)
    assert answer["decision"] == "reject" and answer["appraisal"]["score"] < negotiation.REJECT_BELOW
    assert desk.proposal(pid)["status"] == "rejected"


def test_an_offer_the_rules_now_refuse_is_rejected(scratch_db):
    pid = offer()
    set_week(load_league()["rules"]["trade_deadline_week"] + 1)
    answer = rivals.answer_by_rules(pid)
    assert answer["decision"] == "reject" and "rules" in answer["message"]


def test_only_rivals_answer_and_only_open_offers(scratch_db):
    to_us = desk.propose("SUM", ["SUM-45"], "HAR", ["HAR-46"])["proposal"]["id"]
    with pytest.raises(orders.OrderError, match="the owner answers it"):
        rivals.answer_by_rules(to_us)
    pid = offer()
    rivals.answer_by_rules(pid)
    with pytest.raises(orders.OrderError, match="not open"):
        rivals.answer_by_rules(pid)


# ---- The rival's GM decides, within the limits ------------------------------------------------

def test_the_model_answers_within_the_limits(scratch_db):
    pid = offer()
    gm = RivalGM("counter", option=2, message="Throw in Kofi Strickland and it's done.")
    answer = asyncio.run(rivals.answer_offer(pid, agent=gm))
    assert (answer["decision"], answer["by"], answer["message"]) == (
        "counter", "model", "Throw in Kofi Strickland and it's done.")
    assert [p["id"] for p in answer["counter"]["receives"]] == ["HAR-46", "HAR-06"]  # the second option
    assert answer["cost"] == 0.0002
    prompt = gm.prompts[0]
    assert "accept (NOT allowed" in prompt and "counter 1: ask for Jalen Gaines" in prompt
    assert "Your front office's score: -2.35" in prompt


@pytest.mark.parametrize("decision, option", [("accept", None), ("counter", 4), ("counter", None)])
def test_a_model_answer_outside_the_limits_falls_back_to_the_rules(scratch_db, decision, option):
    pid = offer()
    answer = asyncio.run(rivals.answer_offer(pid, agent=RivalGM(decision, option)))
    assert (answer["decision"], answer["by"]) == ("counter", "rules")  # the rules' answer, not the model's
    assert answer["message"] == "Close. Add Jalen Gaines (DL) and you have a deal."


def test_the_model_may_say_no_to_anything(scratch_db):
    pid = offer(ODOM_AND_GAINES)
    answer = asyncio.run(rivals.answer_offer(pid, agent=RivalGM("reject", message="Not this year.")))
    assert (answer["decision"], answer["by"], answer["message"]) == ("reject", "model", "Not this year.")


def test_without_the_model_the_rules_answer(scratch_db):
    answer = asyncio.run(rivals.answer_offer(offer(), use_model=False))
    assert (answer["decision"], answer["by"], answer["cost"]) == ("counter", "rules", None)


# ---- Offers to us --------------------------------------------------------------------------

def test_an_offer_to_us_comes_with_our_gms_read(scratch_db):
    pid = desk.propose("SUM", ["SUM-45"], "HAR", ["HAR-46", "HAR-24"], "Odom for two.")["proposal"]["id"]
    [item] = rivals.offers_to_us()
    assert item["id"] == pid and item["legal_now"] and item["clashes"] == []
    assert item["appraisal"]["score"] == 2.11
    assert item["advice"].startswith("By the league's measure it's worth +2.11 to us: I'd take it.")
    assert [p["id"] for p in item["evaluation"]["gets"]] == ["SUM-45"]
    assert item["evaluation"]["new_starters"][0]["name"] == "Isaiah Odom"


def test_our_gm_warns_when_an_offer_breaks_an_order(scratch_db):
    terms = orders.OrderTerms(summary="Keep Jalen Gaines.", wants_trades=False, positions=[],
                              max_incoming_salary=None, max_added_payroll=None, protected_player_ids=["HAR-24"])
    oid = orders.save_order("Never trade Jalen Gaines.", orders.ground_terms(terms, load_league()))
    desk.propose("SUM", ["SUM-45"], "HAR", ["HAR-46", "HAR-24"])
    [item] = rivals.offers_to_us()
    assert item["clashes"] == [f"Jalen Gaines (HAR-24) is protected by your order #{oid} "
                               "(\"Never trade Jalen Gaines.\")."]
    assert "I'd take it" not in item["advice"] and "breaks your orders" in item["advice"]


def test_the_owner_accepts_or_rejects(scratch_db):
    a = desk.propose("SUM", ["SUM-45"], "HAR", ["HAR-46", "HAR-24"])["proposal"]["id"]
    assert rivals.accept_offer(a)["accepted"]
    assert {p["id"]: p["team_id"] for p in load_league()["players"]}["SUM-45"] == "HAR"
    b = desk.propose("LAK", ["LAK-47"], "HAR", ["HAR-47"])["proposal"]["id"]
    assert rivals.reject_offer(b, "No thanks.")["proposal"]["status"] == "rejected"
    assert rivals.offers_to_us() == []


# ---- Between weeks ------------------------------------------------------------------------

def _season(db_file, weeks=6):
    out = []
    for week in range(2, weeks + 1):
        set_week(week, db_file)
        out.append(rivals.between_weeks(db_file))
    return out


def test_the_league_moves_on_its_own_and_the_same_seed_moves_it_the_same_way(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    league_db.build(a, season_seed=11)
    league_db.build(b, season_seed=11)
    first, second = _season(a), _season(b)
    assert first == second
    news = [line for week in first for line in week["news"]]
    assert any(" traded " in line for line in news)          # rivals trade with each other
    assert any("made us an offer" in line for line in news)  # and make us offers
    assert rules.move_log(a) and len(rules.move_log(a)) == len(rules.move_log(b))
    for move in rules.move_log(a):  # trades between rivals only: we're never traded without the owner
        assert "HAR" not in {p["from_team_id"] for p in move["players"]} | {p["to_team_id"] for p in move["players"]}


def test_offers_to_us_expire_and_never_repeat(tmp_path):
    db_file = tmp_path / "s.db"
    league_db.build(db_file, season_seed=11)
    _season(db_file, 9)
    to_us = [o for o in desk.proposals("HAR", "all", db_file) if o["to_team_id"] == "HAR"]
    assert to_us
    asked = [(o["from_team_id"], p["id"]) for o in to_us for p in o["receives"]]
    assert len(asked) == len(set(asked))  # never the same player from the same team twice
    current = rivals._season(db_file)[0]
    for o in to_us:
        if o["week"] < current:
            assert o["status"] == "withdrawn" and o["response"] == f"The offer expired at the end of week {o['week']}."


def test_between_weeks_answers_our_open_offers(scratch_db):
    pid = offer()
    set_week(2)
    news = rivals.between_weeks()["news"]
    assert f"Summit answered our offer #{pid}: counter." in news
    assert desk.proposal(pid)["status"] == "countered"


def test_no_trades_after_the_deadline(scratch_db):
    set_week(load_league()["rules"]["trade_deadline_week"] + 1)
    assert rivals.between_weeks()["news"] == []
    assert rules.move_log() == [] and desk.proposals(None, "all") == []


def test_news_lists_other_teams_trades_this_week(scratch_db):
    made = desk.propose("MES", ["MES-44"], "LAK", ["LAK-44"])
    desk.respond(made["proposal"]["id"], "LAK", "accept")
    [line] = rivals.news(1)
    assert line == "Lakeshore traded Dmitri Gaines (S) to Mesa Verde for Omar Sato (S)."
    assert rivals.news(2) == []
    desk.respond(offer(ODOM_AND_GAINES), "SUM", "accept")
    assert len(rivals.news(1)) == 1  # our own trades aren't news to us


# ---- In the game -------------------------------------------------------------------------

@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_rivals_in_the_game(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert "Start or load" in client.post("/api/hub/offer/answer", json={"proposal_id": 1}).json()["error"]
    client.post("/api/saves/new", json={"name": "rivals", "seed": "1"})
    hub = client.get("/api/hub").json()
    assert (hub["offers"], hub["news"]) == ([], [])

    # Our offer: without a key, the rules answer for Summit.
    answer = client.post("/api/hub/offer/answer", json={"proposal_id": offer()}).json()
    assert (answer["decision"], answer["by"]) == ("counter", "rules")
    [counter] = client.get("/api/hub").json()["offers"]
    assert counter["counter_of"] and counter["advice"].startswith("By the league's measure")
    assert client.post("/api/hub/offer/accept", json={"proposal_id": counter["id"]}).json()["accepted"]

    # An offer to us, turned down.
    pid = desk.propose("LAK", ["LAK-47"], "HAR", ["HAR-47"])["proposal"]["id"]
    assert client.post("/api/hub/offer/reject", json={"proposal_id": pid}).json()["proposal"]["status"] == "rejected"
    assert "not open" in client.post("/api/hub/offer/reject", json={"proposal_id": pid}).json()["error"]

    # Advancing the week lets the rivals move, and the page has the new parts.
    client.post("/api/hub/play", json={})
    advanced = client.post("/api/hub/advance", json={}).json()
    assert advanced["week"] == 2 and isinstance(advanced["news"], list)
    page = client.get("/").text
    assert "Offers to us" in page and "data-accept-offer" in page and "/api/hub/offer/answer" in page
