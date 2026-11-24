"""The scouting team (task 4.1): a second level under the GM.

    Owner -> GM -> Scouting (director) -> Pro scout, offense   QB RB WR TE OL K P
                                       -> Pro scout, defense   DL LB CB S
                                       -> Draft                the Draft desk (1.4), moved here

The GM used to find its own trade targets (G4's trade_targets tool). Now the
scouting team finds them and the GM works from its report. For an order, or the
trade deadline (2.3), the Scouting director hands each position to the pro
scout who covers it, each scout grades the players there, and the report goes
to the GM, who builds, checks and proposes the trades as before. In the GM's
own team (1.4) Scouting replaces the Draft desk, which now reports through it.

Plain Python does the looking (`targets()`). For one position, it lists the
players on the other five teams who would start for us, with what each would
add to our units (the simulator's units, measured as the Trade Desk does), his
season so far, whether he's hurt, and the best one-for-one offer his team
should accept by the league's own measure (agents/negotiation.py), that is also
worth it to us and keeps every player the owner protects. The scouts read that
list, grade each player A, B or C (the scouting skill) and write a note on him.
They can't add a player the list doesn't have: the report keeps only the ids
plain Python found, with plain Python's numbers. Without a model (no API key,
or the deadline's rules search) the rules grade the same list: `rules_report()`.

Every report is kept (the scouting_reports table) with the order it was for,
so the week screen can show it under the order, and the org chart (4.3) can
say what Scouting found.
"""

import json
from pathlib import Path
from typing import Literal

from agno.agent import Agent
from agno.team import Team, TeamMode
from pydantic import BaseModel, Field

from agents import draft_desk, memory, negotiation, skills
from agents import trade_desk as desk
from agents.analytics import specialist_model
from agents.league_db import connect, current_injuries, load_league

OUR_TEAM = "HAR"
OFFENSE = ("QB", "RB", "WR", "TE", "OL", "K", "P")
DEFENSE = ("DL", "LB", "CB", "S")
SCOUTED = 6        # players looked at closely per position: the best of those who'd start for us
SHORTLIST = 4      # players per position in a report
WEAKEST = 2        # positions scouted for an order that names none
SCOUT_TOOL_LIMIT = 8
DIRECTOR_DELEGATIONS = 4
A_GRADE = 1.0      # the rules' A: a deal their team takes that's worth at least this much to us

POSITION_NAMES = {"QB": "quarterback", "RB": "running back", "WR": "receiver", "TE": "tight end",
                  "OL": "offensive line", "DL": "defensive line", "LB": "linebacker", "CB": "cornerback",
                  "S": "safety", "K": "kicker", "P": "punter"}

# The season stats worth quoting for each position.
KEY_STATS = {"QB": ["pass_yds", "pass_td"], "RB": ["rush_yds", "rush_td"], "WR": ["rec_yds", "rec_td"],
             "TE": ["rec_yds", "rec_td"], "OL": [], "DL": ["def_sacks"], "LB": ["def_sacks", "def_int"],
             "CB": ["def_int"], "S": ["def_int"], "K": ["fg_made", "fg_att"], "P": ["punt_yds"]}


class ScoutingError(ValueError):
    """A request the scouts can't act on, e.g. an unknown position."""


def side_of(position: str) -> str:
    return "offense" if position in OFFENSE else "defense"


# ---- What plain Python finds ---------------------------------------------------------------

def _team_names(league: dict) -> dict[str, str]:
    return {t["id"]: t["city"] for t in league["teams"]}


def _card(p: dict, league: dict) -> dict:
    return {"id": p["id"], "name": p["name"], "position": p["position"], "team_id": p["team_id"],
            "team": _team_names(league)[p["team_id"]], "overall": p["overall"], "salary": p["salary"],
            "years_left": p["contract_years"]}


