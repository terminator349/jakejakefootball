"""League rules: the checks every move must pass (task 1.2).

Plain Python owns the rules, not a model. A trade is legal only if, after it:

- every team's roster is between the league's minimum and maximum size,
- no team's payroll is over the hard cap, and
- the season is no later than the trade-deadline week.

check_trade() reports every rule a trade would break without changing anything.
make_trade() runs the same checks and, only if they all pass, moves the players
and writes the trade to the move log, in one transaction. Both read the rules
and the current week from the league database (a save, or data/league.db), so
they always judge the league as it stands.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.league_db import connect


@dataclass(frozen=True)
class Trade:
    """Players swapped between two teams. Either side may send nobody."""

    team_a: str
    a_sends: list[str]
    team_b: str
    b_sends: list[str]

    def normalized(self) -> "Trade":
        return Trade(self.team_a.strip().upper(), [p.strip().upper() for p in self.a_sends],
                     self.team_b.strip().upper(), [p.strip().upper() for p in self.b_sends])


@dataclass(frozen=True)
class Violation:
    """One broken rule, worded so the owner can read it as is."""

    rule: str          # invalid_trade, trade_deadline, roster_min, roster_max or hard_cap
    message: str
    team_id: str | None = None


class IllegalMove(Exception):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        super().__init__("; ".join(v.message for v in violations))


def _rules(db: sqlite3.Connection) -> dict:
    return {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key, value FROM rules")}


def _check_players(db: sqlite3.Connection, trade: Trade) -> list[Violation]:
    """Is this a real trade between two teams, of players they actually have?"""
    team_ids = [row["id"] for row in db.execute("SELECT id FROM teams ORDER BY rowid")]
    problems = [f"Unknown team id {t!r}. Valid ids: {team_ids}." for t in (trade.team_a, trade.team_b)
                if t not in team_ids]
    if not problems and trade.team_a == trade.team_b:
        problems.append(f"A trade needs two different teams; both sides are {trade.team_a}.")
    if not trade.a_sends and not trade.b_sends:
        problems.append("The trade moves no players.")

    seen = set()
    for team, sends in ((trade.team_a, trade.a_sends), (trade.team_b, trade.b_sends)):
        for player_id in sends:
            if player_id in seen:
                problems.append(f"{player_id} is listed more than once.")
                continue
            seen.add(player_id)
            row = db.execute("SELECT name, team_id FROM players WHERE id = ?", (player_id,)).fetchone()
            if row is None:
                problems.append(f"There is no player with id {player_id!r}.")
            elif row["team_id"] != team:
                problems.append(f"{row['name']} ({player_id}) plays for {row['team_id']}, not {team}.")
    return [Violation("invalid_trade", message) for message in problems]


def _team_after(db: sqlite3.Connection, team: str, sends: list[str], receives: list[str]) -> dict:
    size, payroll = db.execute("SELECT COUNT(*), TOTAL(c.salary) FROM players p "
                               "JOIN contracts c ON c.player_id = p.id WHERE p.team_id = ?", (team,)).fetchone()

    def salaries(ids: list[str]) -> float:
        marks = ",".join("?" * len(ids))
        return db.execute(f"SELECT TOTAL(salary) FROM contracts WHERE player_id IN ({marks})", ids).fetchone()[0]

    return {"roster_size": size - len(sends) + len(receives),
            "payroll": round(payroll - salaries(sends) + salaries(receives), 2)}


def _check(db: sqlite3.Connection, trade: Trade) -> tuple[int, list[Violation], dict]:
    rules = _rules(db)
    week = db.execute("SELECT current_week FROM game").fetchone()[0]
    violations = []

    deadline = rules["trade_deadline_week"]
    if week > deadline:
        violations.append(Violation("trade_deadline",
                                    f"Trades closed after week {deadline}, the trade deadline; it is week {week}."))

    violations += _check_players(db, trade)
    if any(v.rule == "invalid_trade" for v in violations):
        return week, violations, {}  # sizes and payrolls mean nothing for a trade that cannot happen

    cap, low, high = rules["salary_cap"], rules["roster_min"], rules["roster_max"]
    after = {}
    for team, sends, receives in ((trade.team_a, trade.a_sends, trade.b_sends),
                                  (trade.team_b, trade.b_sends, trade.a_sends)):
        result = after[team] = _team_after(db, team, sends, receives)
        result["cap_space"] = round(cap - result["payroll"], 2)
        size = result["roster_size"]
        if size < low:
            violations.append(Violation("roster_min", f"{team} would have {size} players; "
                                                      f"the roster minimum is {low}.", team))
        if size > high:
            violations.append(Violation("roster_max", f"{team} would have {size} players; "
                                                      f"the roster maximum is {high}.", team))
        if result["cap_space"] < 0:
            violations.append(Violation("hard_cap", f"{team}'s payroll would be ${result['payroll']:.2f}M, "
                                                    f"${-result['cap_space']:.2f}M over the ${cap:.1f}M hard cap.",
                                        team))
    return week, violations, after


def _report(trade: Trade, week: int, violations: list[Violation], after: dict) -> dict:
    return {"legal": not violations, "week": week, "trade": asdict(trade),
            "violations": [asdict(v) for v in violations], "teams_after": after}


def check_trade(trade: Trade, db_file: Path | None = None) -> dict:
    """Every rule the trade would break this week, and each team's roster size, payroll
    and cap space if it went through. Changes nothing."""
    trade = trade.normalized()
    db = connect(db_file)
    try:
        return _report(trade, *_check(db, trade))
    finally:
        db.close()


def make_trade(trade: Trade, db_file: Path | None = None) -> dict:
    """Check the trade and, if it is legal, move the players and log the move. Raises
    IllegalMove (with every broken rule) and changes nothing if it is not. The report
    includes the move's id in the log."""
    trade = trade.normalized()
    db = connect(db_file)
    try:
        # Hold the write lock from the checks to the update, so no other move can
        # change the rosters in between and make a checked trade illegal.
        db.execute("BEGIN IMMEDIATE")
        week, violations, after = _check(db, trade)
        if violations:
            db.rollback()
            raise IllegalMove(violations)
        moved = ([(p, trade.team_a, trade.team_b) for p in trade.a_sends]
                 + [(p, trade.team_b, trade.team_a) for p in trade.b_sends])
        db.executemany("UPDATE players SET team_id = ? WHERE id = ?", [(to, p) for p, _, to in moved])
        move_id = db.execute("INSERT INTO moves (week, kind) VALUES (?, 'trade')", (week,)).lastrowid
        db.executemany("INSERT INTO move_players VALUES (?, ?, ?, ?)", [(move_id, *m) for m in moved])
        db.commit()
        return {**_report(trade, week, [], after), "move_id": move_id}
    finally:
        db.close()


def move_log(db_file: Path | None = None) -> list[dict]:
    """Every move made this season, oldest first, with the players each one moved."""
    db = connect(db_file)
    try:
        moves = {row["id"]: {**dict(row), "players": []}
                 for row in db.execute("SELECT * FROM moves ORDER BY id")}
        for row in db.execute("SELECT mp.*, p.name FROM move_players mp JOIN players p ON p.id = mp.player_id "
                              "ORDER BY mp.move_id, mp.rowid"):
            moves[row["move_id"]]["players"].append(
                {"player_id": row["player_id"], "name": row["name"],
                 "from_team_id": row["from_team_id"], "to_team_id": row["to_team_id"]})
        return list(moves.values())
    finally:
        db.close()
