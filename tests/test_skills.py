"""Checks for the front office's skills (task 1.5). No API key needed: the skills'
scripts are plain Python, run here directly and through Agno's own skill tool."""

import importlib.util
import json
import subprocess
import sys

import pytest

from agents import analytics, cap_contracts, gm, memo, skills, tools
from agents.simulator import build_lineup


def script(skill: str, name: str):
    """A skill's script, imported as a module."""
    path = skills.SKILLS_DIR / skill / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py").replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap_check = script("salary-cap-rules", "cap_check.py")
value_player = script("player-valuation", "value_player.py")
unit_impact = script("roster-impact", "unit_impact.py")
check_memo = script("front-office-memo", "check_memo.py")


# ---- The skills themselves --------------------------------------------------------------

@pytest.mark.parametrize("name", skills.ALL)
def test_every_skill_passes_the_agent_skills_format(name):
    skill = skills.load(name).get_skill(name)  # Agno validates the folder as it loads
    assert skill.name == name and skill.description.startswith(("The ", "How ", "What "))
    assert skill.scripts and "## " in skill.instructions


def test_the_skills_folder_holds_exactly_the_known_skills():
    assert {p.name for p in skills.SKILLS_DIR.iterdir() if p.is_dir()} == set(skills.ALL)


def test_an_unknown_skill_is_refused():
    with pytest.raises(ValueError, match="Unknown skills"):
        skills.load("salary-cap-rules", "mind-reading")


def test_a_section_comes_out_without_its_heading():
    house = skills.section("front-office-memo", "House style")
    assert house.startswith("- **Bottom line first.**") and "## " not in house
    with pytest.raises(ValueError, match="no section"):
        skills.section("front-office-memo", "Poetry")


def test_scripts_run_through_agnos_skill_tool():
    """The way an agent runs them: get_skill_script(..., execute=True)."""
    out = json.loads(skills.load("salary-cap-rules")._get_skill_script(
        "salary-cap-rules", "cap_check.py", execute=True, args=["sign", "--payroll", "249.48", "--salary", "6.0"]))
    assert out["returncode"] == 0 and json.loads(out["stdout"])["salary_to_clear"] == 0.48


