"""Checks for the scouting team (task 4.1). No API key needed: plain Python's scouting
and the rules' grades run as they are, and the scouts' model runs are stood in for."""

import asyncio
import importlib.util
import json
import sqlite3
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from agents import deadline, league_db, orders, saves, scouting, skills
from agents import trade_desk as desk
from agents.orders import OrderTerms
from agents.scouting import ScoutingReport, ScoutPick, ScoutReport
from agents.tools import load_league
from ui.server import app


def order_with(**changes) -> dict:
    base = dict(summary="Upgrade safety.", wants_trades=True, positions=["S"], max_incoming_salary=None,
                max_added_payroll=None, protected_player_ids=[])
    terms = OrderTerms(**{**base, **changes})
    oid = orders.save_order("Upgrade safety.", orders.ground_terms(terms, load_league()))
    return next(o for o in orders.orders() if o["id"] == oid)


def metrics(cost):
    return SimpleNamespace(cost=cost, input_tokens=100, output_tokens=20)


def run(content, members=(), cost=0.001, name="Scouting"):
    return SimpleNamespace(content=content, member_responses=list(members), metrics=metrics(cost), tools=[],
                           model="stand-in", messages=[], agent_name=None if name == "Scouting" else name,
                           team_name=name if name == "Scouting" else None)