def _season_stats(db_file: Path | None, player_ids: list[str]) -> dict[str, dict]:
    if not player_ids:
        return {}
    db = connect(db_file)
    try:
        rows = db.execute(f"SELECT player_id, stat, SUM(value) FROM player_game_stats WHERE player_id IN "
                          f"({','.join('?' * len(player_ids))}) GROUP BY player_id, stat", player_ids).fetchall()
    finally:
        db.close()
    out: dict[str, dict] = {}
    for pid, stat, total in rows:
        out.setdefault(pid, {})[stat] = total
    return out


def best_offer(league: dict, target: dict, protected: set[str] = frozenset(),
               max_added_payroll: float | None = None) -> dict | None:
    """Our best single player to send for the target: the trade is legal, his team scores
    it at least its margin (so it says yes), we score it at least ours, and it sends no
    protected player. Best for us first. None if no one-for-one trade works."""
    from agents import rivals  # here, not at the top: rivals imports orders, which imports this module
    by_id = {p["id"]: p for p in league["players"]}
    best = None
    for p in league["players"]:
        if p["team_id"] != OUR_TEAM or p["id"] in protected:
            continue
        if max_added_payroll is not None and target["salary"] - p["salary"] > max_added_payroll + 1e-9:
            continue
        if not rivals._legal(league, OUR_TEAM, [p["id"]], target["team_id"], [target["id"]], by_id):
            continue
        ours, theirs = rivals._scores(league, OUR_TEAM, [p["id"]], target["team_id"], [target["id"]])
        if theirs["score"] >= theirs["margin"] and ours["score"] >= ours["margin"]:
            if best is None or ours["score"] > best["our_score"]:
                best = {"we_send": [_card(p, league)], "their_score": theirs["score"], "our_score": ours["score"],
                        "margin": theirs["margin"], "payroll_change": round(target["salary"] - p["salary"], 2)}
    return best


def targets(position: str, max_salary: float | None = None, protected=(), max_added_payroll: float | None = None,
            db_file: Path | None = None, league: dict | None = None) -> dict:
    """The players at one position on the other teams who would start for us, best for us
    first: those with a one-for-one trade their team should take, by what it's worth to us,
    then the rest by what they'd add to our units."""
    league = league or load_league(db_file)
    position = position.strip().upper()
    starters = league["rules"]["starters_per_position"]
    if position not in starters:
        raise ScoutingError(f"Unknown position {position!r}. Valid: {', '.join(starters)}.")
    n = starters[position]
    ours = sorted((p for p in league["players"] if p["team_id"] == OUR_TEAM and p["position"] == position),
                  key=lambda p: -p["overall"])
    our_starters = ours[:n]
    worst = our_starters[-1]["overall"] if len(ours) >= n else 0
    pool = sorted((p for p in league["players"] if p["team_id"] != OUR_TEAM and p["position"] == position
                   and p["overall"] > worst and (not max_salary or p["salary"] <= max_salary + 1e-9)),
                  key=lambda p: (-p["overall"], p["id"]))[:SCOUTED]
    hurt = {i["player_id"]: i for i in current_injuries(db_file=db_file)}
    stats = _season_stats(db_file, [p["id"] for p in pool])
    protected = set(protected)
    remembered = memory.timeline(db_file)  # 4.2: what's happened with each target this season

    players = []
    for p in pool:
        depth = sorted((q for q in league["players"] if q["team_id"] == p["team_id"] and q["position"] == position),
                       key=lambda q: -q["overall"])
        joined = desk._side(league, OUR_TEAM, [], [p["id"]])
        players.append({
            **_card(p, league), "age": p["age"], "ratings": p["ratings"],
            "starts_for_his_team": depth.index(p) < n,
            "unit_gain": negotiation.unit_points(joined["unit_changes"]),
            "units": joined["unit_changes"][:3],
            "games_out": hurt[p["id"]]["games_remaining"] if p["id"] in hurt else 0,
            "season": {s: stats.get(p["id"], {}).get(s, 0) for s in KEY_STATS.get(position, [])},
            "offer": best_offer(league, p, protected, max_added_payroll),
            "history": memory.about_player(p["id"], remembered)[-3:]})
    players.sort(key=lambda t: (t["offer"] is None, -(t["offer"]["our_score"] if t["offer"] else t["unit_gain"])))
    return {"position": position, "max_salary": max_salary or None,
            "our_starters": [{"id": p["id"], "name": p["name"], "overall": p["overall"]} for p in our_starters],
            "would_start_above": worst, "players": players}


