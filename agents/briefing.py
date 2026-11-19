"""The GM's weekly briefing (task G3).

At the start of each week the GM writes the owner a short briefing: the record,
last week's results, the biggest weakness, the cap and this week's opponent.

Plain Python owns the numbers. `facts()` reads everything the briefing may say
from the league; the GM only turns those facts into a few plain paragraphs, and
`unknown_numbers()` checks that every number it wrote is one of them. A draft
with a number that isn't in the facts goes back to the GM, with the numbers
named; if no draft checks out, or there's no API key, the owner gets the
plain-Python notes instead (`game_loop.overview()["notes"]`).

How it's written comes from the front-office-memo skill (task 1.5): its house
style and briefing sections are the GM's instructions, and a draft that breaks
the style's measurable rules (headline length, paragraphs, sentences, hype
words; `agents/memo.py`) goes back too. Style is a softer rule than numbers: if
the last try still breaks it, the owner gets the first draft whose numbers check.

A briefing is written once per week and kept in the save (`briefings`), so the
owner reads the same one every time they open the week.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from agno.agent import Agent
from pydantic import BaseModel, Field

from agents import deadline as trade_deadline
from agents import game_loop, league_db, memo, season, skills, tools
from agents.analytics import specialist_model

# A draft and up to two rewrites with the problems named. DeepSeek's structured output
# sometimes runs on into whitespace; a run that returns no Briefing counts as a try.
ATTEMPTS = 3

INSTRUCTIONS = [
    "You are the general manager of the Harbor City Herons (team id HAR), writing the owner's briefing "
    "at the start of the week.",
    "You get the week's facts as JSON. Use only those facts. Every number you write - scores, records, "
    "ranks, ratings, yards, dollars, weeks - must appear in the facts exactly as given. Don't work out new "
    "numbers (no differences, totals, averages or percentages) and don't round them differently. If "
    "something isn't in the facts, leave it out.",
    # The front-office-memo skill's rules, always on (task 1.5).
    "The house style:\n" + skills.section("front-office-memo", "House style"),
    "The weekly briefing:\n" + skills.section("front-office-memo", "The weekly briefing"),
    "`headline` is the headline, `paragraphs` the two to four paragraphs, and `watch` the one sentence on "
    "what you're watching.",
]


class Briefing(BaseModel):
    headline: str = Field(description="The week in one line, at most 12 words.")
    paragraphs: list[str] = Field(description="Two to four short paragraphs, one to three sentences each.")
    watch: str = Field(description="One sentence: what the GM is watching this week.")


# ---- The facts --------------------------------------------------------------------

def _leaders(box: dict, team_id: str) -> list[str]:
    """Our standout lines from one game, as the box score has them."""
    ours = [p for p in box["players"] if p["team_id"] == team_id]
    lines = []

    def top(stat):
        players = [p for p in ours if p.get(stat)]
        return max(players, key=lambda p: p[stat]) if players else None

    if (qb := top("pass_att")):
        lines.append(f"{qb['name']} (QB): {qb.get('pass_cmp', 0)} of {qb['pass_att']} passes for "
                     f"{qb.get('pass_yds', 0)} yards, {qb.get('pass_td', 0)} touchdowns, "
                     f"{qb.get('int_thrown', 0)} interceptions")
    if (rb := top("rush_yds")):
        lines.append(f"{rb['name']} ({rb['position']}): {rb['rush_att']} carries for {rb['rush_yds']} yards, "
                     f"{rb.get('rush_td', 0)} touchdowns")
    if (wr := top("rec_yds")):
        lines.append(f"{wr['name']} ({wr['position']}): {wr['rec']} catches for {wr['rec_yds']} yards, "
                     f"{wr.get('rec_td', 0)} touchdowns")
    for stat, what in (("def_sacks", "sack"), ("def_int", "interception")):
        if (d := top(stat)):
            lines.append(f"{d['name']} ({d['position']}): {d[stat]} {what}{'' if d[stat] == 1 else 's'}")
    return lines


def _result_line(game: dict, table: dict) -> str:
    home, away = table[game["home_team_id"]], table[game["away_team_id"]]
    winner, loser = (home, away) if game["home_score"] >= game["away_score"] else (away, home)
    high, low = max(game["home_score"], game["away_score"]), min(game["home_score"], game["away_score"])
    verb = "tied" if high == low else "beat"
    where = "at home" if winner is home else "on the road"
    return f"{winner['city']} {verb} {loser['city']} {high}-{low} {where}"


def facts(db_file: Path | None = None) -> dict:
    """Everything this week's briefing may say, read from the loaded league."""
    if season.regular_season_over():
        raise ValueError("The regular season is over: there's no weekly briefing.")
    week = game_loop.overview()
    team = week["team"]
    our = team["id"]
    table = {row["team_id"]: row for row in season.standings()}

    started = week["week"] > 1  # standings mean nothing before anyone has played
    out = {"week": week["week"], "season_games": week["season_games"],
           "team": f"{team['city']} {team['name']}", "record": team["record"]}
    if started:
        out.update(standing=f"{game_loop._ordinal(team['rank'])} of {team['teams']}",
                   points_for=team["points_for"], points_against=team["points_against"])

    last = week["last_week"]
    if last:
        box = season.box_score(last["game_id"])
        game = box["game"]
        them = last["opponent"]["id"]
        out["last_week"] = {
            "result": {"win": "won", "loss": "lost", "tie": "tied"}[last["outcome"]],
            "score": f"{last['our_score']}-{last['their_score']}",
            "opponent": f"{last['opponent']['city']} {last['opponent']['name']}",
            "where": "at home" if last["home"] else "away",
            "our_yards": box["teams"][our]["total_yds"], "their_yards": box["teams"][them]["total_yds"],
            "our_turnovers": box["teams"][our]["turnovers"], "their_turnovers": box["teams"][them]["turnovers"],
            "standouts": _leaders(box, our)}
        out["around_the_league"] = [_result_line(g, table) for g in season.games(week["week"] - 1)
                                    if g["id"] != game["id"] and g["home_score"] is not None]

    comparisons = json.loads(tools.compare_to_league(our))["comparisons"]
    weakest, strongest = comparisons[0], comparisons[-1]
    position = weakest["position"]
    starters = [p for p in json.loads(tools.get_roster(our, position))["players"] if p["starter"]]
    out["biggest_weakness"] = {
        "unit": game_loop._rating_name(weakest), "rank": f"{game_loop._ordinal(weakest['rank'])} of {team['teams']}",
        "our_rating": weakest["team_avg"], "league_average": weakest["league_avg"],
        "starters": [f"{p['name']}, age {p['age']}, {weakest['rating']} {p['ratings'].get(weakest['rating'], p['overall'])}, "
                     f"${p['salary']}M" for p in starters]}
    if strongest["gap"] > 0:
        out["biggest_strength"] = {"unit": game_loop._rating_name(strongest),
                                   "rank": f"{game_loop._ordinal(strongest['rank'])} of {team['teams']}"}

    out["cap"] = {"payroll": f"${team['payroll']:.1f}M", "cap_space": f"${team['cap_space']:.1f}M",
                  "hard_cap": f"${team['salary_cap']:.0f}M", "roster": team["roster_size"],
                  "roster_limit": team["roster_max"]}
    # The countdown, and once we've traded, our trades and what they changed (2.3).
    out.update(trade_deadline.briefing_facts(db_file))

    this = week["this_week"]
    if this:
        opp = this["opponent"]
        out["this_week"] = {"opponent": f"{opp['city']} {opp['name']}", "where": "at home" if this["home"] else "away",
                            "their_record": opp["record"]}
        if started:
            out["this_week"]["their_standing"] = f"{game_loop._ordinal(opp['rank'])} of {team['teams']}"
    return out


