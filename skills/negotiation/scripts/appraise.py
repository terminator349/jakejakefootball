#!/usr/bin/env python3
"""How a team scores a trade from its own side, with the league's own formula.

    appraise.py --market-value-change 4.08 --salary-change 3.46 --unit-points 9.63
    appraise.py --market-value-change -4.08 --salary-change -3.46 --unit-points 0 --difficulty hard

Prints JSON: the score, the margin a team needs to accept, and the verdict
(accept, counter or reject). It uses agents/negotiation.py, the same code the
rival GMs and the Trade Desk use, so its numbers are theirs.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents import negotiation  # noqa: E402


def appraise(market_value_change: float, salary_change: float, unit_points: float,
             difficulty: str = negotiation.DIFFICULTY) -> dict:
    side = {"market_value_change": market_value_change, "salary_change": salary_change,
            "unit_changes": [{"unit": "units", "change": unit_points}]}
    return negotiation.appraise(side, difficulty)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market-value-change", type=float, required=True,
                        help="market value of the players the team gets minus those it gives, $M per season")
    parser.add_argument("--salary-change", type=float, required=True,
                        help="the team's payroll change, $M per season (negative if it sheds salary)")
    parser.add_argument("--unit-points", type=float, default=0.0,
                        help="the team's unit changes added up, leaving out tackling")
    parser.add_argument("--difficulty", choices=sorted(negotiation.MARGINS), default=negotiation.DIFFICULTY)
    args = parser.parse_args(argv)
    print(json.dumps(appraise(args.market_value_change, args.salary_change, args.unit_points, args.difficulty),
                     indent=2))


if __name__ == "__main__":
    main()