def player_report(player_id: str, db_file: Path | None = None, league: dict | None = None) -> dict:
    """One player in full: ratings, contract, his whole season's stats, whether he's hurt, and
    where he stands on his team's depth chart and against our starters at his position."""
    league = league or load_league(db_file)
    by_id = {p["id"]: p for p in league["players"]}
    p = by_id.get(player_id.strip().upper())
    if p is None:
        raise ScoutingError(f"No player {player_id!r}. Use an id from scout_targets.")
    pos, n = p["position"], league["rules"]["starters_per_position"][p["position"]]

    def depth(team):
        return [{"id": q["id"], "name": q["name"], "overall": q["overall"]} for q in
                sorted((q for q in league["players"] if q["team_id"] == team and q["position"] == pos),
                       key=lambda q: -q["overall"])]
    hurt = [i for i in current_injuries(db_file=db_file) if i["player_id"] == p["id"]]
    return {**_card(p, league), "age": p["age"], "ratings": p["ratings"],
            "season": _season_stats(db_file, [p["id"]]).get(p["id"], {}),
            "injury": hurt[0] if hurt else None,
            "his_team_depth": depth(p["team_id"]), "our_depth": depth(OUR_TEAM), "starters_per_team": n}


# ---- The rules' grades -----------------------------------------------------------------------

def rules_grade(t: dict) -> str:
    if t["games_out"] or not t["offer"]:
        return "C"
    return "A" if t["offer"]["our_score"] >= A_GRADE else "B"


def rules_note(t: dict) -> str:
    years = f"{t['years_left']} season{'s' if t['years_left'] != 1 else ''}"
    note = f"Adds {t['unit_gain']:+.1f} to our units, with {years} left on his deal. "
    if t["offer"]:
        send = t["offer"]["we_send"][0]
        note += (f"{t['team']} should take {send['name']} ({send['position']}, {send['overall']} overall) for him: "
                 f"they score it {t['offer']['their_score']:+.2f}, we {t['offer']['our_score']:+.2f}.")
    else:
        note += f"No one-for-one trade of ours works for {t['team']}: it would take more."
    if t["games_out"]:
        note += f" Hurt: out {t['games_out']} more game{'s' if t['games_out'] != 1 else ''}."
    if t.get("history"):
        note += f" Before: {t['history'][-1]}"
    return note


def _entry(t: dict, grade: str, note: str, graded_by: str) -> dict:
    keep = ("position", "team_id", "team", "name", "overall", "salary", "years_left", "unit_gain", "games_out",
            "season", "offer", "history")
    return {"player_id": t["id"], **{k: t.get(k) for k in keep}, "grade": grade, "note": note, "graded_by": graded_by}


def _summary(found: dict[str, dict]) -> str:
    parts = []
    for pos, f in found.items():
        players = f["players"]
        limit = f" under ${f['max_salary']:.2f}M" if f["max_salary"] else ""
        name = POSITION_NAMES.get(pos, pos)
        if not players:
            parts.append(f"no {name} target{limit} who would start for us")
            continue
        deals = sum(1 for t in players[:SHORTLIST] if t["offer"])
        shown = min(len(players), SHORTLIST)
        parts.append(f"{shown} {name} target{'s' if shown != 1 else ''}{limit} who would start for us, {deals} on a "
                     "one-for-one trade their team should take")
    text = "; ".join(parts)
    return "Found " + text + "." if not text.startswith("no ") else text[0].upper() + text[1:] + "."