# ---- Checking a draft -----------------------------------------------------------------

def unknown_numbers(briefing: Briefing, known: dict) -> list[str]:
    """Numbers in the briefing that aren't in the facts, in the order they first appear."""
    return memo.unknown_numbers(" ".join([briefing.headline, *briefing.paragraphs, briefing.watch]), known)


def style_problems(briefing: Briefing) -> list[str]:
    """Where the briefing breaks the house style's measurable rules. The watch line is
    held to one sentence, without hype."""
    problems = [p for p in memo.style_problems(briefing.headline, briefing.paragraphs)
                if not p.startswith("hype")]
    if len(memo.sentences(briefing.watch)) > 1:
        problems.append("the watch line has more than one sentence")
    if hype := memo.hype_words(" ".join([briefing.headline, *briefing.paragraphs, briefing.watch])):
        problems.append(f"hype words: {', '.join(hype)}")
    return problems


# ---- Writing it ---------------------------------------------------------------------

def build_briefing_agent(debug: bool = False) -> Agent:
    """The GM writing the briefing. No tools: the facts come in the message."""
    return Agent(name="General Manager", model=specialist_model(), instructions=INSTRUCTIONS,
                 output_schema=Briefing, debug_mode=debug)


async def write(known: dict, agent: Agent | None = None) -> tuple[Briefing | None, list[dict]]:
    """The GM's briefing from the facts, or None if no draft's numbers check out. Also
    returns each attempt's usage and anything it got wrong, for the record."""
    agent = agent or build_briefing_agent()
    facts_text = f"This week's facts:\n{json.dumps(known, indent=2)}"
    prompt = facts_text
    attempts = []
    fallback = None  # the first draft whose numbers check, if the style never does
    for _ in range(ATTEMPTS):
        run = await agent.arun(prompt)
        metrics = run.metrics
        attempt = {"input_tokens": getattr(metrics, "input_tokens", None),
                   "output_tokens": getattr(metrics, "output_tokens", None), "cost": getattr(metrics, "cost", None)}
        attempts.append(attempt)
        if not isinstance(run.content, Briefing):
            attempt["problem"] = "no briefing came back"
            continue
        wrong = unknown_numbers(run.content, known)
        if wrong:
            attempt["problem"] = f"numbers not in the facts: {', '.join(wrong)}"
            prompt = (f"{facts_text}\n\nYour last draft used numbers that are not in the facts: "
                      f"{', '.join(wrong)}. Write it again using only numbers that appear in the facts.")
            continue
        style = style_problems(run.content)
        if not style:
            return run.content, attempts
        attempt["problem"] = f"style: {'; '.join(style)}"
        fallback = fallback or run.content
        prompt = (f"{facts_text}\n\nYour last draft's numbers were right, but it broke the house style: "
                  f"{'; '.join(style)}. Write it again, fixing that and keeping every number as the facts give it.")
    return fallback, attempts


