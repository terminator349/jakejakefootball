"""The highest grade the numbers allow a trade target (the scouting skill's grades).

    python grade.py --our-score 1.35 --games-out 0     -> {"grade": "A", ...}
    python grade.py --our-score 0.40                   -> {"grade": "B", ...}
    python grade.py --no-offer                         -> {"grade": "C", ...}

--our-score is the offer's score for us (the offer's our_score from scout_targets).
"""

import argparse
import json

A_GRADE = 1.0  # an offer worth at least this much to us


def grade(our_score: float | None, games_out: int = 0) -> str:
    if games_out or our_score is None:
        return "C"
    return "A" if our_score >= A_GRADE else "B"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--our-score", type=float, help="the offer's score for us")
    parser.add_argument("--no-offer", action="store_true", help="no one-for-one trade works")
    parser.add_argument("--games-out", type=int, default=0, help="games he'll still miss hurt")
    args = parser.parse_args(argv)
    score = None if args.no_offer else args.our_score
    result = grade(score, args.games_out)
    why = ("hurt" if args.games_out else "no one-for-one offer" if score is None
           else f"the offer is worth {score:+.2f} to us" + (", at least +1.00" if result == "A" else ", under +1.00"))
    print(json.dumps({"grade": result, "why": why}))


if __name__ == "__main__":
    main()
