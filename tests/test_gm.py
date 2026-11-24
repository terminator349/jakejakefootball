"""Checks for the GM's team (task 1.4) and the Draft desk. No API key needed: the
team is built and inspected, and a run is read from a stand-in response."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from agno.team import TeamMode
from agno.tools.mcp import MCPTools

from agents import analytics, cap_contracts, coaching, draft_desk, gm, medical
from draft.players import build_player_pool
from draft.roster_rules import SALARY_CAP


def team(draft_file=draft_desk.RESULTS_FILE):
    return gm.build_gm_team(analytics.league_office_tools(), cap_contracts.league_office_tools(),
                            coaching.league_office_tools(), medical.league_office_tools(), draft_file)


def test_the_gm_leads_every_specialist():
    gm_team = team()
    assert gm_team.name == "General Manager" and gm_team.mode == TeamMode.coordinate
    assert [m.name for m in gm_team.members] == ["Analytics", "Cap & Contracts", "Draft", "Coaching", "Medical"]
    assert all(m.role for m in gm_team.members)  # what the GM reads to choose who to ask
    assert gm_team.model.id == gm.GM_MODEL
    assert not gm_team.tools  # the GM has no data of its own: every number comes from a specialist


def test_each_specialist_keeps_its_own_tools():
    analytics_member, cap_member, draft_member, coaching_member, medical_member = team().members
    assert isinstance(analytics_member.tools[0], MCPTools) and isinstance(cap_member.tools[0], MCPTools)
    assert isinstance(coaching_member.tools[0], MCPTools) and isinstance(medical_member.tools[0], MCPTools)
    assert len({id(m.tools[0]) for m in (analytics_member, cap_member, coaching_member, medical_member)}) == 4
    assert "check_cap_fit" not in analytics.ANALYTICS_TOOLS and "check_cap_fit" in cap_contracts.CAP_CONTRACTS_TOOLS
    assert [f.__name__ for f in draft_member.tools] == ["draft_summary", "team_draft", "best_undrafted"]


def test_the_team_has_loop_guards_and_a_parser():
    gm_team = team()
    assert gm_team.tool_call_limit == gm.DELEGATION_LIMIT
    assert gm_team.share_member_interactions  # Cap & Contracts sees what Analytics found
    assert gm_team.output_schema is gm.GMReport and gm_team.parser_model is not None
    assert "general manager" in gm_team.parser_model_prompt
    for member in gm_team.members:
        assert member.tool_call_limit and member.parser_model is not None and member.output_schema is not None


def test_both_league_office_servers_start():
    """front_office() starts a League Office server per League Office specialist, each with its own tools."""
    async def go():
        async with gm.front_office() as gm_team:
            analytics_m, cap_m, _, coaching_m, medical_m = gm_team.members
            return [set(m.tools[0].functions) for m in (analytics_m, cap_m, coaching_m, medical_m)]
    analytics_tools, cap_tools, coaching_tools, medical_tools = asyncio.run(go())
    assert analytics_tools == set(analytics.ANALYTICS_TOOLS) and cap_tools == set(cap_contracts.CAP_CONTRACTS_TOOLS)
    assert coaching_tools == set(coaching.COACHING_TOOLS) and medical_tools == set(medical.MEDICAL_TOOLS)


def test_the_owner_must_ask_something():
    with pytest.raises(ValueError, match="Type a question"):
        asyncio.run(gm.ask("   "))


def test_ground_report_takes_facts_from_the_league():
    report = gm.GMReport(team_id="Harbor City Herons", answer="a", recommendation="r", evidence=[],
                         payroll=249500000.0, cap_space=-1.0)
    grounded = gm.ground_report(report)
    assert (grounded.team_id, grounded.payroll, grounded.cap_space) == ("HAR", 249.5, 5.5)
    # An answer about another team names it, but the money line is always ours.
    other = gm.ground_report(report.model_copy(update={"team_id": "Mesa Verde"}))
    assert (other.team_id, other.payroll, other.cap_space) == ("MES", 249.5, 5.5)
    # A question only about Draft Day has no league team.
    assert gm.ground_report(report.model_copy(update={"team_id": "Draft Day"})).team_id == "HAR"


# ---- Reading a run ------------------------------------------------------------------

def tool(name, args, result="{}"):
    return SimpleNamespace(tool_name=name, tool_args=args, tool_call_error=False, result=result)


def metrics(i, o, cost):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cost=cost)


def test_summarize_shows_who_was_asked_and_what_they_said():
    roster = analytics.RosterReport(team_id="HAR", answer="Safety.", weakest_area="safety coverage", evidence=["48.5"],
                                    target_profile="coverage safety", payroll=1.0, cap_space=1.0)
    cap = cap_contracts.CapReport(team_id="Harbor City", answer="It fits.", evidence=[], payroll=1.0, cap_space=1.0,
                                  fits_under_cap=True, salary_to_clear=0.0)
    response = SimpleNamespace(
        content=gm.GMReport(team_id="HAR", answer="Sign one.", recommendation="Sign a $5M safety.",
                            evidence=["$5.5M of space"], payroll=0.0, cap_space=0.0),
        tools=[tool("delegate_task_to_member", {"member_id": "analytics", "task": "Find the weakness."}),
               tool("delegate_task_to_member", {"member_id": "cap-&-contracts", "task": "Does $5M fit?"})],
        member_responses=[
            SimpleNamespace(agent_name="Analytics", content=roster, tools=[tool("compare_to_league", {"team_id": "HAR"})],
                            metrics=metrics(100, 10, 0.001)),
            SimpleNamespace(agent_name="Cap & Contracts", content=cap, tools=[tool("check_cap_fit", {"new_salary": 5})],
                            metrics=metrics(50, 5, 0.0005))],
        metrics=metrics(20, 2, 0.0001), model="m")
    run = gm.summarize(response, seconds=61.23)
    assert run["consulted"] == ["Analytics", "Cap & Contracts"]
    assert [d["task"] for d in run["delegations"]] == ["Find the weakness.", "Does $5M fit?"]
    assert run["report"]["answer"] == "Sign one." and run["report"]["cap_space"] == 5.5  # grounded
    assert run["specialists"][1]["report"]["team_id"] == "HAR"  # specialists' reports are grounded too
    assert run["specialists"][0]["tool_calls"][0]["tool"] == "compare_to_league"
    assert (run["input_tokens"], run["output_tokens"]) == (170, 17)  # the GM's calls plus the specialists'
    assert run["cost"] == pytest.approx(0.0016) and run["seconds"] == 61.2


def test_summarize_keeps_a_plain_text_answer():
    response = SimpleNamespace(content="I couldn't reach anyone.", tools=None, member_responses=None,
                               metrics=None, model="m")
    run = gm.summarize(response)
    assert run["report"] is None and run["text"] == "I couldn't reach anyone." and run["consulted"] == []
    assert run["cost"] is None


def message(role, content, tool_calls=None):
    return SimpleNamespace(role=role, content=content, tool_calls=tool_calls)


BROKEN = SimpleNamespace(  # the parser ran on into whitespace: the GM's answer is only in its messages
    content='{"team_id":"","answer":"Safety."\t\r\n\r\n\r\n', tools=None, member_responses=None,
    metrics=metrics(10, 1, 0.0001), model="m",
    messages=[message("user", "Where are we weakest?"), message("assistant", None, tool_calls=[{"id": 1}]),
              message("tool", "{}"), message("assistant", "Safety is our weakest spot. Sign one.")])


def test_a_lost_report_shows_what_the_gm_wrote():
    assert gm.gm_text(BROKEN) == "Safety is our weakest spot. Sign one."
    assert gm.summarize(BROKEN)["text"] == "Safety is our weakest spot. Sign one."


def test_ask_parses_the_gms_answer_again(monkeypatch):
    @asynccontextmanager
    async def front_office(db_file=None, debug=False):
        async def arun(question):
            return SimpleNamespace(**vars(BROKEN))
        yield SimpleNamespace(arun=arun)

    async def reparse(text, usage):
        usage.append({"input_tokens": 5, "output_tokens": 5, "cost": 0.0002})
        return gm.GMReport(team_id="HAR", answer=text, recommendation="Sign one.", evidence=[], payroll=0, cap_space=0)

    monkeypatch.setattr(gm, "front_office", front_office)
    monkeypatch.setattr(gm, "reparse", reparse)
    run = asyncio.run(gm.ask("Where are we weakest?"))
    assert run["report"]["answer"] == "Safety is our weakest spot. Sign one." and run["text"] is None
    assert run["cost"] == pytest.approx(0.0003)  # the second parse is counted


# ---- The Draft desk ---------------------------------------------------------------

@pytest.fixture
def small_draft(tmp_path):
    """Two teams, three picks, from the real draft class."""
    pool = {p.id: p for p in build_player_pool()}
    picks = [("HAR", "QB-01", 1, 14.0), ("MES", "S-01", 2, 11.0), ("HAR", "CB-01", 3, 10.5)]
    teams = {t: {"id": t, "city": "C", "name": t, "is_user": False, "philosophy": f"{t} way", "payroll": 0,
                 "cap_room": 220, "players": []} for t in ("HAR", "MES")}
    for team_id, player_id, pick, salary in picks:
        p = pool[player_id]
        teams[team_id]["players"].append({"id": p.id, "name": p.name, "position": p.position, "overall": p.overall,
                                          "team_id": team_id, "salary": salary, "pick_number": pick})
    results = {"draft_order": ["HAR", "MES"], "teams": list(teams.values()),
               "draft_log": [{"pick": n, "team_id": t, "player_id": i, "salary": s} for t, i, n, s in picks]}
    path = tmp_path / "draft_results.json"
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def tools_for(path):
    return {f.__name__: f for f in draft_desk.build_draft_tools(path)}


def test_draft_summary_uses_the_league_cap(small_draft):
    summary = json.loads(tools_for(small_draft)["draft_summary"]())
    har = summary["teams"][0]
    assert summary["salary_cap"] == SALARY_CAP == 255
    assert (har["team_id"], har["payroll"], har["cap_room"]) == ("HAR", 24.5, 230.5)  # not the file's stale 220 cap
    assert har["best_picks"][0]["pick"] in (1, 3)
    # Every class is graded, so "who drafted best?" takes one call.
    mes = summary["teams"][1]
    assert har["players"] == 2 and har["value_surplus"] == round(har["market_value"] - har["payroll"], 1)
    assert sorted([har["rank_by_average_overall"], mes["rank_by_average_overall"]]) == [1, 2]
    assert har["rated_90_plus"] == sum(p["overall"] >= 90 for p in json.loads(tools_for(small_draft)["team_draft"]("HAR"))["picks"])


def test_team_draft_lists_picks_in_order(small_draft):
    tools = tools_for(small_draft)
    picks = json.loads(tools["team_draft"]("har"))["picks"]
    assert [(p["pick"], p["round"], p["position"]) for p in picks] == [(1, 1, "QB"), (3, 1, "CB")]
    assert picks[0]["market_value"] > 0
    assert [p["position"] for p in json.loads(tools["team_draft"]("HAR", "cb"))["picks"]] == ["CB"]
    assert "error" in json.loads(tools["team_draft"]("XXX"))
    assert "error" in json.loads(tools["team_draft"]("HAR", "ZZ"))


def test_best_undrafted_leaves_out_who_was_taken(small_draft):
    best = json.loads(tools_for(small_draft)["best_undrafted"]("S", 3))
    assert best["undrafted"] == sum(1 for p in build_player_pool() if p.position == "S") - 1
    assert len(best["players"]) == 3 and all(p["position"] == "S" for p in best["players"])
    taken = next(p for p in build_player_pool() if p.id == "S-01").name
    assert taken not in [p["name"] for p in best["players"]]


def test_no_draft_yet(tmp_path):
    for name, f in tools_for(tmp_path / "missing.json").items():
        assert "draft_day.py" in json.loads(f("HAR") if name == "team_draft" else f())["error"]


def test_the_real_draft_results_read(tmp_path):
    """data/draft_results.json, as draft_day.py writes it."""
    summary = json.loads(tools_for(draft_desk.RESULTS_FILE)["draft_summary"]())
    assert len(summary["teams"]) == 6 and summary["rounds"] == 53