@pytest.mark.parametrize("skill, name, args", [
    ("salary-cap-rules", "cap_check.py", ["trade", "--payroll", "249.48", "--roster", "48", "--out", "4.1", "--in", "9.87"]),
    ("player-valuation", "value_player.py", ["--position", "S", "--overall", "70", "--salary", "4.1"]),
    ("roster-impact", "unit_impact.py", ["--position", "S", "--current", "coverage=52,tackling=78,speed=81",
                                         "--candidate", "coverage=83,tackling=71,speed=80"]),
    ("front-office-memo", "check_memo.py", ["--facts", '{"record": "2-1"}', "--text", "We are 2-1."]),
])
def test_every_script_runs_from_its_own_folder(skill, name, args):
    """Agno runs a script with the skill's folder as the working directory."""
    folder = skills.SKILLS_DIR / skill
    run = subprocess.run([sys.executable, f"scripts/{name}", *args], cwd=folder, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "error" not in json.loads(run.stdout)


# ---- salary-cap-rules ---------------------------------------------------------------------

def test_a_signing_is_the_league_offices_own_arithmetic():
    out = cap_check.sign(249.48, 6.0, 255.0)
    assert out == {"move": "sign", **tools.cap_math(249.48, 6.0, 255.0)}
    assert out["fits_under_cap"] is False and out["salary_to_clear"] == 0.48


def test_a_trade_is_tested_against_every_rule():
    rules = cap_check.RULES
    limits = (rules["trade_deadline_week"], rules["roster_min"], rules["roster_max"])
    ok = cap_check.trade(249.48, 48, [4.1, 2.98], [9.87], 255.0, 3, *limits)
    assert (ok["payroll_after"], ok["cap_space_after"], ok["roster_after"], ok["legal"]) == (252.27, 2.73, 47, True)
    late = cap_check.trade(249.48, 48, [], [9.87], 255.0, 10, *limits)
    assert not late["legal"] and late["salary_to_clear"] == 4.35
    assert [r.split()[0] for r in late["broken_rules"]] == ["Trades", "Payroll"]
    short = cap_check.trade(249.48, 46, [4.1], [], 255.0, None, *limits)
    assert short["broken_rules"] == ["The roster would have 45 players; the minimum is 46."]


def test_cap_can_go_before_or_after_the_move(capsys):
    cap_check.main(["--cap", "250", "sign", "--payroll", "249.48", "--salary", "1"])
    cap_check.main(["sign", "--payroll", "249.48", "--salary", "1", "--cap", "250"])
    first, second = capsys.readouterr().out.split("}\n{")
    assert '"salary_to_clear": 0.48' in first and '"salary_to_clear": 0.48' in second


# ---- player-valuation ---------------------------------------------------------------------

def test_market_value_rises_with_the_rating():
    low, high = (value_player.value("S", overall, 4.0)["market_value"] for overall in (60, 85))
    assert 1.0 < low < high


def test_the_job_value_prices_the_rating_the_job_needs():
    """Theo Strickland: 70 overall, but coverage 52 - fair on overall, overpaid for the job."""
    out = value_player.value("S", 70, 4.1, age=34, key=52)
    assert out["verdict"] == "fair" and out["value_for_the_job"] == 1.0
    assert out["job_surplus_per_season"] == pytest.approx(-3.1) and out["age_note"].startswith("Past 29")


def test_the_key_rating_can_be_named(capsys):
    assert value_player.parse_key("coverage=88") == value_player.parse_key("88") == 88.0
    value_player.main(["--position", "S", "--overall", "70", "--salary", "4.1", "--key", "coverage"])
    assert "needs the rating's value" in json.loads(capsys.readouterr().out)["error"]


def test_contract_years_and_bad_positions():
    out = value_player.value("S", 85, 3.45, age=23, years=3)
    assert out["surplus_over_contract"] == pytest.approx(out["surplus_per_season"] * 3)
    assert out["age_note"].startswith("On a rookie deal")
    assert "error" in value_player.value("QBR", 70, 1.0)


# ---- roster-impact ---------------------------------------------------------------------

def test_a_safety_swap_moves_the_engines_units():
    out = unit_impact.impact("S", {"coverage": 52, "tackling": 78, "speed": 81},
                             {"coverage": 83, "tackling": 71, "speed": 80})
    change = {c["unit"]: c["change"] for c in out["changes"]}
    assert change["deep_coverage"] == pytest.approx(6.15) and change["short_coverage"] == pytest.approx(3.88)
    assert out["changes"][0]["unit"] == "deep_coverage" and out["starters_at_position"] == 2
    assert any("their offense" in play for play in out["changes"][0]["plays"])


def test_the_impact_is_exactly_build_lineups():
    current, candidate = {"pass_rush": 60, "run_defense": 60, "strength": 60}, {"pass_rush": 90, "run_defense": 60,
                                                                                 "strength": 60}
    before = build_lineup("X", unit_impact._team("DL", current), unit_impact.STARTERS).units
    after = build_lineup("X", unit_impact._team("DL", candidate), unit_impact.STARTERS).units
    change = {c["unit"]: c["change"] for c in unit_impact.impact("DL", current, candidate)["changes"]}
    assert change == {u: round(after[u] - before[u], 2) for u in before if after[u] != before[u]}


def test_ratings_must_match_the_position():
    with pytest.raises(ValueError, match="Missing: speed"):
        unit_impact.parse_ratings("S", "coverage=80,tackling=70")
    with pytest.raises(ValueError, match="Not a S rating: hands"):
        unit_impact.parse_ratings("S", "coverage=80,tackling=70,speed=80,hands=60")


# ---- front-office-memo ---------------------------------------------------------------------

def test_numbers_are_compared_however_theyre_written():
    assert memo.numbers("1,200 yards, $5.50M, 007") == ["1200", "5.5", "7"]
    assert memo.unknown_numbers("We won 24-17 with $5.5M left, by 7.", {"score": "24-17", "space": "$5.50M"}) == ["7"]


def test_sentences_dont_split_on_decimals_or_initials():
    assert memo.sentences("A.J. Brown had 3 catches. We have $5.5M. Fine!") == [
        "A.J. Brown had 3 catches.", "We have $5.5M.", "Fine!"]


def test_the_good_example_passes_and_the_bad_one_doesnt():
    facts = json.dumps({"record": "0-1", "score": "10-30", "cap_space": "$5.5M"})
    good = check_memo.check(facts, "We are 0-1 after a 10-30 loss.\n\nWe have $5.5M of cap space.",
                            "Herons 0-1 after Mesa Verde loss")
    assert good == {"numbers_not_in_the_facts": [], "style_problems": [], "ready": True}
    bad = check_memo.check(facts, "We lost by 20 in a massive upset.",
                           "A massive week ahead as the Herons look to bounce back in a must-win clash")
    assert bad["numbers_not_in_the_facts"] == ["20"] and not bad["ready"]
    assert bad["style_problems"] == ["the headline has 15 words; at most 12", "1 paragraphs; write 2 to 4",
                                     "hype words: massive, must-win"]


# ---- Who has which ---------------------------------------------------------------------

def _names(agent):
    return sorted(skill.name for skill in agent.skills.get_all_skills())


def test_each_agent_has_its_skills():
    assert _names(analytics.build_analytics_agent(None)) == ["player-valuation", "roster-impact"]
    assert _names(cap_contracts.build_cap_contracts_agent(None)) == ["salary-cap-rules"]
    assert analytics.TOOL_CALL_LIMIT >= 18  # room to load a skill and run its script


def test_the_gm_always_writes_in_the_house_style():
    team = gm.build_gm_team(None, None, None, None)
    text = " ".join(team.instructions)
    assert skills.section("front-office-memo", "House style") in text
    assert skills.section("front-office-memo", "Answering the owner") in text
