#!/usr/bin/env python3
"""How much swapping one starter for another moves each unit the simulator uses.

    unit_impact.py --position S --current coverage=52,tackling=78,speed=81 \\
                   --candidate coverage=83,tackling=71,speed=80

Prints JSON: each unit that changes, by how many points (25-99 scale), and the
plays that unit takes part in. It builds two lineups with the simulator's own
build_lineup (agents/simulator.py), identical but for that one starter, so the
numbers are exactly the engine's.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.simulator import UNITS, build_lineup  # noqa: E402

RULES = json.loads((ROOT / "data" / "league.json").read_text(encoding="utf-8"))["rules"]
STARTERS = RULES["starters_per_position"]
# Each position's skill ratings; a player's overall is their average (data/generate_league.py).
POSITION_RATINGS = {
    "QB": ["accuracy", "arm_strength", "decision_making", "mobility"],
    "RB": ["rushing", "receiving", "pass_protection", "speed"],
    "WR": ["route_running", "hands", "speed"],
    "TE": ["receiving", "blocking", "speed"],
    "OL": ["pass_blocking", "run_blocking", "strength"],
    "DL": ["pass_rush", "run_defense", "strength"],
    "LB": ["run_defense", "coverage", "tackling", "pass_rush"],
    "CB": ["coverage", "speed", "tackling"],
    "S": ["coverage", "tackling", "speed"],
    "K": ["kick_power", "kick_accuracy"],
    "P": ["kick_power", "kick_accuracy"],
}
# What each unit does beyond the matchups in UNITS, as agents/simulator.py uses it.
OTHER_USES = {"pass_block": ["sacks on every pass (ours)"], "pass_rush": ["sacks on every pass (theirs)"],
              "decision": ["interceptions thrown"], "mobility": ["sacks avoided", "scrambles"],
              "kick_power": ["field goal range"], "kick_accuracy": ["field goals", "extra points"],
              "punt_power": ["punt distance"],
              "tackling": ["nothing yet: the simulator computes it but no play uses it"]}


def _player(position: str, ratings: dict[str, float], n: int) -> dict:
    return {"id": f"X-{position}-{n}", "position": position, "ratings": ratings,
            "overall": round(sum(ratings.values()) / len(ratings))}


def _team(position: str, swapped: dict[str, float]) -> list[dict]:
    """Every starter at 60 in every rating, but for one starter at `position`."""
    players = []
    for pos, count in STARTERS.items():
        for n in range(count):
            ratings = dict(swapped) if (pos, n) == (position, 0) else {r: 60 for r in POSITION_RATINGS[pos]}
            players.append(_player(pos, ratings, n))
    return players


def parse_ratings(position: str, text: str) -> dict[str, float]:
    ratings = {}
    for part in text.replace(" ", "").split(","):
        if part:
            name, _, number = part.partition("=")
            ratings[name] = float(number)
    needed = POSITION_RATINGS[position]
    missing, extra = [r for r in needed if r not in ratings], [r for r in ratings if r not in needed]
    if missing or extra:
        raise ValueError(f"A {position} has exactly these ratings: {', '.join(needed)}."
                         + (f" Missing: {', '.join(missing)}." if missing else "")
                         + (f" Not a {position} rating: {', '.join(extra)}." if extra else ""))
    return ratings


def impact(position: str, current: dict[str, float], candidate: dict[str, float]) -> dict:
    position = position.upper()
    before = build_lineup("X", _team(position, current), STARTERS).units
    after = build_lineup("X", _team(position, candidate), STARTERS).units
    plays = {}
    for play, (offense, defense) in UNITS.items():
        plays.setdefault(offense, []).append(f"{play} (our offense)")
        plays.setdefault(defense, []).append(f"{play} (their offense)")
    changes = [{"unit": unit, "change": round(after[unit] - before[unit], 2),
                "plays": plays.get(unit, []) + OTHER_USES.get(unit, [])}
               for unit in before if abs(after[unit] - before[unit]) >= 0.005]
    changes.sort(key=lambda c: -abs(c["change"]))
    return {"position": position, "starters_at_position": STARTERS[position], "changes": changes,
            "note": "Points on the 25-99 unit scale. The simulator softens big gaps between units: "
                    "about the first 10 points of a gap count almost in full, and no gap counts for more than 10."}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--position", required=True, choices=sorted(POSITION_RATINGS), type=str.upper)
    parser.add_argument("--current", required=True, help="the starter now, e.g. coverage=52,tackling=78,speed=81")
    parser.add_argument("--candidate", required=True, help="the player who would replace him, same ratings")
    args = parser.parse_args(argv)
    try:
        result = impact(args.position, parse_ratings(args.position, args.current),
                        parse_ratings(args.position, args.candidate))
    except ValueError as problem:
        result = {"error": str(problem)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
