"""The Trade Desk: proposing, evaluating and making trades (task 2.1).

The League Office (1.1 - 1.3) only reads the league. The Trade Desk is where
trades happen, and it keeps the deal between two teams in one place:

    propose  ->  open  ->  accept   -> the players move (rules.make_trade_in), logged in moves
                       ->  reject
                       ->  counter  -> a new open proposal the other way
                       ->  withdraw (by the team that proposed it)
                       ->  void     (it broke a rule when accepted, or a player in it was traded)

Plain Python owns every step. A proposal is checked against the 1.2 rules when
it is made, and again in the same transaction that moves the players, so an
offer that was legal on Monday can't go through illegally on Sunday. An
illegal proposal is refused and never stored.

evaluate() is what a team reads before it answers: the rule check, and for each
side the players in and out with their market value (the player-valuation
skill's own formula, 1.5), the payroll change, which starters change, and how
each simulator unit moves (agents/simulator.build_lineup, as the roster-impact
skill uses it), all computed here so no agent has to do the arithmetic.

Who may act is checked by team id: only the team a proposal is addressed to can
accept, reject or counter it, and only the team that made it can withdraw it.
The owner's approval of the Herons' own offers is G4's job, before a proposal
reaches the desk.

The functions at the bottom wrap these for the MCP server (servers/trade_desk.py):
they return JSON text and turn mistakes into {"error": ...}, as the League
Office's tools do.
"""

import importlib.util
import json
import sqlite3
from functools import cache
from pathlib import Path

from agents import rules
from agents.league_db import connect, load_league
from agents.simulator import build_lineup

SKILLS_DIR = Path(__file__).parent.parent / "skills"
STATUSES = ("open", "accepted", "rejected", "countered", "withdrawn", "void")


class TradeDeskError(ValueError):
    """A request the desk can't act on: no such proposal, the wrong team, or not open."""


# ---- Evaluating a trade ----------------------------------------------------------