def rules_report(found: dict[str, dict]) -> dict:
    """A report graded by the rules, from what `targets()` found for each position."""
    entries = [_entry(t, rules_grade(t), rules_note(t), "rules")
               for f in found.values() for t in f["players"][:SHORTLIST]]
    return {"by": "rules", "positions": list(found), "summary": _summary(found), "targets": entries, "cost": None}


# ---- The scouts and their director -------------------------------------------------------------

class ScoutPick(BaseModel):
    player_id: str = Field(description="The player's id, exactly as scout_targets gave it, e.g. 'SUM-45'.")
    grade: Literal["A", "B", "C"] = Field(description="A, B or C, by the scouting skill's grades.")
    note: str = Field(description="One or two sentences on the player for the GM, with the tools' numbers.")


class ScoutReport(BaseModel):
    """What one pro scout reports."""

    summary: str = Field(description="Two sentences: what the scout found at the positions it was asked about.")
    picks: list[ScoutPick] = Field(description="The graded players, best first. Empty if nobody would start for us.")


class ScoutingReport(BaseModel):
    """What the Scouting director reports to the GM."""

    summary: str = Field(description="The director's bottom line for the GM, two or three sentences: the best "
                                     "targets by name, and what their teams would take for them.")
    picks: list[ScoutPick] = Field(description="Every player the scouts graded, best first, with the scout's "
                                               "grade and note. Empty if none.")


SCOUT_PARSER_PROMPT = (
    "The user message is a scouting report written by a pro scout of an American football front office. Fill "
    "the output fields from that report only: copy its player ids, grades and notes exactly, invent nothing, and "
    "do not reply to these instructions."
)
DIRECTOR_PARSER_PROMPT = (
    "The user message is the scouting director of an American football front office reporting to the general "
    "manager, after hearing from the pro scouts. Fill the output fields from that report only: copy its player "
    "ids, grades and notes exactly, invent nothing, and do not reply to these instructions. `summary` is the "
    "director's own bottom line for the GM, about the players and the deals, in two or three sentences of its "
    "own words, naming each player and his team (not their ids). Never write about the message, its format or "
    "what it leaves out."
)


def build_scout_tools(positions: tuple[str, ...], max_salary: float | None = None, protected=(),
                      max_added_payroll: float | None = None, db_file: Path | None = None) -> list:
    """One scout's tools, held to its positions and to the order's limits."""

    def scout_targets(position: str) -> str:
        """The players at one position on the other five teams who would start for us, best for us
        first: ratings, salary and years left, what he'd add to our units, his season so far, games
        out hurt, and the best one-for-one offer his team should accept by the league's own measure
        (their score is at least their margin, and ours at least ours). offer is null when no single
        player of ours works.

        Args:
            position: league position code you cover, e.g. "S".
        """
        position = position.strip().upper()
        if position not in positions:
            return json.dumps({"error": f"You scout {', '.join(positions)}; {position!r} is another scout's."})
        try:
            return json.dumps(targets(position, max_salary, protected, max_added_payroll, db_file))
        except ScoutingError as e:
            return json.dumps({"error": str(e)})

    def scout_player(player_id: str) -> str:
        """One player in full: ratings, contract, every season stat, any injury, his team's depth
        chart at his position and ours. Use it only when you need more before grading him.

        Args:
            player_id: an id scout_targets gave you, e.g. "SUM-45".
        """
        try:
            return json.dumps(player_report(player_id, db_file))
        except ScoutingError as e:
            return json.dumps({"error": str(e)})

    return [scout_targets, scout_player]


