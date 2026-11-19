"""The owner's orders and approvals (task G4).

The owner gives an order in plain words ("Upgrade safety. Stay under $5M a year.
Don't trade Okafor."). The GM turns it into proposed moves, and the owner
approves or vetoes each one. Nothing goes to another team until it's approved.

    order  ->  terms (the GM reads them)  ->  the GM searches and files moves
           ->  owner approves  ->  our offer on the Trade Desk (2.1), for the other team to answer
           ->  owner vetoes    ->  dropped

The model reads and searches; plain Python holds it to the order. The GM reads
the order into `OrderTerms`: the positions to upgrade, the most an incoming
player may earn, the most our payroll may grow, and players we won't trade.
The owner sees those terms, and `check_move()` enforces them: the GM can only
file a move through `propose_to_owner`, which refuses one that breaks a league
rule (the Trade Desk's evaluation), sends away a player any active order
protects, or breaks this order's salary limits or positions. Orders stand all
season until the owner cancels them, so "don't trade Okafor" holds for every
later order too.

Approving re-checks the move against the rules and the orders as they are then,
and proposes it on the Trade Desk as the Herons' offer. The other team answers
it there: the rival GMs (2.2) will; until then it waits, and the bench's MCP tab
can answer for them.

The GM searches on its own here, with the League Office's read tools, the Trade
Desk's evaluate_trade and a target list (`trade_targets`). The scouting team
(4.1) takes over finding targets later.
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters
from pydantic import BaseModel, Field

from agents import rules, skills
from agents import trade_desk as desk
from agents.league_db import connect, load_league

PROJECT_ROOT = Path(__file__).parent.parent
OUR_TEAM = "HAR"
MAX_PROPOSALS = 3        # moves the GM may file for one order
SEARCH_TOOL_LIMIT = 24   # a search takes about 6-15 calls
READ_ATTEMPTS = 2        # DeepSeek's structured output now and then comes back empty
TARGETS_SHOWN = 12


class OrderError(ValueError):
    """A request about orders or proposed moves the game can't act on."""


