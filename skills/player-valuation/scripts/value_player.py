#!/usr/bin/env python3
"""What a player is worth in this league, from the league's own salaries.

    value_player.py --position S --overall 74 --salary 4.5 --age 27 --years 3 --key coverage=81

Prints JSON: the market value for his position and overall, the surplus against
his salary (per season and over the contract), a verdict, and what his age means.
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEAGUE = ROOT / "data" / "league.json"
DB_ENV = "FRONT_OFFICE_DB"  # the game sets it to the loaded save (agents/league_db.py)

FLOOR = 55          # at or below this overall, a veteran earns about the minimum
MIN_SALARY = 1.0    # $M; the league minimum
ROOKIE_AGE = 23     # 23 and under are still on rookie deals
BAND = 0.20         # within 20% (or $1M) of market is fair


def _quality(overall: float) -> float:
    return max(0.0, (overall - FLOOR) / 35) ** 2


def curves(players: list[dict]) -> dict[str, float]:
    """Per position, the $M a veteran earns above the minimum at quality 1 (overall 90),
    fitted by least squares through the origin: salary = MIN + k * quality."""
    sums: dict[str, list[float]] = {}
    for p in players:
        if p["age"] <= ROOKIE_AGE:
            continue
        q = _quality(p["overall"])
        xy, xx = sums.setdefault(p["position"], [0.0, 0.0])
        sums[p["position"]] = [xy + q * (p["salary"] - MIN_SALARY), xx + q * q]
    return {pos: xy / xx for pos, (xy, xx) in sums.items() if xx}


def market_value(position: str, overall: float, k: dict[str, float]) -> float:
    return round(MIN_SALARY + k[position] * _quality(overall), 2)


def value(position: str, overall: float, salary: float, age: int | None = None, years: int | None = None,
          players: list[dict] | None = None, key: float | None = None) -> dict:
    if players is None:
        players = json.loads(LEAGUE.read_text(encoding="utf-8"))["players"]
    k = curves(players)
    position = position.upper()
    if position not in k:
        return {"error": f"Unknown position {position!r}. Valid: {sorted(k)}"}
    market = market_value(position, overall, k)
    surplus = round(market - salary, 2)
    margin = max(BAND * market, 1.0)
    verdict = "bargain" if surplus >= margin else "overpaid" if -surplus >= margin else "fair"
    out = {"position": position, "overall": overall, "salary": salary, "market_value": market,
           "surplus_per_season": surplus, "verdict": verdict}
    if key is not None:
        # Salaries are priced on overall. Priced on the one rating the job needs instead,
        # what would he be worth? Above his salary: he's better at the job than he's paid for.
        job = market_value(position, key, k)
        out.update(key_rating=key, value_for_the_job=job, job_surplus_per_season=round(job - salary, 2))
    if years:
        out["contract_years"] = years
        out["surplus_over_contract"] = round(surplus * years, 2)
    if age is not None:
        out["age"] = age
        if age <= ROOKIE_AGE:
            out["age_note"] = "On a rookie deal: cheap for his rating, but only until the contract ends."
        elif age < 30:
            out["age_note"] = "In his prime."
        else:
            out["age_note"] = (f"Past 29: the league's history has players his age missing about "
                               f"{0.4 * (age - 29):.1f} more games a season. Injuries arrive with task 3.2.")
    return out


def parse_key(text: str | None) -> float | None:
    """--key as "coverage=88" or "88"."""
    if text is None:
        return None
    number = text.partition("=")[2] or text
    try:
        return float(number)
    except ValueError:
        raise ValueError(f"--key needs the rating's value, e.g. --key coverage=88, not {text!r}.") from None


def players_in_play() -> list[dict] | None:
    """The loaded game's players, when the game says which save is loaded, so a real-players
    league is priced on its own salaries. None means the generated league's seed."""
    path = os.environ.get(DB_ENV)
    if not path or not Path(path).exists():
        return None
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT p.position, p.age, p.overall, c.salary FROM players p "
                          "JOIN contracts c ON c.player_id = p.id").fetchall()
    db.close()
    return [{"position": pos, "age": age, "overall": overall, "salary": salary} for pos, age, overall, salary in rows]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--position", required=True, help="QB, RB, WR, TE, OL, DL, LB, CB, S, K or P")
    parser.add_argument("--overall", type=float, required=True, help="overall rating, 25-99")
    parser.add_argument("--salary", type=float, required=True, help="salary, $M per season")
    parser.add_argument("--age", type=int)
    parser.add_argument("--years", type=int, help="contract years left, this season included")
    parser.add_argument("--key", help="the one rating the job needs and its value, e.g. coverage=88 (or just 88)")
    args = parser.parse_args(argv)
    try:
        key = parse_key(args.key)
    except ValueError as problem:
        print(json.dumps({"error": str(problem)}, indent=2))
        return
    print(json.dumps(value(args.position, args.overall, args.salary, args.age, args.years,
                           players=players_in_play(), key=key), indent=2))


if __name__ == "__main__":
    main()