def build_scout(side: str, max_salary: float | None = None, protected=(), max_added_payroll: float | None = None,
                db_file: Path | None = None, debug: bool = False) -> Agent:
    positions = OFFENSE if side == "offense" else DEFENSE
    return Agent(
        name=f"Pro scout, {side}",
        role=f"Scouts {side} ({' '.join(positions)}) on the other five teams: who would start for us, what he'd "
             "add, what his team would take for him, and a grade.",
        model=specialist_model(),
        tools=build_scout_tools(positions, max_salary, protected, max_added_payroll, db_file),
        tool_call_limit=SCOUT_TOOL_LIMIT,
        instructions=[
            f"You are the {side} pro scout of the Harbor City Herons (team id HAR) in a six-team American football "
            f"league. You scout {', '.join(positions)} on the other five teams, for trades.",
            "Call scout_targets once for each position you're asked about. It lists the players there who would "
            "start for us, with everything plain Python knows about them. Call scout_player only if you need more "
            "before grading a player.",
            f"Grade at most {SHORTLIST} players per position, best first, and write a note on each with the tools' "
            "numbers. Use only ids scout_targets returned; never invent players or numbers.",
            "If nobody at a position would start for us, say so: an empty list is a fine report.",
            "How to grade:\n" + skills.section("scouting", "Grades"),
            "How to write a note:\n" + skills.section("scouting", "Notes"),
        ],
        output_schema=ScoutReport,
        parser_model=specialist_model(),
        parser_model_prompt=SCOUT_PARSER_PROMPT,
        debug_mode=debug,
    )


def build_scouting_team(max_salary: float | None = None, protected=(), max_added_payroll: float | None = None,
                        db_file: Path | None = None, draft_file: Path = draft_desk.RESULTS_FILE,
                        debug: bool = False) -> Team:
    """The Scouting director and its scouts. The limits hold the scouts' tools to an order's
    terms; with none, they scout freely (the GM's questions, 1.4)."""
    limits = dict(max_salary=max_salary, protected=protected, max_added_payroll=max_added_payroll, db_file=db_file)
    return Team(
        name="Scouting",
        role="Finds trade targets at any position on the other five teams: who would start for us, what he'd add "
             "to our units, the one-for-one trade his team should take, and a scout's grade. Also knows Draft Day, "
             "the separate draft of real NFL players, through its Draft desk.",
        mode=TeamMode.coordinate,
        model=specialist_model(),
        members=[build_scout("offense", **limits, debug=debug), build_scout("defense", **limits, debug=debug),
                 draft_desk.build_draft_desk(draft_file, debug=debug)],
        instructions=[
            "You are the scouting director of the Harbor City Herons (team id HAR) in a six-team American football "
            "league. You report to the general manager. You have no data of your own: your scouts do the looking.",
            f"Pro scout, offense covers {', '.join(OFFENSE)}. Pro scout, defense covers {', '.join(DEFENSE)}. "
            "Draft covers Draft Day, the separate draft of real NFL players, whose rosters are not the league's.",
            "Ask each scout once, naming every position of its own you need, and any salary limit. Never ask a "
            "scout about another scout's positions.",
            "Then report to the GM: a short summary of the best targets and what they'd take, and every player your "
            "scouts graded, best first, with the player id, grade and note exactly as the scout wrote them. Never "
            "add a player they didn't grade.",
        ],
        tool_call_limit=DIRECTOR_DELEGATIONS,
        share_member_interactions=True,
        store_member_responses=True,
        output_schema=ScoutingReport,
        parser_model=specialist_model(),
        parser_model_prompt=DIRECTOR_PARSER_PROMPT,
        debug_mode=debug,
    )


def _runs(response):
    """A team run and every member run under it, at any depth."""
    yield response
    for member in getattr(response, "member_responses", None) or []:
        yield from _runs(member)


def usage_of(response) -> list[dict]:
    return [{"input_tokens": getattr(r.metrics, "input_tokens", None),
             "output_tokens": getattr(r.metrics, "output_tokens", None),
             "cost": getattr(r.metrics, "cost", None)} for r in _runs(response) if getattr(r, "metrics", None)]


def scout_picks(response) -> list[ScoutPick]:
    """The scouts' own graded picks, from their structured reports; the director's if none."""
    picks = [p for r in _runs(response) if isinstance(r.content, ScoutReport) for p in r.content.picks]
    if not picks and isinstance(response.content, ScoutingReport):
        picks = response.content.picks
    return picks


