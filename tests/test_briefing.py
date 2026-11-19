"""Checks for the GM's weekly briefing (task G3). No API key needed: the GM is
replaced by a stand-in that returns the drafts each test gives it."""

import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from agents import briefing, league_db, season


def test_week_one_has_no_standings_or_last_week(scratch_db):
    facts = briefing.facts()
    assert (facts["week"], facts["record"]) == (1, "0-0")
    assert "standing" not in facts and "last_week" not in facts and "their_standing" not in facts["this_week"]
    weakness = facts["biggest_weakness"]
    assert (weakness["unit"], weakness["rank"]) == ("safety coverage", "6th of 6")
    assert weakness["starters"] and all("coverage" in s for s in weakness["starters"])
    assert facts["cap"]["cap_space"] == "$5.5M" and facts["trade_deadline"]["after_week"] == 9


def test_later_weeks_report_last_week(scratch_db):
    season.play_week()
    season.advance_week()
    facts = briefing.facts()
    last = facts["last_week"]
    ours = next(g for g in season.games(1) if "HAR" in (g["home_team_id"], g["away_team_id"]))
    home = ours["home_team_id"] == "HAR"
    us, them = (ours["home_score"], ours["away_score"]) if home else (ours["away_score"], ours["home_score"])
    assert last["score"] == f"{us}-{them}" and last["where"] == ("at home" if home else "away")
    assert len(facts["around_the_league"]) == 2 and last["standouts"][0].endswith("interceptions")
    assert facts["standing"].endswith("of 6") and facts["trade_deadline"]["weeks_left_after_this_one"] == 7


def test_no_briefing_after_the_season(scratch_db):
    with league_db.connect() as db:
        db.execute("UPDATE game SET current_week = 18")
    with pytest.raises(ValueError, match="over"):
        briefing.facts()


# ---- The number check -----------------------------------------------------------------

FACTS = {"record": "2-1", "cap": {"cap_space": "$5.5M", "payroll": "$249.5M"}, "last_week": {"score": "24-17"},
         "weakness": {"our_rating": 48.5, "league_average": 71.8}, "yards": 1200}


def draft(*paragraphs, headline="Herons 2-1", watch="Safety coverage."):
    return briefing.Briefing(headline=headline, paragraphs=list(paragraphs), watch=watch)


def test_numbers_from_the_facts_pass():
    ok = draft("We won 24-17 and are 2-1.", "Safety coverage is 48.5 against 71.8, with $5.5M of space.",
               "We gained 1,200 yards; space is $5.50M.")
    assert briefing.unknown_numbers(ok, FACTS) == []


def test_numbers_not_in_the_facts_are_named():
    bad = draft("We won by 7 and have $5.52M of space.", "That's 23.3 below average.", watch="Week 2026 matters.")
    assert briefing.unknown_numbers(bad, FACTS) == ["7", "5.52", "23.3", "2026"]


# ---- Writing it ------------------------------------------------------------------------

class StandIn:
    """Returns each of `drafts` in turn, and keeps every prompt it was given."""

    def __init__(self, *drafts):
        self.drafts, self.prompts = list(drafts), []

    async def arun(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.drafts.pop(0),
                               metrics=SimpleNamespace(input_tokens=10, output_tokens=5, cost=0.0001))


def test_a_bad_number_goes_back_to_the_gm():
    gm = StandIn(draft("We lost by 7.", "We are 2-1."), draft("We lost 17-24.", "We are 2-1."))
    known = {"last_week": {"score": "17-24"}, "record": "2-1"}
    written, attempts = asyncio.run(briefing.write(known, gm))
    assert written.paragraphs == ["We lost 17-24.", "We are 2-1."]
    assert "not in the facts: 7" in gm.prompts[1] and attempts[0]["problem"].endswith(": 7")


def test_no_briefing_when_nothing_checks_out():
    gm = StandIn("{ broken json", draft("We lost by 7."), draft("We lost by 7."))
    written, attempts = asyncio.run(briefing.write({"record": "2-1"}, gm))
    assert written is None and len(attempts) == briefing.ATTEMPTS
    assert attempts[0]["problem"] == "no briefing came back"


def test_written_once_a_week_and_kept(scratch_db):
    gm = StandIn(draft("We are 0-0 as the season starts.", "Safety coverage ranks last.", headline="Week 1"))
    first = asyncio.run(briefing.this_week(gm))
    assert (first["week"], first["headline"]) == (1, "Week 1") and first["cost"] == pytest.approx(0.0001)
    assert asyncio.run(briefing.this_week(StandIn())) == first  # the GM isn't asked again
    assert briefing.stored(1) == first and briefing.stored(2) is None


def test_a_briefing_that_fails_isnt_kept(scratch_db):
    gm = StandIn(*[draft("We lost by 7.")] * briefing.ATTEMPTS)
    with pytest.raises(ValueError, match="didn't check out"):
        asyncio.run(briefing.this_week(gm))
    assert briefing.stored(1) is None


# ---- The house style (front-office-memo, task 1.5) ---------------------------------------

def test_the_instructions_come_from_the_memo_skill():
    text = " ".join(briefing.INSTRUCTIONS)
    assert "Bottom line first" in text and "at most 12 words" in text and "Watching" in text


def test_style_problems_are_named():
    assert briefing.style_problems(draft("We are 2-1.", "Safety coverage ranks last.")) == []
    bad = draft("We are 2-1. We won. We scored. We celebrated.", headline="A " * 13,
                watch="A huge week. Then another.")
    assert briefing.style_problems(bad) == ["the headline has 13 words; at most 12",
                                            "1 paragraphs; write 2 to 4",
                                            "paragraph 1 has 4 sentences; at most 3",
                                            "the watch line has more than one sentence", "hype words: huge"]


def test_a_style_problem_goes_back_to_the_gm():
    gm = StandIn(draft("We are 2-1 after a massive win."), draft("We are 2-1.", "Safety coverage ranks last."))
    written, attempts = asyncio.run(briefing.write({"record": "2-1"}, gm))
    assert written.paragraphs == ["We are 2-1.", "Safety coverage ranks last."]
    assert "broke the house style" in gm.prompts[1] and "hype words: massive" in gm.prompts[1]
    assert attempts[0]["problem"].startswith("style:")


def test_style_alone_never_costs_the_owner_a_briefing():
    """Numbers are the hard rule: if the style never comes right, the first draft whose
    numbers check goes out, not the notes."""
    first, later = draft("We are 2-1. Massive."), draft("We are 2-1, huge.")
    gm = StandIn(draft("We lost by 7.", "We are 2-1."), first, later)
    written, attempts = asyncio.run(briefing.write({"record": "2-1"}, gm))
    assert written is first and len(attempts) == briefing.ATTEMPTS


def test_g8_saves_get_the_briefings_table(tmp_path):
    path = tmp_path / "g8.db"
    league_db.build(path)
    with sqlite3.connect(path) as db:  # turn it back into a G8 database
        db.executescript("DROP TABLE briefings; PRAGMA user_version = 3;")
    db.close()
    assert briefing.stored(1, path) is None
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == league_db.SCHEMA_VERSION
    db.close()
