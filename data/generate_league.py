"""Generate a fictional six-team league and write it to data/league.json.

Made-up data keeps early steps independent of any real stats API. The seed
makes every run produce the same league, so demos are reproducible.

Our team (HAR) is deliberately weak at perimeter defense, so the Step 1
agent has a real weakness to find.
"""

import json
import random
from pathlib import Path

SEED = 42
OUR_TEAM = "HAR"

# Simplified money rules, in millions of dollars.
RULES = {
    "salary_cap": 140.0,
    "luxury_tax_line": 170.0,
    "roster_min": 13,
    "roster_max": 15,
}

TEAMS = [
    ("HAR", "Harbor City", "Herons"),
    ("MES", "Mesa Verde", "Coyotes"),
    ("IRN", "Iron Falls", "Foundry"),
    ("LAK", "Lakeshore", "Loons"),
    ("SUM", "Summit", "Sherpas"),
    ("DEL", "Delta Bay", "Gators"),
]

# Two of each position plus three extra bodies = 13 players.
ROSTER_POSITIONS = ["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C", "C", "SG", "SF", "PF"]

FIRST_NAMES = ["Marcus", "Dante", "Theo", "Jalen", "Andre", "Kofi", "Luca", "Mateo", "Isaiah",
               "Rafael", "Devin", "Omar", "Nikola", "Tariq", "Elias", "Bryce", "Caleb", "Jonah",
               "Kenji", "Malik", "Dmitri", "Xavier", "Quentin", "Ruben"]
LAST_NAMES = ["Okafor", "Reyes", "Lindqvist", "Hargrove", "Mbeki", "Castillo", "Brennan",
              "Achebe", "Novak", "Whitfield", "Tanaka", "Dubois", "Kowalski", "Ferreira",
              "Abernathy", "Sato", "Mensah", "Vance", "Ibarra", "Holloway"]

# Position archetypes nudge ratings so guards shoot, bigs rebound, and so on.
POSITION_BIAS = {
    "PG": {"offense": 4, "three_pt": 6, "rebounding": -12, "perimeter_defense": 4, "interior_defense": -10},
    "SG": {"offense": 5, "three_pt": 8, "rebounding": -8, "perimeter_defense": 5, "interior_defense": -8},
    "SF": {"offense": 2, "three_pt": 2, "rebounding": -2, "perimeter_defense": 4, "interior_defense": -2},
    "PF": {"offense": 0, "three_pt": -4, "rebounding": 6, "perimeter_defense": -4, "interior_defense": 6},
    "C": {"offense": -2, "three_pt": -12, "rebounding": 12, "perimeter_defense": -10, "interior_defense": 10},
}

RATING_KEYS = ["offense", "three_pt", "rebounding", "perimeter_defense", "interior_defense", "athleticism"]


def clamp(value: float, low: int = 25, high: int = 99) -> int:
    return max(low, min(high, round(value)))


def make_player(rng: random.Random, player_id: str, team_id: str, position: str, is_starter: bool) -> dict:
    base = rng.gauss(72 if is_starter else 62, 6)
    bias = POSITION_BIAS[position]
    ratings = {key: clamp(base + bias.get(key, 0) + rng.gauss(0, 5)) for key in RATING_KEYS}

    if team_id == OUR_TEAM and position in ("PG", "SG", "SF"):
        ratings["perimeter_defense"] = clamp(ratings["perimeter_defense"] - 18)

    age = rng.randint(20, 35)
    overall = sum(ratings.values()) / len(ratings)
    # Better players earn more; very young players are still on cheap deals.
    salary = max(1.5, (overall - 50) * 1.1 + rng.gauss(0, 3))
    if age <= 22:
        salary = min(salary, 8.0)

    return {
        "id": player_id,
        "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "team_id": team_id,
        "position": position,
        "age": age,
        "salary": round(salary, 1),
        "contract_years": rng.randint(1, 5),
        "games_missed_last_season": max(0, round(rng.expovariate(1 / 8) + (age - 28) * 0.8)),
        "ratings": ratings,
    }


def generate() -> dict:
    rng = random.Random(SEED)
    teams, players = [], []

    for team_id, city, nickname in TEAMS:
        teams.append({"id": team_id, "city": city, "name": nickname})
        for index, position in enumerate(ROSTER_POSITIONS):
            # The first player listed at each position is that position's starter.
            is_starter = position not in ROSTER_POSITIONS[:index]
            players.append(make_player(rng, f"{team_id}-{index + 1:02d}", team_id, position, is_starter))

    return {"our_team": OUR_TEAM, "rules": RULES, "teams": teams, "players": players}


if __name__ == "__main__":
    league = generate()
    out_path = Path(__file__).parent / "league.json"
    out_path.write_text(json.dumps(league, indent=2))
    print(f"Wrote {len(league['teams'])} teams and {len(league['players'])} players to {out_path}")