def ground(picks: list[ScoutPick], found: dict[str, dict], summary: str) -> dict:
    """The scouts' grades and notes on the players plain Python found, with plain Python's
    numbers. A pick the list doesn't have is dropped; a position the scouts left empty
    though plain Python found players there is graded by the rules."""
    known = {t["id"]: t for f in found.values() for t in f["players"]}
    by_position: dict[str, list[dict]] = {pos: [] for pos in found}
    seen = set()
    for pick in picks:
        t = known.get(pick.player_id.strip().upper())
        if t is None or t["id"] in seen or len(by_position[t["position"]]) >= SHORTLIST:
            continue
        seen.add(t["id"])
        # A scout may grade lower than the numbers allow, never higher (the scouting skill).
        grade = max(pick.grade, "C" if t["games_out"] or not t["offer"] else "A")
        by_position[t["position"]].append(_entry(t, grade, pick.note.strip(), "scouts"))
    for pos, f in found.items():
        if not by_position[pos] and f["players"]:
            by_position[pos] = [_entry(t, rules_grade(t), rules_note(t), "rules") for t in f["players"][:SHORTLIST]]
    return {"by": "scouts", "positions": list(found), "summary": summary.strip() or _summary(found),
            "targets": [e for pos in found for e in by_position[pos]], "cost": None}


def scouting_prompt(positions: list[str], max_salary: float | None, max_added_payroll: float | None,
                    reason: str) -> str:
    limits = []
    if max_salary:
        limits.append(f"no incoming player over ${max_salary:.2f}M a season")
    if max_added_payroll is not None:
        limits.append(f"our payroll may grow at most ${max_added_payroll:.2f}M")
    return (f"The GM needs trade targets at {', '.join(positions)}, for this: {reason}\n"
            + (f"Limits (the scouts' tools already hold to them): {'; '.join(limits)}.\n" if limits else "")
            + "Ask the scout who covers each position, then report to the GM.")


# ---- Keeping reports -----------------------------------------------------------------------------

def _row(row) -> dict:
    return {"id": row["id"], "week": row["week"], "order_id": row["order_id"], "by": row["by"],
            "positions": json.loads(row["positions"]), "summary": row["summary"],
            "targets": json.loads(row["targets"]), "cost": row["cost"]}