# ---- Keeping it in the save -------------------------------------------------------------

def stored(week: int, db_file: Path | None = None) -> dict | None:
    db = league_db.connect(db_file)
    try:
        row = db.execute("SELECT * FROM briefings WHERE week = ?", (week,)).fetchone()
    finally:
        db.close()
    return None if row is None else {"week": row["week"], **json.loads(row["briefing"]), "written": row["written"],
                                     "cost": row["cost"]}


def _store(week: int, briefing: Briefing, cost: float | None, db_file: Path | None = None) -> None:
    db = league_db.connect(db_file)
    try:
        with db:
            db.execute("INSERT OR IGNORE INTO briefings (week, briefing, written, cost) VALUES (?, ?, ?, ?)",
                       (week, briefing.model_dump_json(),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"), cost))
    finally:
        db.close()


async def this_week(agent: Agent | None = None) -> dict:
    """This week's briefing: the one already in the save, or a new one the GM writes now.
    Raises ValueError when the GM's drafts don't check out; the owner keeps the notes."""
    week = season.current_week()
    if (kept := stored(week)) is not None:
        return kept
    known = facts()
    briefing, attempts = await write(known, agent)
    if briefing is None:
        problems = "; ".join(a["problem"] for a in attempts if a.get("problem"))
        raise ValueError(f"The GM's briefing didn't check out against the league ({problems}). "
                         "The notes stand in for it this week.")
    costs = [a["cost"] for a in attempts if a["cost"] is not None]
    _store(week, briefing, sum(costs) if costs else None)
    return stored(week)  # the one in the save, in case another request wrote it first