@cache
def _valuation():
    """The player-valuation skill's script (task 1.5), so the desk and the skill price
    players with exactly the same formula."""
    path = SKILLS_DIR / "player-valuation" / "scripts" / "value_player.py"
    spec = importlib.util.spec_from_file_location("value_player", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _card(player: dict, players: list[dict]) -> dict:
    value = _valuation().value(player["position"], player["overall"], player["salary"],
                               player["age"], player["contract_years"], players=players)
    return {"id": player["id"], "name": player["name"], "position": player["position"], "age": player["age"],
            "overall": player["overall"], "salary": player["salary"], "years_left": player["contract_years"],
            "market_value": value["market_value"], "surplus_per_season": value["surplus_per_season"],
            "verdict": value["verdict"]}


def _starters(lineup, starters_per_position: dict) -> set[str]:
    return {p["id"] for pos, n in starters_per_position.items() for p in lineup.depth[pos][:n]}


def _side(league: dict, team: str, gives: list[str], gets: list[str]) -> dict:
    """One team's view of the trade: who it gives and gets, what that's worth, and how
    its starting lineup and the simulator's units change."""
    players = league["players"]
    by_id = {p["id"]: p for p in players}
    starters_per_position = league["rules"]["starters_per_position"]
    roster = [p for p in players if p["team_id"] == team]
    after = [p for p in roster if p["id"] not in gives] + [{**by_id[p], "team_id": team} for p in gets]
    before_lineup = build_lineup(team, roster, starters_per_position)
    after_lineup = build_lineup(team, after, starters_per_position)
    before_starters = _starters(before_lineup, starters_per_position)
    after_starters = _starters(after_lineup, starters_per_position)

    give_cards = [_card(by_id[p], players) for p in gives]
    get_cards = [_card(by_id[p], players) for p in gets]
    units = [{"unit": unit, "before": round(old, 2), "after": round(after_lineup.units[unit], 2),
              "change": round(after_lineup.units[unit] - old, 2)}
             for unit, old in before_lineup.units.items() if abs(after_lineup.units[unit] - old) >= 0.005]
    units.sort(key=lambda u: -abs(u["change"]))

    def total(cards, key):
        return round(sum(c[key] for c in cards), 2)

    return {
        "team_id": team, "gives": give_cards, "gets": get_cards,
        "salary_change": round(total(get_cards, "salary") - total(give_cards, "salary"), 2),
        "market_value_change": round(total(get_cards, "market_value") - total(give_cards, "market_value"), 2),
        "surplus_change": round(total(get_cards, "surplus_per_season") - total(give_cards, "surplus_per_season"), 2),
        "new_starters": [p for p in gets if p in after_starters],
        "starters_lost": [p for p in gives if p in before_starters],
        "benched": sorted(p for p in before_starters - after_starters if p not in gives),
        "unit_changes": units,
    }


def evaluate(trade: rules.Trade, db_file: Path | None = None) -> dict:
    """The rule check plus both teams' side of the trade. Changes nothing."""
    trade = trade.normalized()
    check = rules.check_trade(trade, db_file)
    result = {"legal": check["legal"], "rules": check}
    if any(v["rule"] == "invalid_trade" for v in check["violations"]):
        return result  # unknown teams or players: there's nothing to value
    league = load_league(db_file)
    result["teams"] = {trade.team_a: _side(league, trade.team_a, trade.a_sends, trade.b_sends),
                       trade.team_b: _side(league, trade.team_b, trade.b_sends, trade.a_sends)}
    result["note"] = ("market_value is what the league pays a veteran of that position and overall, $M per season; "
                      "surplus is market value minus salary. Unit changes are on the simulator's 25-99 scale.")
    return result


# ---- Proposals -------------------------------------------------------------------

def _week(db: sqlite3.Connection) -> int:
    return db.execute("SELECT current_week FROM game").fetchone()[0]


def _players(db: sqlite3.Connection, ids: list[str]) -> list[dict]:
    out = []
    for player_id in ids:
        row = db.execute("SELECT p.id, p.name, p.position, p.team_id, p.overall, c.salary FROM players p "
                         "JOIN contracts c ON c.player_id = p.id WHERE p.id = ?", (player_id,)).fetchone()
        out.append(dict(row) if row else {"id": player_id})
    return out


def _proposal(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    out = dict(row)
    out["sends"] = _players(db, json.loads(row["sends"]))
    out["receives"] = _players(db, json.loads(row["receives"]))
    return out


def _row(db: sqlite3.Connection, proposal_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM trade_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if row is None:
        raise TradeDeskError(f"There is no trade proposal #{proposal_id}.")
    return row


def _open_for(row: sqlite3.Row, team_id: str, side: str) -> None:
    """Only an open proposal can be answered, and only by the right team."""
    team_id = team_id.strip().upper()
    if row["status"] != "open":
        raise TradeDeskError(f"Proposal #{row['id']} is {row['status']}, not open.")
    owner = row["to_team_id"] if side == "to" else row["from_team_id"]
    if team_id != owner:
        verb = "answer" if side == "to" else "withdraw"
        raise TradeDeskError(f"Only {owner} can {verb} proposal #{row['id']}; {team_id} can't.")


def _trade(row: sqlite3.Row) -> rules.Trade:
    return rules.Trade(row["from_team_id"], json.loads(row["sends"]), row["to_team_id"], json.loads(row["receives"]))


def _insert(db: sqlite3.Connection, trade: rules.Trade, note: str, counter_of: int | None) -> int | dict:
    """Store a legal proposal and return its id, or return the rule check if it's illegal."""
    check = rules.check_trade_in(db, trade)
    if not check["legal"]:
        return check
    sends, receives = json.dumps(trade.a_sends), json.dumps(trade.b_sends)
    for row in db.execute("SELECT * FROM trade_proposals WHERE status = 'open' AND from_team_id = ? "
                          "AND to_team_id = ?", (trade.team_a, trade.team_b)):
        if (sorted(json.loads(row["sends"])), sorted(json.loads(row["receives"]))) == \
                (sorted(trade.a_sends), sorted(trade.b_sends)):
            raise TradeDeskError(f"Proposal #{row['id']} already offers {trade.team_b} this trade.")
    return db.execute("INSERT INTO trade_proposals (week, from_team_id, to_team_id, sends, receives, note, "
                      "counter_of) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (_week(db), trade.team_a, trade.team_b, sends, receives, note.strip(), counter_of)).lastrowid


def _decide(db: sqlite3.Connection, proposal_id: int, status: str, response: str, move_id: int | None = None):
    db.execute("UPDATE trade_proposals SET status = ?, response = ?, decided_week = ?, move_id = ? WHERE id = ?",
               (status, response.strip() or None, _week(db), move_id, proposal_id))


def _write(db_file: Path | None):
    db = connect(db_file)
    db.execute("BEGIN IMMEDIATE")  # one writer from the checks to the commit
    return db


def propose(from_team: str, sends: list[str], to_team: str, receives: list[str], note: str = "",
            db_file: Path | None = None) -> dict:
    """Offer a trade: from_team gives `sends` and gets `receives` from to_team. A legal
    offer is stored as open; an illegal one is refused with every rule it breaks."""
    trade = rules.Trade(from_team, sends, to_team, receives).normalized()
    db = _write(db_file)
    try:
        made = _insert(db, trade, note, None)
        if isinstance(made, dict):
            db.rollback()
            return {"proposed": False, "rules": made}
        proposal = _proposal(db, _row(db, made))
        db.commit()
        return {"proposed": True, "proposal": proposal}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def counter(proposal_id: int, team_id: str, sends: list[str], receives: list[str], note: str = "",
            db_file: Path | None = None) -> dict:
    """The team a proposal was offered to answers with its own terms: team_id gives `sends`
    and gets `receives`. The original is marked countered only if the counter is legal."""
    db = _write(db_file)
    try:
        original = _row(db, proposal_id)
        _open_for(original, team_id, "to")
        trade = rules.Trade(original["to_team_id"], sends, original["from_team_id"], receives).normalized()
        made = _insert(db, trade, note, proposal_id)
        if isinstance(made, dict):
            db.rollback()
            return {"proposed": False, "rules": made}
        _decide(db, proposal_id, "countered", f"Countered with proposal #{made}.")
        proposal = _proposal(db, _row(db, made))
        db.commit()
        return {"proposed": True, "proposal": proposal}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def respond(proposal_id: int, team_id: str, decision: str, reason: str = "", db_file: Path | None = None) -> dict:
    """Accept or reject an open proposal. Accepting checks the rules again and, if they
    pass, makes the trade; if they don't, the proposal is void and nothing moves. A
    completed trade voids every other open proposal that includes one of its players."""
    decision = decision.strip().lower()
    if decision not in ("accept", "reject"):
        raise TradeDeskError(f"decision must be 'accept' or 'reject', not {decision!r}.")
    db = _write(db_file)
    try:
        row = _row(db, proposal_id)
        _open_for(row, team_id, "to")
        if decision == "reject":
            _decide(db, proposal_id, "rejected", reason)
            result = {"accepted": False, "proposal": _proposal(db, _row(db, proposal_id))}
            db.commit()
            return result

        try:
            trade = rules.make_trade_in(db, _trade(row))
        except rules.IllegalMove as refused:
            _decide(db, proposal_id, "void", "Broke the league rules when accepted: " + str(refused))
            result = {"accepted": False, "proposal": _proposal(db, _row(db, proposal_id)),
                      "violations": [v.__dict__ for v in refused.violations]}
            db.commit()
            return result

        _decide(db, proposal_id, "accepted", reason, trade["move_id"])
        voided = _void_overtaken(db, proposal_id, set(trade["trade"]["a_sends"]) | set(trade["trade"]["b_sends"]))
        result = {"accepted": True, "proposal": _proposal(db, _row(db, proposal_id)), "trade": trade,
                  "voided": voided}
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _void_overtaken(db: sqlite3.Connection, accepted_id: int, moved: set[str]) -> list[int]:
    voided = []
    for row in db.execute("SELECT * FROM trade_proposals WHERE status = 'open'").fetchall():
        overlap = sorted(moved & (set(json.loads(row["sends"])) | set(json.loads(row["receives"]))))
        if overlap:
            names = ", ".join(f"{p['name']} ({p['id']})" for p in _players(db, overlap))
            _decide(db, row["id"], "void", f"{names} moved in the trade from proposal #{accepted_id}.")
            voided.append(row["id"])
    return voided


def withdraw(proposal_id: int, team_id: str, db_file: Path | None = None) -> dict:
    """The team that made an open proposal takes it back."""
    db = _write(db_file)
    try:
        _open_for(_row(db, proposal_id), team_id, "from")
        _decide(db, proposal_id, "withdrawn", "")
        result = {"proposal": _proposal(db, _row(db, proposal_id))}
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def proposals(team_id: str | None = None, status: str = "open", db_file: Path | None = None) -> list[dict]:
    """Proposals, oldest first: those a team made or was offered (or every team's), with
    one status or 'all'."""
    status = (status or "open").strip().lower()
    if status != "all" and status not in STATUSES:
        raise TradeDeskError(f"status must be 'all' or one of {', '.join(STATUSES)}, not {status!r}.")
    db = connect(db_file)
    try:
        sql, args = "SELECT * FROM trade_proposals WHERE 1 = 1", []
        if status != "all":
            sql, args = sql + " AND status = ?", [status]
        if team_id:
            team_id = team_id.strip().upper()
            sql, args = sql + " AND (from_team_id = ? OR to_team_id = ?)", args + [team_id, team_id]
        return [_proposal(db, row) for row in db.execute(sql + " ORDER BY id", args).fetchall()]
    finally:
        db.close()


def proposal(proposal_id: int, db_file: Path | None = None) -> dict:
    """One proposal and, while it's open, whether it would pass the rules right now."""
    db = connect(db_file)
    try:
        row = _row(db, proposal_id)
        out = _proposal(db, row)
        if row["status"] == "open":
            out["rules_now"] = rules.check_trade_in(db, _trade(row))
        return out
    finally:
        db.close()


# ---- The MCP tools (servers/trade_desk.py) ------------------------------------------
# Their docstrings are the descriptions the model sees.

def _tool(fn, *args, **kwargs) -> str:
    try:
        return json.dumps(fn(*args, **kwargs))
    except TradeDeskError as problem:
        return json.dumps({"error": str(problem)})


def evaluate_trade(team_a: str, a_sends: list[str], team_b: str, b_sends: list[str]) -> str:
    """Evaluate a possible trade without making or proposing it. Returns whether it is
    legal under the league rules this week (with every broken rule in plain English),
    and for each team: the players it gives and gets (overall, salary, years left, market
    value and surplus per season, and a verdict: bargain, fair or overpaid), its payroll
    change, the change in market value and surplus, which incoming players would start,
    which starters it loses or moves to the bench, and how each of its simulator units (e.g. deep_coverage,
    run_defense) would move. Use this before proposing or answering a trade.

    Args:
        team_a: three-letter id of one team, e.g. "HAR".
        a_sends: player ids team_a gives up, e.g. ["HAR-46"]. May be empty.
        team_b: three-letter id of the other team, e.g. "SUM".
        b_sends: player ids team_b gives up. May be empty, but not both sides.
    """
    return _tool(evaluate, rules.Trade(team_a, a_sends, team_b, b_sends))


def propose_trade(from_team: str, sends: list[str], to_team: str, receives: list[str], note: str = "") -> str:
    """Offer a trade to another team. from_team gives up `sends` and gets `receives` from
    to_team. The offer is checked against the league rules first: a legal one is stored
    as an open proposal for to_team to accept, reject or counter (returned with its id),
    and an illegal one is refused with every rule it breaks and is not stored. Nothing
    moves until to_team accepts.

    Args:
        from_team: three-letter id of the team making the offer, e.g. "HAR".
        sends: player ids from_team gives up, e.g. ["HAR-46"]. May be empty.
        to_team: three-letter id of the team the offer goes to, e.g. "SUM".
        receives: player ids from_team wants from to_team. May be empty, but not both sides.
        note: optional pitch to the other team, one or two sentences.
    """
    return _tool(propose, from_team, sends, to_team, receives, note)


def list_proposals(team_id: str = "", status: str = "open") -> str:
    """List trade proposals, oldest first, each with its id, week, who offered it to whom,
    the players on each side (name, position, overall, salary), the note, its status and
    the answer. `sends` are the players the offering team (from_team_id) gives up;
    `receives` are the ones it gets.

    Args:
        team_id: only proposals this team made or was offered, e.g. "HAR". Empty for every team.
        status: open (the default), accepted, rejected, countered, withdrawn, void, or all.
    """
    return _tool(proposals, team_id or None, status)


def get_proposal(proposal_id: int) -> str:
    """Get one trade proposal by id. While it is open, it includes `rules_now`: whether it
    would still pass the league rules if accepted this week, and every rule it would break.

    Args:
        proposal_id: the proposal's id, from propose_trade or list_proposals.
    """
    return _tool(proposal, proposal_id)


def respond_to_proposal(proposal_id: int, team_id: str, decision: str, reason: str = "") -> str:
    """Accept or reject an open trade proposal made to your team. Accepting checks the
    league rules again and, if they pass, makes the trade: the players change teams and
    the trade goes in the move log. This cannot be undone. If the rules fail now, the
    proposal becomes void and nothing moves. Only the team the proposal was offered to
    can answer it.

    Args:
        proposal_id: the proposal's id.
        team_id: three-letter id of your team, which must be the team the offer was made to.
        decision: "accept" or "reject".
        reason: optional one-sentence reason, shown to the team that offered it.
    """
    return _tool(respond, proposal_id, team_id, decision, reason)


def counter_proposal(proposal_id: int, team_id: str, sends: list[str], receives: list[str],
                     note: str = "") -> str:
    """Answer an open proposal made to your team with different terms. team_id gives up
    `sends` and gets `receives` from the team that made the original offer. The counter is
    checked against the league rules: if it is legal, it becomes a new open proposal to
    the other team and the original is marked countered; if not, it is refused and the
    original stays open.

    Args:
        proposal_id: the id of the proposal you are answering.
        team_id: three-letter id of your team, which must be the team the offer was made to.
        sends: player ids your team gives up. May be empty.
        receives: player ids your team wants from the other team. May be empty, but not both sides.
        note: optional one or two sentences for the other team.
    """
    return _tool(counter, proposal_id, team_id, sends, receives, note)


def withdraw_proposal(proposal_id: int, team_id: str) -> str:
    """Take back an open trade proposal your team made. Only the team that made it can.

    Args:
        proposal_id: the proposal's id.
        team_id: three-letter id of your team, which must be the team that made the offer.
    """
    return _tool(withdraw, proposal_id, team_id)


def trade_log() -> str:
    """Every trade made this season, oldest first: the week and each player who moved,
    from which team to which."""
    return json.dumps({"moves": rules.move_log()})


READ_TOOLS = [evaluate_trade, list_proposals, get_proposal, trade_log]
WRITE_TOOLS = [propose_trade, counter_proposal, withdraw_proposal]
TRADE_TOOLS = [respond_to_proposal]  # the one tool that moves players
