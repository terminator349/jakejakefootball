"""The front office org chart (task 4.3): the agent hierarchy, and a short line
on what each member has done this week, for a screen in the game.

Plain Python only - nothing here asks a model anything. The hierarchy is read
from the GM's own Team (`agents/gm.py`) rather than written out separately, so
it can't drift from who is actually on it. Each member's "this week" line comes
from what's already in the save (orders, proposed moves, the briefing,
injuries), the same facts G3's briefing and G4's desk already show the owner,
so the screen costs nothing and needs no API key.
"""

import json
from pathlib import Path

from agents import briefing, deadline, draft_desk, game_loop, gm, league_db, orders, season
from agents.game_loop import _ordinal, _rating_name
from agents.gm import OUR_TEAM


def hierarchy() -> list[dict]:
    """Owner -> GM -> specialists. No League Office tools are connected: only the
    static name and role each member was built with is read, so this is cheap."""
    team = gm.build_gm_team(None, None, None, None)
    return [{"name": "Owner", "role": "Sets priorities; approves or vetoes every move.", "reports_to": None},
            {"name": team.name, "role": team.role, "reports_to": "Owner"},
            *({"name": m.name, "role": m.role, "reports_to": team.name} for m in team.members)]


def _team_names(league: dict) -> dict[str, str]:
    return {t["id"]: t["city"] for t in league["teams"]}


def _gm_activity(week: int, league: dict, db_file: Path | None) -> list[str]:
    lines = []
    brief = briefing.stored(week, db_file)
    if brief:
        lines.append(f"Wrote this week's briefing: “{brief['headline']}”")
    for order in orders.orders("all", db_file):
        if order["week"] == week:
            lines.append(f"Took an order from the owner: “{order['text']}”")
    names = _team_names(league)
    for move in orders.moves(db_file):
        if move.get("decided_week") == week and move["status"] in ("approved", "vetoed"):
            lines.append(f"The owner {move['status']} its proposed move with {names.get(move['team_id'], move['team_id'])}.")
    return lines or ["Nothing from the GM yet this week."]


def _analytics_activity(league: dict) -> list[str]:
    worst = deadline.comparisons(league)[0]
    return [f"Flagged {_rating_name(worst)} as our weakest spot: {_ordinal(worst['rank'])} of {len(league['teams'])}, "
            f"{abs(worst['gap'])} below the league average."]


def _cap_activity(week: int, league: dict, db_file: Path | None) -> list[str]:
    cap = league["rules"]["salary_cap"]
    payroll = round(sum(p["salary"] for p in league["players"] if p["team_id"] == OUR_TEAM), 1)
    lines = [f"Holding ${payroll}M payroll, ${round(cap - payroll, 1)}M space under the ${cap:.0f}M hard cap."]
    filed = [m for m in orders.moves(db_file) if m["week"] == week]
    if filed:
        lines.append(f"Checked {len(filed)} proposed move{'s' if len(filed) != 1 else ''} this week against the cap.")
    return lines


def _draft_activity() -> list[str]:
    summary = json.loads(draft_desk.build_draft_tools()[0]())
    if "error" in summary:
        return ["No draft has been run yet."]
    ours = next((t for t in summary["teams"] if t["team_id"] == OUR_TEAM), None)
    if ours is None:
        return ["No draft has been run yet."]
    return [f"Last active at the rookie draft: {ours['players']} picks, average overall {ours['average_overall']} "
            f"({_ordinal(ours['rank_by_average_overall'])} of {len(summary['teams'])})."]


def _coaching_activity(week: int, db_file: Path | None) -> list[str]:
    hurt = league_db.current_injuries(OUR_TEAM, db_file)
    new = [p for p in hurt if p["since_week"] == week]
    if new:
        lead = f"Reset the depth chart after {new[0]['name']} ({new[0]['position']}) went down"
        lines = [lead + (f" and {len(new) - 1} other player(s)." if len(new) > 1 else ".")]
    else:
        lines = ["No depth chart changes this week."]
    this_week = game_loop.overview()["this_week"]
    if this_week:
        opp = this_week["opponent"]
        lines.append(f"Planning this week's game around {opp['city']} {opp['name']}.")
    return lines


def _medical_activity(week: int, db_file: Path | None) -> list[str]:
    hurt = league_db.current_injuries(OUR_TEAM, db_file)
    new = [p for p in hurt if p["since_week"] == week]
    if new:
        names = ", ".join(f"{p['name']} ({p['position']}, out {p['games_remaining']})" for p in new)
        return [f"{len(new)} new injur{'y' if len(new) == 1 else 'ies'} this week: {names}."]
    if hurt:
        return [f"No new injuries this week; {len(hurt)} still working back, including "
                f"{hurt[0]['name']} ({hurt[0]['position']})."]
    return ["Clean bill of health this week."]


def chart(db_file: Path | None = None) -> dict:
    """The hierarchy and this week's activity, for the org chart screen."""
    week = season.current_week(db_file)
    league = league_db.load_league(db_file)
    return {"week": week, "hierarchy": hierarchy(),
            "activity": {"General Manager": _gm_activity(week, league, db_file),
                        "Analytics": _analytics_activity(league),
                        "Cap & Contracts": _cap_activity(week, league, db_file),
                        "Draft": _draft_activity(),
                        "Coaching": _coaching_activity(week, db_file),
                        "Medical": _medical_activity(week, db_file)}}