class MoveRefused(OrderError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(" ".join(problems))


class OrderTerms(BaseModel):
    """What the GM understood the owner to want. Plain Python enforces every field but the summary."""

    summary: str = Field(description="The order restated in one plain sentence, as you will carry it out.")
    wants_trades: bool = Field(description="True if the owner wants you to look for trades now; false for "
                                           "an order that only sets a rule, e.g. 'never trade Okafor'.")
    positions: list[str] = Field(description="Positions the owner wants upgraded, as league position codes "
                                             "(QB, RB, WR, TE, OL, DL, LB, CB, S, K, P). Empty if none named.")
    max_incoming_salary: float | None = Field(description="The most, in $M per season, any player we get may "
                                                          "earn, if the owner set a limit. Null if not.")
    max_added_payroll: float | None = Field(description="The most, in $M per season, our total payroll may "
                                                        "grow, if the owner set a limit. Null if not.")
    protected_player_ids: list[str] = Field(description="Ids of our players the owner says not to trade, "
                                                        "copied from the roster list. Empty if none.")


# ---- Reading the order --------------------------------------------------------------

READ_INSTRUCTIONS = [
    "You are the general manager of the Harbor City Herons (team id HAR). The owner has given you an order. "
    "Read it into its terms. Take only what the owner said: don't add limits or players they didn't name.",
    "A salary limit like 'stay under $5M a year' or 'nobody over $5M' is max_incoming_salary. A limit on the "
    "total, like 'don't add more than $3M to payroll', is max_added_payroll. Write amounts in $M (5, not 5000000).",
    "For players the owner says not to trade, find them in our roster list and copy their ids exactly. If "
    "the owner names a player only by a name more than one of our players shares, protect all of them and "
    "name each one in the summary, so the owner can see who you mean.",
]


def build_reader(debug: bool = False) -> Agent:
    from agents.analytics import specialist_model
    return Agent(name="General Manager", model=specialist_model(), instructions=READ_INSTRUCTIONS,
                 output_schema=OrderTerms, debug_mode=debug)


def _usage(run) -> dict:
    metrics = run.metrics
    return {"input_tokens": getattr(metrics, "input_tokens", None),
            "output_tokens": getattr(metrics, "output_tokens", None), "cost": getattr(metrics, "cost", None)}


async def read_order(text: str, league: dict, reader: Agent | None = None) -> tuple[OrderTerms, list[dict]]:
    reader = reader or build_reader()
    roster = [f"{p['id']} {p['name']} ({p['position']})" for p in league["players"] if p["team_id"] == OUR_TEAM]
    prompt = f"The owner's order: {text}\n\nOur roster (id, name, position):\n" + "\n".join(roster)
    usage = []
    for _ in range(READ_ATTEMPTS):
        run = await reader.arun(prompt)
        usage.append(_usage(run))
        if isinstance(run.content, OrderTerms):
            return run.content, usage
    raise OrderError("Your GM couldn't read that order. Try saying it another way.")


def ground_terms(terms: OrderTerms, league: dict) -> dict:
    """The terms as plain Python will enforce them: real positions, our own players, sane limits."""
    positions = list(league["rules"]["starters_per_position"])
    ours = {p["id"]: p for p in league["players"] if p["team_id"] == OUR_TEAM}
    out = terms.model_dump()
    out["positions"] = list(dict.fromkeys(p.strip().upper() for p in terms.positions
                                          if p.strip().upper() in positions))
    out["protected_player_ids"] = list(dict.fromkeys(p.strip().upper() for p in terms.protected_player_ids
                                                     if p.strip().upper() in ours))
    out["protected"] = [f"{ours[p]['name']} ({p})" for p in out["protected_player_ids"]]
    for key in ("max_incoming_salary", "max_added_payroll"):
        value = out[key]
        out[key] = round(value, 2) if isinstance(value, (int, float)) and value > 0 else None
    return out


# ---- Storage ----------------------------------------------------------------------

def _week(db: sqlite3.Connection) -> int:
    return db.execute("SELECT current_week FROM game").fetchone()[0]


def _order(row: sqlite3.Row) -> dict:
    return {**dict(row), "terms": json.loads(row["terms"])}


def _order_row(db: sqlite3.Connection, order_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise OrderError(f"There is no order #{order_id}.")
    return row


def save_order(text: str, terms: dict, db_file: Path | None = None) -> int:
    db = connect(db_file)
    try:
        with db:
            return db.execute("INSERT INTO orders (week, text, terms) VALUES (?, ?, ?)",
                              (_week(db), text, json.dumps(terms))).lastrowid
    finally:
        db.close()


def _finish_order(order_id: int, reply: str, cost: float | None, db_file: Path | None) -> None:
    db = connect(db_file)
    try:
        with db:
            db.execute("UPDATE orders SET reply = ?, cost = ? WHERE id = ?", (reply, cost, order_id))
    finally:
        db.close()


def orders(status: str = "active", db_file: Path | None = None) -> list[dict]:
    db = connect(db_file)
    try:
        sql = "SELECT * FROM orders" + ("" if status == "all" else " WHERE status = ?") + " ORDER BY id"
        return [_order(row) for row in db.execute(sql, () if status == "all" else (status,))]
    finally:
        db.close()


def cancel_order(order_id: int, db_file: Path | None = None) -> dict:
    """The owner withdraws a standing order. Its moves still waiting for approval go with it."""
    db = connect(db_file)
    try:
        with db:
            row = _order_row(db, order_id)
            if row["status"] != "active":
                raise OrderError(f"Order #{order_id} is already {row['status']}.")
            db.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
            db.execute("UPDATE gm_proposals SET status = 'void', owner_note = 'You cancelled the order.', "
                       "decided_week = ? WHERE order_id = ? AND status = 'waiting'", (_week(db), order_id))
            return _order(_order_row(db, order_id))
    finally:
        db.close()


# ---- Checking a move against the rules and the orders ---------------------------------------

def _ids(values) -> list[str]:
    return [v.strip().upper() for v in values]


def check_move(order_id: int, team_id: str, we_send: list[str], we_get: list[str], db_file: Path | None = None,
               skip_proposal: int | None = None) -> tuple[list[str], dict]:
    """Everything wrong with a move the GM wants to propose for an order, in words the GM
    and the owner can read, plus the Trade Desk's evaluation of it. No problems: it can go
    to the owner."""
    team_id, we_send, we_get = team_id.strip().upper(), _ids(we_send), _ids(we_get)
    if team_id == OUR_TEAM:
        return ["A move needs another team: team_id is the team we trade with, not HAR."], {}
    evaluation = desk.evaluate(rules.Trade(OUR_TEAM, we_send, team_id, we_get), db_file)
    problems = [v["message"] for v in evaluation["rules"]["violations"]]
    if "teams" not in evaluation:
        return problems, evaluation

    db = connect(db_file)
    try:
        order = _order(_order_row(db, order_id))
        standing = [_order(r) for r in db.execute("SELECT * FROM orders WHERE status = 'active' ORDER BY id")]
        waiting = db.execute("SELECT * FROM gm_proposals WHERE status = 'waiting' AND team_id = ?",
                             (team_id,)).fetchall()
    finally:
        db.close()

    ours = evaluation["teams"][OUR_TEAM]
    sent = {p["id"]: p for p in ours["gives"]}
    for other in standing:
        for player_id in other["terms"]["protected_player_ids"]:
            if player_id in sent:
                problems.append(f"{sent[player_id]['name']} ({player_id}) can't be traded: your order "
                                f"#{other['id']} (\"{other['text']}\") protects him.")
    terms = order["terms"]
    if (limit := terms["max_incoming_salary"]) is not None:
        for p in ours["gets"]:
            if p["salary"] > limit:
                problems.append(f"{p['name']} earns ${p['salary']:.2f}M, over the order's ${limit:.2f}M limit.")
    if (limit := terms["max_added_payroll"]) is not None and ours["salary_change"] > limit:
        problems.append(f"Our payroll would grow ${ours['salary_change']:.2f}M, over the order's "
                        f"${limit:.2f}M limit.")
    if terms["positions"] and not any(p["position"] in terms["positions"] for p in ours["gets"]):
        problems.append(f"The order is for {', '.join(terms['positions'])}; this move brings in nobody there.")
    for row in waiting:
        if row["id"] != skip_proposal and (sorted(json.loads(row["sends"])), sorted(json.loads(row["receives"]))) \
                == (sorted(we_send), sorted(we_get)):
            problems.append(f"Move #{row['id']} already proposes this trade.")
    return problems, evaluation


def file_move(order_id: int, team_id: str, we_send: list[str], we_get: list[str], reason: str,
              db_file: Path | None = None) -> int:
    """Put a checked move in front of the owner. Raises MoveRefused with every problem."""
    db = connect(db_file)
    try:
        filed = db.execute("SELECT COUNT(*) FROM gm_proposals WHERE order_id = ?", (order_id,)).fetchone()[0]
    finally:
        db.close()
    if filed >= MAX_PROPOSALS:
        raise MoveRefused([f"You've already proposed {MAX_PROPOSALS} moves for this order, the most allowed."])
    if not reason.strip():
        raise MoveRefused(["Give the owner a reason for the move."])
    problems, _ = check_move(order_id, team_id, we_send, we_get, db_file)
    if problems:
        raise MoveRefused(problems)
    db = connect(db_file)
    try:
        with db:
            return db.execute("INSERT INTO gm_proposals (order_id, week, team_id, sends, receives, reason) "
                              "VALUES (?, ?, ?, ?, ?, ?)",
                              (order_id, _week(db), team_id.strip().upper(), json.dumps(_ids(we_send)),
                               json.dumps(_ids(we_get)), reason.strip())).lastrowid
    finally:
        db.close()


# ---- The owner decides ----------------------------------------------------------------

def _move_row(db: sqlite3.Connection, move_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM gm_proposals WHERE id = ?", (move_id,)).fetchone()
    if row is None:
        raise OrderError(f"There is no proposed move #{move_id}.")
    if row["status"] != "waiting":
        raise OrderError(f"Move #{move_id} is {row['status']}, not waiting for you.")
    return row


def _decide(move_id: int, status: str, note: str, desk_id: int | None, db_file: Path | None) -> None:
    db = connect(db_file)
    try:
        with db:
            db.execute("UPDATE gm_proposals SET status = ?, owner_note = ?, decided_week = ?, desk_proposal_id = ? "
                       "WHERE id = ?", (status, note.strip() or None, _week(db), desk_id, move_id))
    finally:
        db.close()


def approve(move_id: int, note: str = "", db_file: Path | None = None) -> dict:
    """The owner says yes: the move is checked again and offered on the Trade Desk. If the
    league or the orders changed so that it no longer passes, it's void and nothing is sent."""
    db = connect(db_file)
    try:
        row = _move_row(db, move_id)
    finally:
        db.close()
    sends, receives = json.loads(row["sends"]), json.loads(row["receives"])
    problems, _ = check_move(row["order_id"], row["team_id"], sends, receives, db_file, skip_proposal=move_id)
    if problems:
        _decide(move_id, "void", "No longer passes: " + " ".join(problems), None, db_file)
        return {"sent": False, "move": move(move_id, db_file)}
    offered = desk.propose(OUR_TEAM, sends, row["team_id"], receives, row["reason"], db_file)
    if not offered["proposed"]:
        messages = " ".join(v["message"] for v in offered["rules"]["violations"])
        _decide(move_id, "void", "No longer passes: " + messages, None, db_file)
        return {"sent": False, "move": move(move_id, db_file)}
    _decide(move_id, "approved", note, offered["proposal"]["id"], db_file)
    return {"sent": True, "move": move(move_id, db_file)}


def veto(move_id: int, note: str = "", db_file: Path | None = None) -> dict:
    db = connect(db_file)
    try:
        _move_row(db, move_id)
    finally:
        db.close()
    _decide(move_id, "vetoed", note, None, db_file)
    return {"move": move(move_id, db_file)}


# ---- What the owner sees ----------------------------------------------------------------

def _player(p: dict) -> dict:
    return {k: p[k] for k in ("id", "name", "position", "age", "overall", "salary", "years_left")}


def _summary(evaluation: dict) -> dict:
    """The parts of the Trade Desk's evaluation the owner reads before deciding."""
    ours = evaluation["teams"][OUR_TEAM]
    after = evaluation["rules"]["teams_after"][OUR_TEAM]
    return {"legal": evaluation["legal"], "cap_space_after": after["cap_space"], "roster_after": after["roster_size"],
            "salary_change": ours["salary_change"], "gives": [_player(p) for p in ours["gives"]],
            "gets": [_player(p) for p in ours["gets"]], "new_starters": ours["new_starters"],
            "benched": ours["benched"], "starters_lost": ours["starters_lost"],
            "unit_changes": ours["unit_changes"][:4]}


def _move(db: sqlite3.Connection, row: sqlite3.Row, db_file: Path | None) -> dict:
    out = dict(row)
    out["sends"], out["receives"] = json.loads(row["sends"]), json.loads(row["receives"])
    out["order"] = db.execute("SELECT text FROM orders WHERE id = ?", (row["order_id"],)).fetchone()["text"]
    if row["desk_proposal_id"]:
        offer = db.execute("SELECT status, response FROM trade_proposals WHERE id = ?",
                           (row["desk_proposal_id"],)).fetchone()
        out["offer"] = dict(offer)
    if row["status"] == "waiting":
        problems, evaluation = check_move(row["order_id"], row["team_id"], out["sends"], out["receives"], db_file,
                                          skip_proposal=row["id"])
        out["problems_now"] = problems
        if "teams" in evaluation:
            summary = _summary(evaluation)
            ids = summary["new_starters"] + summary["benched"] + summary["starters_lost"]
            names = {r["id"]: r["name"] for r in db.execute(
                f"SELECT id, name FROM players WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
            for key in ("new_starters", "benched", "starters_lost"):
                summary[key] = [{"id": p, "name": names.get(p, p)} for p in summary[key]]
            out["evaluation"] = summary
    else:
        league_players = {r["id"]: dict(r) for r in db.execute(
            "SELECT p.id, p.name, p.position, p.age, p.overall, c.salary, c.years_left FROM players p "
            "JOIN contracts c ON c.player_id = p.id WHERE p.id IN (SELECT value FROM json_each(?) "
            "UNION SELECT value FROM json_each(?))", (row["sends"], row["receives"]))}
        out["gives"] = [league_players[p] for p in out["sends"] if p in league_players]
        out["gets"] = [league_players[p] for p in out["receives"] if p in league_players]
    return out


def move(move_id: int, db_file: Path | None = None) -> dict:
    db = connect(db_file)
    try:
        row = db.execute("SELECT * FROM gm_proposals WHERE id = ?", (move_id,)).fetchone()
        if row is None:
            raise OrderError(f"There is no proposed move #{move_id}.")
        return _move(db, row, db_file)
    finally:
        db.close()


def moves(db_file: Path | None = None, order_id: int | None = None) -> list[dict]:
    """Every move the GM has proposed, the ones waiting for the owner first, then newest first."""
    db = connect(db_file)
    try:
        sql = "SELECT * FROM gm_proposals" + (" WHERE order_id = ?" if order_id else "") + \
              " ORDER BY status <> 'waiting', id DESC"
        return [_move(db, row, db_file) for row in db.execute(sql, (order_id,) if order_id else ()).fetchall()]
    finally:
        db.close()


def desk_view(db_file: Path | None = None) -> dict:
    """The orders standing and the moves the GM has proposed, for the week screen."""
    all_moves = moves(db_file)
    return {"orders": orders("active", db_file), "moves": all_moves,
            "waiting": sum(m["status"] == "waiting" for m in all_moves)}


# ---- The GM's search ----------------------------------------------------------------

def build_tools(order_id: int, db_file: Path | None = None) -> list:
    """The GM's own tools for one order, bound to it and to the loaded league."""

    def trade_targets(position: str, max_salary: float = 0) -> str:
        """Players at one position on the other five teams, best overall first, with their
        ratings, salary, contract years and whether they start for their team. Use it to find
        players to trade for.

        Args:
            position: league position code, e.g. "S" or "CB".
            max_salary: only players earning at most this, in $M per season. 0 for no limit.
        """
        league = load_league(db_file)
        position = position.strip().upper()
        starters = league["rules"]["starters_per_position"]
        if position not in starters:
            return json.dumps({"error": f"Unknown position {position!r}. Valid: {', '.join(starters)}."})
        found = []
        for team in league["teams"]:
            if team["id"] == OUR_TEAM:
                continue
            depth = sorted((p for p in league["players"] if p["team_id"] == team["id"] and p["position"] == position),
                           key=lambda p: -p["overall"])
            for rank, p in enumerate(depth):
                if max_salary and p["salary"] > max_salary:
                    continue
                found.append({"id": p["id"], "name": p["name"], "team_id": team["id"], "age": p["age"],
                              "overall": p["overall"], "ratings": p["ratings"], "salary": p["salary"],
                              "years_left": p["contract_years"], "starts_for_his_team": rank < starters[position]})
        found.sort(key=lambda p: -p["overall"])
        return json.dumps({"position": position, "max_salary": max_salary or None, "players": found[:TARGETS_SHOWN]})

    def propose_to_owner(team_id: str, we_send: list[str], we_get: list[str], reason: str) -> str:
        """Put one trade in front of the owner for approval. It is checked first: against the
        league rules, against every standing order (players the owner protects), and against
        this order's salary limits and positions. A refused move comes back with every problem,
        so you can fix it and try again. Nothing goes to the other team until the owner approves.

        Args:
            team_id: three-letter id of the team we trade with, e.g. "SUM".
            we_send: our player ids we give up, e.g. ["HAR-46"]. May be empty.
            we_get: their player ids we get, e.g. ["SUM-45"].
            reason: two or three sentences for the owner: why this move, with the numbers from evaluate_trade.
        """
        try:
            move_id = file_move(order_id, team_id, we_send, we_get, reason, db_file)
        except MoveRefused as refused:
            return json.dumps({"filed": False, "problems": refused.problems})
        return json.dumps({"filed": True, "move_id": move_id,
                           "moves_left_for_this_order": MAX_PROPOSALS - len(moves(db_file, order_id))})

    return [trade_targets, propose_to_owner]


SEARCH_INSTRUCTIONS = [
    "You are the general manager of the Harbor City Herons (team id HAR) in a six-team American football "
    "league. The owner gave you an order. Carry it out by finding trades and putting the best of them in "
    f"front of the owner with propose_to_owner (at most {MAX_PROPOSALS}). The owner approves or vetoes each one.",
    "Work like this: if the order names no position, call compare_to_league for HAR to find the weakest. Call "
    "get_roster for HAR at the position to see who starts. Call trade_targets for that position, with the "
    "order's salary limit, to find players who would start for us. For each promising one, decide what we "
    "send back (backups at the same position, or salary we can spare) and call evaluate_trade to check it: "
    "it must be legal, and it should improve the units the order is about.",
    "The salary cap is $255M and hard, and rosters must stay between 46 and 53 players. evaluate_trade tells "
    "you both teams' payroll, cap space and roster size after the trade: trust it rather than doing sums.",
    "Never send a player the owner protects. Never invent players: use only ids that your tools returned.",
    "Write each reason with the numbers evaluate_trade gave you (ratings, salaries, unit changes, cap space "
    "after). If propose_to_owner refuses a move, read its problems and fix the move or try another.",
    "Propose only moves you would recommend. If nothing fits the order, propose nothing and say why.",
    "When you're done, write the owner a short reply: what you proposed and why, or why nothing fits.",
    "How to answer the owner:\n" + skills.section("front-office-memo", "Answering the owner"),
    "The house style:\n" + skills.section("front-office-memo", "House style"),
]


# The slice of each server the GM's search uses: reading rosters, and evaluating a trade.
# Proposing on the Trade Desk is left out on purpose: only the owner's approval does that.
LEAGUE_OFFICE_TOOLS = ["list_teams", "get_roster", "compare_to_league"]
TRADE_DESK_TOOLS = ["evaluate_trade"]


def _server(module: str, include: list[str], db_file: Path | None) -> MCPTools:
    args = ["-m", module] + (["--db", str(Path(db_file).resolve())] if db_file else [])
    server = StdioServerParameters(command=sys.executable, args=args, cwd=str(PROJECT_ROOT))
    return MCPTools(server_params=server, transport="stdio", include_tools=include)


def league_office_tools(db_file: Path | None = None) -> MCPTools:
    return _server("servers.league_office", LEAGUE_OFFICE_TOOLS, db_file)


def trade_desk_tools(db_file: Path | None = None) -> MCPTools:
    return _server("servers.trade_desk", TRADE_DESK_TOOLS, db_file)


def build_searcher(league_office, trade_tools, order_id: int, db_file: Path | None = None,
                   debug: bool = False) -> Agent:
    from agents.analytics import specialist_model
    return Agent(name="General Manager", model=specialist_model(),
                 tools=[league_office, trade_tools, *build_tools(order_id, db_file)],
                 instructions=SEARCH_INSTRUCTIONS, tool_call_limit=SEARCH_TOOL_LIMIT, debug_mode=debug)


def search_prompt(order: dict, standing: list[dict], league: dict, week: int) -> str:
    cap = league["rules"]["salary_cap"]
    payroll = round(sum(p["salary"] for p in league["players"] if p["team_id"] == OUR_TEAM), 2)
    others = [f"#{o['id']}: \"{o['text']}\"" + (f" (protects {', '.join(o['terms']['protected'])})"
                                                 if o["terms"]["protected"] else "")
              for o in standing if o["id"] != order["id"]]
    return (f"It is week {week}; trades close after week {league['rules']['trade_deadline_week']}.\n"
            f"Our payroll is ${payroll:.2f}M, cap space ${cap - payroll:.2f}M.\n\n"
            f"The owner's order #{order['id']}: \"{order['text']}\"\n"
            f"How you read it (enforced when you propose): {json.dumps(order['terms'])}\n\n"
            + (f"Standing orders that still apply:\n" + "\n".join(others) if others else "No other standing orders."))


async def give_order(text: str, db_file: Path | None = None, reader: Agent | None = None,
                     searcher=None) -> dict:
    """Read the order, keep it, and have the GM propose moves for it. `searcher(order, standing,
    league, week)` stands in for the GM's search in tests; it returns (reply, run or None)."""
    text = text.strip()
    if not text:
        raise OrderError("Type an order for your GM.")
    started = time.perf_counter()
    league = load_league(db_file)
    terms, usage = await read_order(text, league, reader)
    order_id = save_order(text, ground_terms(terms, league), db_file)
    order = next(o for o in orders("all", db_file) if o["id"] == order_id)
    week = _current_week(db_file)
    deadline = league["rules"]["trade_deadline_week"]

    calls = []
    if not order["terms"]["wants_trades"]:
        reply = f"Understood: {order['terms']['summary']} That stands until you cancel it."
    elif week > deadline:
        reply = (f"Understood: {order['terms']['summary']} But trades closed after week {deadline}, the trade "
                 f"deadline, so there's nothing I can propose this season. The order still stands.")
    else:
        standing = orders("active", db_file)
        if searcher is None:
            reply, run = await _search(order, standing, league, week, db_file)
        else:
            reply, run = await searcher(order, standing, league, week)
        if run is not None:
            from agents.gm import tool_calls
            usage.append(_usage(run))
            calls = tool_calls(run)

    costs = [u["cost"] for u in usage if u["cost"] is not None]
    cost = round(sum(costs), 6) if costs else None
    _finish_order(order_id, reply, cost, db_file)
    return {"order": next(o for o in orders("all", db_file) if o["id"] == order_id), "reply": reply,
            "moves": moves(db_file, order_id), "tool_calls": calls,
            "seconds": round(time.perf_counter() - started, 1), "cost": cost}


async def _search(order: dict, standing: list[dict], league: dict, week: int, db_file: Path | None):
    async with league_office_tools(db_file) as league_office, trade_desk_tools(db_file) as trade_tools:
        run = await build_searcher(league_office, trade_tools, order["id"], db_file).arun(
            search_prompt(order, standing, league, week))
    content = run.content if isinstance(run.content, str) and run.content.strip() else None
    filed = len(moves(db_file, order["id"]))
    reply = content or (f"I've put {filed} move{'s' if filed != 1 else ''} in front of you." if filed
                        else "I couldn't find a move that fits the order.")
    return reply, run


def _current_week(db_file: Path | None) -> int:
    db = connect(db_file)
    try:
        return _week(db)
    finally:
        db.close()
