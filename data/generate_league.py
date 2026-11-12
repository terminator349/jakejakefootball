"""Generate a fictional six-team American football league and write it to data/league.json.

Made-up data keeps early steps independent of any real stats API. The seed
makes every run produce the same league, so demos are reproducible.

Our team (HAR) is deliberately weak in pass coverage at cornerback and
safety, and sits just under the hard cap, so the Step 1 agent has a real
weakness to find and very little money to fix it with.
"""

import json
import random
from pathlib import Path

SEED = 42
OUR_TEAM = "HAR"

# Each position's skill ratings (25-99). A player's overall is the average of these.
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

# 48 players per team; the first STARTERS[pos] players at each position start.
ROSTER_COUNTS = {"QB": 2, "RB": 3, "WR": 6, "TE": 3, "OL": 9, "DL": 7, "LB": 6, "CB": 6, "S": 4, "K": 1, "P": 1}
STARTERS = {"QB": 1, "RB": 1, "WR": 3, "TE": 1, "OL": 5, "DL": 4, "LB": 3, "CB": 2, "S": 2, "K": 1, "P": 1}

# Simplified money and roster rules. Money is in millions of dollars.
RULES = {
    "salary_cap": 255.0,
    "cap_type": "hard",
    "roster_min": 46,
    "roster_max": 53,
    "season_games": 17,
    "trade_deadline_week": 9,
    "starters_per_position": STARTERS,
}

# What a star at each position earns before team payrolls are scaled.
TOP_SALARY = {"QB": 50, "DL": 30, "WR": 30, "CB": 22, "OL": 22, "LB": 18, "S": 16, "TE": 15, "RB": 12, "K": 5, "P": 3}
MIN_SALARY = 1.0
OUR_PAYROLL = 249.5  # $5.5M of cap space
OTHER_PAYROLL_RANGE = (225.0, 252.0)

TEAMS = [
    ("HAR", "Harbor City", "Herons"),
    ("MES", "Mesa Verde", "Coyotes"),
    ("IRN", "Iron Falls", "Foundry"),
    ("LAK", "Lakeshore", "Loons"),
    ("SUM", "Summit", "Sherpas"),
    ("DEL", "Delta Bay", "Gators"),
]

FIRST_NAMES = ["Marcus", "Dante", "Theo", "Jalen", "Andre", "Kofi", "Luca", "Mateo", "Isaiah",
               "Rafael", "Devin", "Omar", "Nikola", "Tariq", "Elias", "Bryce", "Caleb", "Jonah",
               "Kenji", "Malik", "Dmitri", "Xavier", "Quentin", "Ruben", "Tyrell", "Silas", "Darius",
               "Hunter", "Mason", "Cole", "Jamal", "Wade", "Reggie", "Tobias", "Grant", "Emeka"]
LAST_NAMES = ["Okafor", "Reyes", "Lindqvist", "Hargrove", "Mbeki", "Castillo", "Brennan",
              "Achebe", "Novak", "Whitfield", "Tanaka", "Dubois", "Kowalski", "Ferreira",
              "Abernathy", "Sato", "Mensah", "Vance", "Ibarra", "Holloway", "Pruitt", "Gaines",
              "McAllister", "Odom", "Thibodeaux", "Kessler", "Bolden", "Strickland", "Faulk", "Riggins"]


def clamp(value: float, low: int = 25, high: int = 99) -> int:
    return max(low, min(high, round(value)))


def unique_name(rng: random.Random, used: set) -> str:
    while True:
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name


def make_player(rng: random.Random, player_id: str, name: str, team_id: str, position: str, is_starter: bool) -> dict:
    base = rng.gauss(74 if is_starter else 63, 5)
    ratings = {key: clamp(base + rng.gauss(0, 5)) for key in POSITION_RATINGS[position]}

    if team_id == OUR_TEAM and position in ("CB", "S"):
        ratings["coverage"] = clamp(ratings["coverage"] - 22)

    overall = round(sum(ratings.values()) / len(ratings))
    age = rng.randint(22, 38 if position in ("K", "P") else 34)
    # Raw salary grows with the square of quality; scale_payroll turns it into dollars.
    raw_salary = TOP_SALARY[position] * max(0.0, (overall - 55) / 35) ** 2
    if age <= 23:
        raw_salary = min(raw_salary, 3.0)  # still on a rookie deal

    return {
        "id": player_id,
        "name": name,
        "team_id": team_id,
        "position": position,
        "age": age,
        "overall": overall,
        "raw_salary": raw_salary,
        "contract_years": rng.randint(1, 5),
        "games_missed_last_season": min(17, max(0, round(rng.expovariate(1 / 2) + max(0, age - 29) * 0.4))),
        "ratings": ratings,
    }


def scale_payroll(roster: list[dict], target: float) -> None:
    """Every player earns at least MIN_SALARY; the rest of the target is shared by raw salary."""
    total_raw = sum(p["raw_salary"] for p in roster)
    per_raw = (target - MIN_SALARY * len(roster)) / total_raw
    for player in roster:
        player["salary"] = round(MIN_SALARY + player.pop("raw_salary") * per_raw, 2)


def generate() -> dict:
    rng = random.Random(SEED)
    teams, players, used_names = [], [], set()

    for team_id, city, nickname in TEAMS:
        teams.append({"id": team_id, "city": city, "name": nickname})
        roster = []
        for position, count in ROSTER_COUNTS.items():
            for depth in range(count):
                player_id = f"{team_id}-{len(roster) + 1:02d}"
                name = unique_name(rng, used_names)
                roster.append(make_player(rng, player_id, name, team_id, position, depth < STARTERS[position]))
        target = OUR_PAYROLL if team_id == OUR_TEAM else round(rng.uniform(*OTHER_PAYROLL_RANGE), 1)
        scale_payroll(roster, target)
        players.extend(roster)

    return {"sport": "american_football", "our_team": OUR_TEAM, "rules": RULES, "teams": teams, "players": players}


if __name__ == "__main__":
    league = generate()
    out_path = Path(__file__).parent / "league.json"
    out_path.write_text(json.dumps(league, indent=2))
    print(f"Wrote {len(league['teams'])} teams and {len(league['players'])} players to {out_path}")