def save_report(report: dict, order_id: int | None = None, db_file: Path | None = None) -> dict:
    db = connect(db_file)
    try:
        with db:
            week = db.execute("SELECT current_week FROM game").fetchone()[0]
            cur = db.execute("INSERT INTO scouting_reports (week, order_id, by, positions, summary, targets, cost) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (week, order_id, report["by"], json.dumps(report["positions"]), report["summary"],
                              json.dumps(report["targets"]), report["cost"]))
            return _row(db.execute("SELECT * FROM scouting_reports WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        db.close()


def report_for_order(order_id: int, db_file: Path | None = None) -> dict | None:
    """The latest report Scouting wrote for an order, or None."""
    db = connect(db_file)
    try:
        row = db.execute("SELECT * FROM scouting_reports WHERE order_id = ? ORDER BY id DESC LIMIT 1",
                         (order_id,)).fetchone()
        return _row(row) if row else None
    finally:
        db.close()


def reports(week: int | None = None, db_file: Path | None = None) -> list[dict]:
    db = connect(db_file)
    try:
        rows = db.execute("SELECT * FROM scouting_reports" + (" WHERE week = ?" if week else "") + " ORDER BY id",
                          (week,) if week else ()).fetchall()
        return [_row(r) for r in rows]
    finally:
        db.close()


# ---- Scouting for an order -----------------------------------------------------------------------

def positions_for(terms: dict, league: dict) -> list[str]:
    """The order's positions, or our weakest if it names none."""
    from agents import rivals
    return list(terms["positions"]) or rivals._weakest_positions(league, OUR_TEAM, WEAKEST)


async def scout_for_order(order: dict, standing: list[dict], db_file: Path | None = None, use_model: bool = True,
                          usage: list[dict] | None = None, team=None) -> dict:
    """Scouting's report for one order, kept with it. The scouting team grades the targets
    with the model; without it (or if the run fails) the rules do. `team` stands in for the
    scouting team in tests: anything with `arun(prompt)`."""
    league = load_league(db_file)
    terms = order["terms"]
    protected = {pid for o in standing for pid in o["terms"]["protected_player_ids"]}
    limits = dict(max_salary=terms.get("max_incoming_salary"), protected=protected,
                  max_added_payroll=terms.get("max_added_payroll"))
    positions = positions_for(terms, league)
    found = {pos: targets(pos, **limits, db_file=db_file, league=league) for pos in positions}

    report = rules_report(found)
    if use_model and any(f["players"] for f in found.values()):
        team = team or build_scouting_team(**limits, db_file=db_file)
        try:
            response = await team.arun(scouting_prompt(positions, limits["max_salary"], limits["max_added_payroll"],
                                                       terms["summary"]))
        except Exception as e:  # a failed run still leaves the GM the rules' report
            report["summary"] += f" (The scouts couldn't report: {e}.)"
        else:
            content = response.content
            summary = content.summary if isinstance(content, ScoutingReport) else ""
            report = ground(scout_picks(response), found, summary)
            spent = usage_of(response)
            costs = [u["cost"] for u in spent if u["cost"] is not None]
            report["cost"] = round(sum(costs), 6) if costs else None
            if usage is not None:
                usage.extend(spent)
    return save_report(report, order["id"], db_file)


async def ask(question: str, db_file: Path | None = None, team=None) -> dict:
    """Put one question to the scouting team on its own (the test bench). Returns the GM's
    `summarize()` of the run, with the report grounded as for an order: only players plain
    Python finds, with its numbers."""
    import time
    from agents.gm import summarize  # here: gm imports this module
    question = question.strip()
    if not question:
        raise ValueError("Type a question for the scouting team.")
    started = time.perf_counter()
    response = await (team or build_scouting_team(db_file=db_file)).arun(question)
    league = load_league(db_file)
    by_id = {p["id"]: p for p in league["players"]}
    picks = scout_picks(response)
    positions = list(dict.fromkeys(by_id[p.player_id.strip().upper()]["position"] for p in picks
                                   if p.player_id.strip().upper() in by_id))
    found = {pos: targets(pos, db_file=db_file, league=league) for pos in positions}
    content = response.content
    summary = content.summary if isinstance(content, ScoutingReport) else str(content or "")
    out = summarize(response, time.perf_counter() - started)
    out["report"] = ground(picks, found, summary)
    out["text"] = None
    return out


def report_text(report: dict | None) -> str:
    """The report as the GM's search reads it."""
    if not report:
        return "Scouting has no report for this order."
    lines = [f"Your scouting team's report: {report['summary']}"]
    if not report["targets"]:
        return lines[0] + "\nNo targets."
    lines.append("Targets, best first by position. The offer is the best one-for-one trade their team should take by "
                 "the league's measure; null means it would take more than one player:")
    for t in report["targets"]:
        offer = t["offer"]
        deal = (f"offer {offer['we_send'][0]['id']} {offer['we_send'][0]['name']} ({offer['we_send'][0]['position']}, "
                f"{offer['we_send'][0]['overall']} overall, ${offer['we_send'][0]['salary']:.2f}M): they score it "
                f"{offer['their_score']:+.2f} (margin {offer['margin']:+.2f}), we {offer['our_score']:+.2f}"
                if offer else "offer null")
        hurt = f"; out {t['games_out']} more games" if t["games_out"] else ""
        hurt += "".join(f" [{h}]" for h in t.get("history", []))
        lines.append(f"- {t['player_id']} {t['name']} ({t['position']}, {t['team']}), {t['overall']} overall, "
                     f"${t['salary']:.2f}M, {t['years_left']} years left, adds {t['unit_gain']:+.1f} to our units"
                     f"{hurt}. Grade {t['grade']}: {t['note']} Suggested {deal}.")
    return "\n".join(lines)