class Team:
    """Stands in for the scouting team: returns a canned run and keeps the prompt."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.prompts = response, error, []

    async def arun(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response


# ---- What plain Python finds ---------------------------------------------------------------

def test_targets_are_players_who_would_start_for_us(scratch_db):
    found = scouting.targets("s")
    league = load_league()
    ours = sorted((p["overall"] for p in league["players"] if p["team_id"] == "HAR" and p["position"] == "S"),
                  reverse=True)
    assert found["position"] == "S" and found["would_start_above"] == ours[1]  # two safeties start
    assert [s["overall"] for s in found["our_starters"]] == ours[:2]
    players = found["players"]
    assert 0 < len(players) <= scouting.SCOUTED
    assert all(p["team_id"] != "HAR" and p["position"] == "S" and p["overall"] > ours[1] for p in players)
    assert all(p["unit_gain"] > 0 and "def_int" in p["season"] for p in players)
    # Offers first, best for us first; then the rest.
    with_offer = [p for p in players if p["offer"]]
    assert players[:len(with_offer)] == with_offer
    assert [p["offer"]["our_score"] for p in with_offer] == sorted((p["offer"]["our_score"] for p in with_offer),
                                                                   reverse=True)


def test_every_offer_is_one_their_team_takes_and_worth_it_to_us(scratch_db):
    for p in scouting.targets("S")["players"]:
        if not p["offer"]:
            continue
        send = p["offer"]["we_send"][0]["id"]
        teams = desk.evaluate(desk.rules.Trade("HAR", [send], p["team_id"], [p["id"]]))["teams"]
        assert teams[p["team_id"]]["appraisal"]["verdict"] == "accept"
        assert teams["HAR"]["appraisal"]["verdict"] == "accept"
        assert teams[p["team_id"]]["appraisal"]["score"] == p["offer"]["their_score"]


def test_targets_keep_the_orders_limits(scratch_db):
    free = scouting.targets("S")["players"]
    sent = {p["offer"]["we_send"][0]["id"] for p in free if p["offer"]}
    limited = scouting.targets("S", max_salary=5.0, protected=sent, max_added_payroll=0.5)["players"]
    assert all(p["salary"] <= 5.0 for p in limited)
    for p in limited:
        if p["offer"]:
            assert p["offer"]["we_send"][0]["id"] not in sent and p["offer"]["payroll_change"] <= 0.5


def test_a_hurt_target_is_flagged(scratch_db):
    target = scouting.targets("S")["players"][0]
    db = league_db.connect()
    with db:
        league_db.save_injury(db, target["id"], target["team_id"], 1, 3, "Hamstring.")
    db.close()
    hurt = next(p for p in scouting.targets("S")["players"] if p["id"] == target["id"])
    assert hurt["games_out"] > 0 and scouting.rules_grade(hurt) == "C"


def test_an_unknown_position(scratch_db):
    with pytest.raises(scouting.ScoutingError, match="Unknown position"):
        scouting.targets("PG")


def test_player_report(scratch_db):
    r = scouting.player_report("sum-45")
    assert r["name"] == "Isaiah Odom" and r["team"] == "Summit" and r["ratings"]["coverage"] == 80
    assert r["our_depth"][0]["overall"] >= r["our_depth"][-1]["overall"] and r["starters_per_team"] == 2
    with pytest.raises(scouting.ScoutingError, match="No player"):
        scouting.player_report("XYZ-99")


# ---- The rules' grades -----------------------------------------------------------------------

def grade_script():
    path = skills.SKILLS_DIR / "scouting" / "scripts" / "grade.py"
    spec = importlib.util.spec_from_file_location("grade", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("offer, games_out, expected", [
    ({"our_score": 1.5}, 0, "A"), ({"our_score": 0.4}, 0, "B"), (None, 0, "C"), ({"our_score": 2.0}, 2, "C")])
def test_the_rules_grade_as_the_skill_says(offer, games_out, expected):
    assert scouting.rules_grade({"offer": offer, "games_out": games_out}) == expected
    script = grade_script()
    assert script.grade(offer and offer["our_score"], games_out) == expected
    assert script.A_GRADE == scouting.A_GRADE


def test_the_rules_report(scratch_db):
    found = {"S": scouting.targets("S"), "CB": scouting.targets("CB", max_salary=0.5)}
    report = scouting.rules_report(found)
    assert report["by"] == "rules" and report["positions"] == ["S", "CB"] and report["cost"] is None
    assert len(report["targets"]) == min(scouting.SHORTLIST, len(found["S"]["players"]))
    assert report["summary"].startswith("Found ") and "safety target" in report["summary"]
    assert "no cornerback target under $0.50M who would start for us" in report["summary"]
    for t in report["targets"]:
        assert t["graded_by"] == "rules" and t["grade"] in "ABC" and "to our units" in t["note"]
    assert scouting.rules_report({"CB": found["CB"]})["summary"].startswith("No cornerback target")


# ---- Grounding the scouts' picks ------------------------------------------------------------

def test_ground_keeps_only_what_plain_python_found(scratch_db):
    found = {"S": scouting.targets("S"), "CB": scouting.targets("CB")}
    s = found["S"]["players"]
    no_offer = next((p for p in s if not p["offer"]), None)
    picks = [ScoutPick(player_id=s[1]["id"].lower(), grade="B", note="Second best."),
             ScoutPick(player_id="SUM-99", grade="A", note="Made up."),        # not a real target: dropped
             ScoutPick(player_id=s[1]["id"], grade="A", note="Again."),         # already graded: dropped
             ScoutPick(player_id=s[0]["id"], grade="A", note="The best.")]
    if no_offer:
        picks.append(ScoutPick(player_id=no_offer["id"], grade="A", note="Graded too high."))
    report = scouting.ground(picks, found, "Two safeties.")
    graded = [t for t in report["targets"] if t["position"] == "S"]
    assert [t["player_id"] for t in graded][:2] == [s[1]["id"], s[0]["id"]]
    assert graded[0]["grade"] == "B" and graded[0]["note"] == "Second best." and graded[0]["graded_by"] == "scouts"
    assert graded[0]["salary"] == s[1]["salary"] and graded[0]["offer"] == s[1]["offer"]  # plain Python's numbers
    if no_offer:
        assert next(t for t in graded if t["player_id"] == no_offer["id"])["grade"] == "C"  # held to the numbers
    # The scouts left cornerback empty though there are targets: the rules grade them.
    cbs = [t for t in report["targets"] if t["position"] == "CB"]
    assert cbs and all(t["graded_by"] == "rules" for t in cbs)
    assert report["summary"] == "Two safeties." and report["by"] == "scouts"


# ---- The team ---------------------------------------------------------------------------------

def test_the_scouting_team():
    team = scouting.build_scouting_team(max_salary=5.0)
    assert team.name == "Scouting" and not team.tools and team.output_schema is ScoutingReport
    assert team.tool_call_limit == scouting.DIRECTOR_DELEGATIONS and team.share_member_interactions
    offense, defense, draft = team.members
    assert (offense.name, defense.name, draft.name) == ("Pro scout, offense", "Pro scout, defense", "Draft")
    for scout in (offense, defense):
        assert [f.__name__ for f in scout.tools] == ["scout_targets", "scout_player"]
        assert scout.output_schema is ScoutReport and scout.parser_model is not None
        assert scout.tool_call_limit == scouting.SCOUT_TOOL_LIMIT
        assert any(i.startswith("How to grade:\n") for i in scout.instructions)


def test_a_scout_keeps_to_its_own_positions(scratch_db):
    targets, player = scouting.build_scout_tools(scouting.DEFENSE, max_salary=5.0)
    found = json.loads(targets("s"))
    assert found["position"] == "S" and all(p["salary"] <= 5.0 for p in found["players"])
    assert "another scout's" in json.loads(targets("QB"))["error"]
    assert json.loads(player("SUM-45"))["name"] == "Isaiah Odom" and "error" in json.loads(player("nope"))


# ---- Scouting for an order -------------------------------------------------------------------

def test_the_scouts_report_for_an_order(scratch_db):
    order = order_with(max_incoming_salary=8.0)
    best = scouting.targets("S", max_salary=8.0)["players"][0]
    scout = run(ScoutReport(summary="One safety.", picks=[ScoutPick(player_id=best["id"], grade="A", note="Fits.")]),
                cost=0.002, name="Pro scout, defense")
    team = Team(run(ScoutingReport(summary="Get him.", picks=[]), [scout]))
    usage = []
    report = asyncio.run(scouting.scout_for_order(order, orders.orders(), use_model=True, usage=usage, team=team))
    assert "trade targets at S" in team.prompts[0] and "$8.00M" in team.prompts[0]
    assert report["by"] == "scouts" and report["order_id"] == order["id"] and report["week"] == 1
    assert report["summary"] == "Get him." and report["targets"][0]["player_id"] == best["id"]
    assert report["cost"] == 0.003 and len(usage) == 2
    assert scouting.report_for_order(order["id"]) == report and scouting.reports(1) == [report]


def test_a_failed_scouting_run_leaves_the_rules_report(scratch_db):
    order = order_with()
    report = asyncio.run(scouting.scout_for_order(order, orders.orders(), team=Team(error=RuntimeError("timeout"))))
    assert report["by"] == "rules" and report["targets"] and "couldn't report: timeout" in report["summary"]


def test_an_order_with_no_position_scouts_our_weakest(scratch_db):
    order = order_with(positions=[])
    report = asyncio.run(scouting.scout_for_order(order, orders.orders(), use_model=False))
    assert len(report["positions"]) == scouting.WEAKEST and report["positions"][0] == "S"


def test_standing_orders_protect_players_from_the_offers(scratch_db):
    first = scouting.targets("S")["players"]
    sent = sorted({p["offer"]["we_send"][0]["id"] for p in first if p["offer"]})
    keep = OrderTerms(summary="Keep them.", wants_trades=False, positions=[], max_incoming_salary=None,
                      max_added_payroll=None, protected_player_ids=sent)
    orders.save_order("Keep them.", orders.ground_terms(keep, load_league()))
    report = asyncio.run(scouting.scout_for_order(order_with(), orders.orders(), use_model=False))
    assert not {t["offer"]["we_send"][0]["id"] for t in report["targets"] if t["offer"]} & set(sent)


def test_the_gm_works_from_scoutings_report(scratch_db):
    seen = []

    async def searcher(order, standing, league, week):
        seen.append(scouting.report_for_order(order["id"]))
        return "Done.", None
    result = asyncio.run(orders.work_order(order_with()["id"], searcher=searcher))
    assert result["scouting"] == seen[0] and seen[0]["by"] == "rules"  # a stand-in GM: the rules grade
    view = orders.desk_view()
    assert view["orders"][0]["scouting"]["id"] == result["scouting"]["id"]
    prompt = orders.search_prompt(result["order"], orders.orders(), load_league(), 1, result["scouting"])
    first = result["scouting"]["targets"][0]
    assert "Your scouting team's report: Found" in prompt and f"- {first['player_id']} " in prompt
    assert "Suggested offer " in prompt or "offer null" in prompt


def test_an_order_without_a_search_gets_no_scouting(scratch_db):
    order = order_with(wants_trades=False, positions=[])
    result = asyncio.run(orders.work_order(order["id"], searcher=None))
    assert result["scouting"] is None and scouting.reports() == []


def test_the_deadline_files_scoutings_offers(scratch_db):
    db = league_db.connect()
    with db:
        db.execute("UPDATE game SET current_week = 8")
    db.close()
    result = asyncio.run(deadline.work(use_model=False))
    report = scouting.report_for_order(result["order"]["id"])
    offered = {t["player_id"]: t for t in report["targets"] if t["offer"]}
    assert result["moves"] and all(m["receives"][0] in offered for m in result["moves"])
    for m in result["moves"]:
        assert m["sends"] == [offered[m["receives"][0]]["offer"]["we_send"][0]["id"]]
        assert f"Scouting grades him {offered[m['receives'][0]]['grade']}" in m["reason"]


# ---- Asking the scouting team (the test bench) and older saves ---------------------------------

def test_asking_the_scouting_team(scratch_db):
    best = scouting.targets("CB")["players"][0]
    scout = run(ScoutReport(summary="A corner.", picks=[ScoutPick(player_id=best["id"], grade="B", note="Good.")]),
                name="Pro scout, defense")
    out = asyncio.run(scouting.ask("Find us a corner.", team=Team(run(ScoutingReport(summary="Try him.", picks=[]),
                                                                      [scout]))))
    assert out["report"]["targets"][0]["player_id"] == best["id"] and out["report"]["summary"] == "Try him."
    assert out["consulted"] == ["Pro scout, defense"] and out["cost"] == pytest.approx(0.002)
    with pytest.raises(ValueError, match="Type a question"):
        asyncio.run(scouting.ask("  "))


def test_older_saves_get_the_reports_table(tmp_path):
    path = tmp_path / "v8.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:
        db.executescript("DROP TABLE scouting_reports; PRAGMA user_version = 8;")
    db.close()
    league_db.connect(path).close()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM scouting_reports").fetchone()[0] == 0
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION == 9
    db.close()


@pytest.fixture
def client(scratch_db, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(league_db, "DEFAULT_DB_FILE", scratch_db)
    monkeypatch.setattr(league_db, "DB_FILE", league_db.DB_FILE)
    return TestClient(app)


def test_the_week_screen_shows_scoutings_report(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client.post("/api/saves/new", json={"name": "scouting", "seed": "3"})

    async def searcher(*args):
        return "Here's what I found.", None
    asyncio.run(orders.work_order(order_with()["id"], searcher=searcher))  # in the save just loaded
    hub = client.get("/api/hub").json()
    [standing] = hub["desk"]["orders"]
    assert standing["scouting"]["by"] == "rules" and standing["scouting"]["targets"]
    assert "Scouting:" in client.get("/").text
    assert "OPENROUTER_API_KEY" in client.post("/api/agent/scouting", json={"question": "Safeties?"}).json()["error"]
