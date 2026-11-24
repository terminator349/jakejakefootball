"""The trade deadline as a game event (task 2.3).

Trades close after the deadline week (week 9): the 1.2 rules refuse any trade
after it. This module makes the deadline something the owner plays:

- **The countdown.** From two weeks before the deadline week, the week screen
  shows the deadline card: the weeks left, our biggest weakness, the cap space
  and the trades we've made. The GM's briefing gets the same facts
  (`briefing_facts`), so it warns the owner, and in the deadline week it leads
  with it.
- **Working the deadline.** One click and the GM runs the whole scenario
  (`work`): it finds the weakness, values targets and builds offers the other
  side will take, with the G4 search and the negotiation skill. Without an API
  key a plain-Python search (`rules_search`) does the same by the league's
  appraisal. Either way the moves go in front of the owner, each approval is
  answered by the rival's GM (2.2), and a counter comes back under Offers to us.
- **Closing the desk.** Once the week moves past the deadline, every move still
  waiting for the owner is void (`close`). G5's `between_weeks`, which runs
  first, closes the open offers: ours are refused by the rules, and the rivals'
  offers to us expire.
- **What our trades changed** (`since_our_trades`): for each position we traded
  for, the unit's rating and rank before our trades and now, and the gap to the
  team just above us, so the briefing can say "4 points behind Mesa Verde
  instead of 21.5" under G3's number check.
"""

import copy
from pathlib import Path

from agents import negotiation, orders, rules, scouting, season
from agents.game_loop import _ordinal, _rating_name
from agents.league_db import load_league
from agents.tools import _starter_average

OUR_TEAM = "HAR"
WINDOW = 2              # the deadline card shows from this many weeks before the deadline week
PREFIX = "Work the deadline:"  # how a deadline order starts, so the week screen can find it


# ---- Where the season is ------------------------------------------------------------------

def phase(week: int, deadline: int) -> str:
    """'open', 'approaching' (the WINDOW weeks before), 'deadline_week' or 'closed'."""
    if week > deadline:
        return "closed"
    if week == deadline:
        return "deadline_week"
    return "approaching" if week >= deadline - WINDOW else "open"


def comparisons(league: dict, team: str = OUR_TEAM) -> list[dict]:
    """compare_to_league's rows, worst gap first, for any league dict (also one with our
    trades undone)."""
    team_ids = [t["id"] for t in league["teams"]]
    rows = []
    for position in league["rules"]["starters_per_position"]:
        sample = next(p for p in league["players"] if p["position"] == position)
        for rating in ["overall", *sample["ratings"]]:
            averages = {tid: _starter_average(league, tid, position, rating) for tid in team_ids}
            ours = averages[team]
            league_avg = sum(averages.values()) / len(averages)
            rows.append({"position": position, "rating": rating, "team_avg": round(ours, 1),
                         "league_avg": round(league_avg, 1), "gap": round(ours - league_avg, 1),
                         "rank": 1 + sum(1 for v in averages.values() if v > ours), "averages": averages})
    rows.sort(key=lambda row: row["gap"])
    return rows


def _team_name(league: dict, team_id: str) -> str:
    return next(t["city"] for t in league["teams"] if t["id"] == team_id)


def _cap_space(league: dict) -> float:
    payroll = sum(p["salary"] for p in league["players"] if p["team_id"] == OUR_TEAM)
    return round(league["rules"]["salary_cap"] - payroll, 2)


# ---- Our trades and what they changed ---------------------------------------------------------

def _our_moves(db_file: Path | None) -> list[dict]:
    return [m for m in rules.move_log(db_file)
            if OUR_TEAM in {p["from_team_id"] for p in m["players"]} | {p["to_team_id"] for p in m["players"]}]


def our_trades(db_file: Path | None = None) -> list[str]:
    """Our trades this season, oldest first, in a line each."""
    league = load_league(db_file)
    position = {p["id"]: p["position"] for p in league["players"]}
    lines = []
    for move in _our_moves(db_file):
        got = [p for p in move["players"] if p["to_team_id"] == OUR_TEAM]
        sent = [p for p in move["players"] if p["from_team_id"] == OUR_TEAM]
        other = next(p["from_team_id"] for p in got) if got else next(p["to_team_id"] for p in sent)

        def names(ps):
            named = [f"{p['name']} ({position[p['player_id']]})" for p in ps]
            return ", ".join(named[:-1]) + " and " + named[-1] if len(named) > 1 else (named or ["nobody"])[0]
        lines.append(f"Week {move['week']}: {names(got)} from {_team_name(league, other)} for {names(sent)}")
    return lines


