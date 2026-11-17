#!/usr/bin/env python3
"""Test a signing or a trade against the league's cap, roster limits and deadline.

    cap_check.py sign  --payroll 249.48 --salary 6.0
    cap_check.py trade --payroll 249.48 --roster 48 --out 4.1 2.98 --in 9.87 --week 3

Prints JSON. Uses the League Office's own cap arithmetic (agents.tools.cap_math)
and the league's rules (data/league.json), so the answer matches what
check_cap_fit and check_trade would say.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.tools import cap_math  # noqa: E402

RULES = json.loads((ROOT / "data" / "league.json").read_text(encoding="utf-8"))["rules"]


def sign(payroll: float, salary: float, cap: float) -> dict:
    return {"move": "sign", **cap_math(payroll, salary, cap)}


def trade(payroll: float, roster: int, out: list[float], incoming: list[float], cap: float,
          week: int | None, deadline: int, low: int, high: int) -> dict:
    after = round(payroll - sum(out) + sum(incoming), 2)
    size = roster - len(out) + len(incoming)
    broken = []
    if week is not None and week > deadline:
        broken.append(f"Trades closed after week {deadline}, the trade deadline; it is week {week}.")
    if after > cap:
        broken.append(f"Payroll would be ${after:.2f}M, ${after - cap:.2f}M over the ${cap:.0f}M hard cap.")
    if size < low:
        broken.append(f"The roster would have {size} players; the minimum is {low}.")
    if size > high:
        broken.append(f"The roster would have {size} players; the maximum is {high}.")
    return {"move": "trade", "salary_cap": cap, "payroll_before": round(payroll, 2), "salary_out": round(sum(out), 2),
            "salary_in": round(sum(incoming), 2), "payroll_after": after, "cap_space_after": round(cap - after, 2),
            "roster_after": size, "legal": not broken, "broken_rules": broken,
            "salary_to_clear": round(max(0.0, after - cap), 2)}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cap", type=float, default=RULES["salary_cap"], help="hard cap in $M (default: the league's)")
    moves = parser.add_subparsers(dest="move", required=True)
    s = moves.add_parser("sign", help="add one contract")
    s.add_argument("--payroll", type=float, required=True, help="the team's payroll now, $M")
    s.add_argument("--salary", type=float, required=True, help="the new contract, $M per season")
    t = moves.add_parser("trade", help="send salaries out and take salaries in")
    t.add_argument("--payroll", type=float, required=True, help="the team's payroll now, $M")
    t.add_argument("--roster", type=int, required=True, help="the team's roster size now")
    t.add_argument("--out", type=float, nargs="*", default=[], help="each outgoing player's salary, $M")
    t.add_argument("--in", dest="incoming", type=float, nargs="*", default=[], help="each incoming player's salary, $M")
    t.add_argument("--week", type=int, help="the current week, to check the deadline")
    for move in (s, t):  # also accept --cap after the move, where a model tends to put it
        move.add_argument("--cap", type=float, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.move == "sign":
        result = sign(args.payroll, args.salary, args.cap)
    else:
        result = trade(args.payroll, args.roster, args.out, args.incoming, args.cap, args.week,
                       RULES["trade_deadline_week"], RULES["roster_min"], RULES["roster_max"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