def _before_our_trades(league: dict, moves: list[dict]) -> dict:
    """The league with our trades undone, newest first: every player back where he came from."""
    before = copy.deepcopy(league)
    by_id = {p["id"]: p for p in before["players"]}
    for move in reversed(moves):
        for p in move["players"]:
            by_id[p["player_id"]]["team_id"] = p["from_team_id"]
    return before


def _neighbour(averages: dict, team: str) -> tuple[str, str] | None:
    """The team just above us on this rating ('behind'), or just below if we're first ('ahead')."""
    ours = averages[team]
    above = {t: v for t, v in averages.items() if t != team and v > ours}
    if above:
        return "behind", min(above, key=above.get)
    below = {t: v for t, v in averages.items() if t != team}
    return ("ahead", max(below, key=below.get)) if below else None


def since_our_trades(db_file: Path | None = None) -> list[dict]:
    """For each position we traded for: the unit we were fixing (our worst rating there
    before the trades), its rating and rank before and now, and how far we were and are
    from the team just above us now (or just below, if we're first)."""
    moves = _our_moves(db_file)
    if not moves:
        return []
    league = load_league(db_file)
    before = _before_our_trades(league, moves)
    n = len(league["teams"])
    position = {p["id"]: p["position"] for p in league["players"]}
    out = []
    for pos in dict.fromkeys(position[p["player_id"]] for m in moves for p in m["players"]
                             if p["to_team_id"] == OUR_TEAM):
        then = next(r for r in comparisons(before) if r["position"] == pos)
        now = next(r for r in comparisons(league) if r["position"] == pos and r["rating"] == then["rating"])
        item = {"unit": _rating_name(now), "position": pos, "before": then["team_avg"], "now": now["team_avg"],
                "rank_before": f"{_ordinal(then['rank'])} of {n}", "rank_now": f"{_ordinal(now['rank'])} of {n}"}
        if (near := _neighbour(now["averages"], OUR_TEAM)):
            team = near[1]

            def gap(row):
                diff = round(row["averages"][OUR_TEAM] - row["averages"][team], 1)
                return f"{abs(diff)} {'ahead' if diff > 0 else 'behind'}" if diff else "level"
            item["against"] = {"team": _team_name(league, team), "before": gap(then), "now": gap(now)}
        out.append(item)
    return out


# ---- The deadline card and the briefing ---------------------------------------------------------

def _deadline_orders(db_file: Path | None) -> list[dict]:
    return [o for o in orders.orders("all", db_file) if o["text"].startswith(PREFIX)]


def status(db_file: Path | None = None) -> dict:
    """The deadline as the week screen shows it."""
    league = load_league(db_file)
    week, deadline = season.current_week(db_file), league["rules"]["trade_deadline_week"]
    worst = comparisons(league)[0]
    runs = [o for o in _deadline_orders(db_file) if o["week"] == week]
    return {"week": week, "deadline_week": deadline, "phase": phase(week, deadline),
            "weeks_left_after_this_one": deadline - week if week <= deadline else None,
            "weakness": {"position": worst["position"], "unit": _rating_name(worst),
                         "rank": f"{_ordinal(worst['rank'])} of {len(league['teams'])}",
                         "our_rating": worst["team_avg"], "league_average": worst["league_avg"]},
            "cap_space": _cap_space(league), "trades": our_trades(db_file), "since": since_our_trades(db_file),
            "worked": {"order_id": runs[-1]["id"], "reply": runs[-1]["reply"]} if runs else None}


def briefing_facts(db_file: Path | None = None) -> dict:
    """What the briefing may say about the deadline (added to G3's facts)."""
    league = load_league(db_file)
    week, deadline = season.current_week(db_file), league["rules"]["trade_deadline_week"]
    now = phase(week, deadline)
    out = {"trade_deadline": "passed" if now == "closed" else
           {"after_week": deadline, "weeks_left_after_this_one": deadline - week}}
    if now == "deadline_week":
        out["trade_deadline"]["warning"] = "Last chance to trade: the Trade Desk closes after this week's games."
    elif now == "approaching":
        out["trade_deadline"]["warning"] = "The trade deadline is close."
    if (trades := our_trades(db_file)):
        out["our_trades"] = trades
        out["since_our_trades"] = since_our_trades(db_file)
    return out


# ---- Working the deadline --------------------------------------------------------------------

def _reason(league: dict, t: dict) -> str:
    offer = t["offer"]
    send = offer["we_send"][0]
    return (f"{t['name']} ({t['position']}, {t['overall']} overall, ${t['salary']:.2f}M) would start for us; "
            f"Scouting grades him {t['grade']}. {_team_name(league, t['team_id'])} scores the trade "
            f"{offer['their_score']:+.2f}, above the {offer['margin']:+.2f} a team needs to say yes, and it's worth "
            f"{offer['our_score']:+.2f} to us. We send {send['name']} ({send['position']}, {send['overall']} overall, "
            f"${send['salary']:.2f}M).")


def rules_search(db_file: Path | None = None):
    """The deadline search without a model: a searcher for orders.work_order. It files the
    offers in Scouting's report (4.1), best for us first: one-for-one trades for a player who
    would start for us, which his team scores at least its margin, and so do we."""
    async def search(order, standing, league, week):
        report = scouting.report_for_order(order["id"], db_file)
        deals = sorted((t for t in (report["targets"] if report else []) if t["offer"] and not t["games_out"]),
                       key=lambda t: -t["offer"]["our_score"])
        filed, sent, targets = 0, set(), set()
        for t in deals:
            if filed == orders.MAX_PROPOSALS:
                break
            send = t["offer"]["we_send"][0]["id"]
            if send in sent or t["player_id"] in targets:
                continue
            try:
                orders.file_move(order["id"], t["team_id"], [send], [t["player_id"]], _reason(league, t), db_file)
            except orders.MoveRefused:
                continue
            filed, sent, targets = filed + 1, sent | {send}, targets | {t["player_id"]}
        unit = order["terms"]["summary"]
        reply = (f"I've put {filed} deadline move{'s' if filed != 1 else ''} in front of you, each one the other "
                 "team should take by the league's measure." if filed else
                 f"I couldn't find a trade that the other team would take and that's worth it for us. {unit}")
        return reply, None
    return search


async def work(db_file: Path | None = None, use_model: bool = True, searcher=None) -> dict:
    """The GM works the deadline: an order to upgrade our biggest weakness, worked by the
    GM's search (with the model) or the rules' search. The owner approves each move."""
    st = status(db_file)
    deadline = st["deadline_week"]
    if st["phase"] == "closed":
        raise orders.OrderError(f"Trades closed after week {deadline}, the trade deadline.")
    if st["phase"] == "open":
        raise orders.OrderError(f"The deadline is after week {deadline}; your GM works it from week "
                                f"{deadline - WINDOW}. Give an order to trade before then.")
    weak = st["weakness"]
    league = load_league(db_file)
    text = f"{PREFIX} upgrade {weak['unit']} ({weak['position']}) before trades close after week {deadline}."
    terms = orders.OrderTerms(
        summary=f"Upgrade {weak['unit']} ({weak['position']}), {weak['rank']}, before the deadline, within the "
                "league rules and your standing orders.",
        wants_trades=True, positions=[weak["position"]], max_incoming_salary=None, max_added_payroll=None,
        protected_player_ids=[])
    order_id = orders.save_order(text, orders.ground_terms(terms, league), db_file)
    by = "model" if use_model and searcher is None else "rules"
    if not use_model and searcher is None:
        searcher = rules_search(db_file)
    return {**await orders.work_order(order_id, db_file, searcher), "by": by}


# ---- Closing the desk -------------------------------------------------------------------------

def close(db_file: Path | None = None) -> list[str]:
    """Once the week has moved past the deadline: void the moves still waiting. Returns the news."""
    week, deadline = season.current_week(db_file), load_league(db_file)["rules"]["trade_deadline_week"]
    if week != deadline + 1:
        return []
    voided = orders.void_waiting(f"The trade deadline passed: trades closed after week {deadline}.", db_file)
    return [f"The trade deadline has passed: trades are closed for the season."
            + (f" {voided} move{'s' if voided != 1 else ''} waiting for you went with it." if voided else "")]
