"""Generate a fictional six-team football league and write it to data/league.json.

Made-up data keeps early steps independent of any real stats API. The seed
makes every run produce the same league, so demos are reproducible.

Our team (HAR) is deliberately weak at coverage in the secondary, so the
Step 1 agent has a real weakness to find.

Football has a hard salary cap (unlike basketball's cap + luxury tax): no
team may be generated over the cap, so "legal under the cap" holds from the
very first run, not just after a trade-legality check is added later.
"""

import json
import random
from pathlib import Path

SEED = 42
OUR_TEAM = "HAR"

# Simplified money rules, in millions of dollars. NFL-style hard cap: there
# is no luxury-tax overage allowed, only a cap line nobody may cross.
RULES = {
    "salary_cap": 220.0,
    "roster_min": 21,
    "roster_max": 24,
}

TEAMS = [
    ("HAR", "Harbor City", "Herons"),
    ("MES", "Mesa Verde", "Coyotes"),
    ("IRN", "Iron Falls", "Foundry"),
    ("LAK", "Lakeshore", "Loons"),
    ("SUM", "Summit", "Sherpas"),
    ("DEL", "Delta Bay", "Gators"),
]

# One QB, a handful of skill players, a five-man line each way, a K.
# 23 players: inside the roster_min/roster_max window above.
ROSTER_POSITIONS = [
    "QB",
    "RB", "RB",
    "WR", "WR", "WR",
    "TE",
    "OT", "OT", "OG", "OG", "C",
    "EDGE", "EDGE", "DT", "DT",
    "LB", "LB",
    "CB", "CB",
    "S", "S",
    "K",
]

FIRST_NAMES = ["Marcus", "Dante", "Theo", "Jalen", "Andre", "Kofi", "Luca", "Mateo", "Isaiah",
               "Rafael", "Devin", "Omar", "Nikola", "Tariq", "Elias", "Bryce", "Caleb", "Jonah",
               "Kenji", "Malik", "Dmitri", "Xavier", "Quentin", "Ruben"]
LAST_NAMES = ["Okafor", "Reyes", "Lindqvist", "Hargrove", "Mbeki", "Castillo", "Brennan",
              "Achebe", "Novak", "Whitfield", "Tanaka", "Dubois", "Kowalski", "Ferreira",
              "Abernathy", "Sato", "Mensah", "Vance", "Ibarra", "Holloway"]

RATING_KEYS = ["passing", "rushing", "receiving", "blocking", "pass_rush",
               "run_defense", "coverage", "kicking", "athleticism"]

# Position archetypes nudge ratings so a QB passes, a CB covers, and so on.
# Skills that are irrelevant to a position get a negative bias, the same way
# a basketball center was biased away from three-point shooting.
POSITION_BIAS = {
    "QB":   {"passing": 25, "rushing": 2,   "receiving": -15, "blocking": -20, "pass_rush": -20, "run_defense": -20, "coverage": -20, "kicking": -15, "athleticism": 3},
    "RB":   {"passing": -20, "rushing": 20, "receiving": 6,   "blocking": -5,  "pass_rush": -20, "run_defense": -18, "coverage": -18, "kicking": -15, "athleticism": 8},
    "WR":   {"passing": -20, "rushing": -5, "receiving": 20,  "blocking": -15, "pass_rush": -20, "run_defense": -20, "coverage": -18, "kicking": -15, "athleticism": 10},
    "TE":   {"passing": -20, "rushing": -8, "receiving": 10,  "blocking": 8,   "pass_rush": -15, "run_defense": -10, "coverage": -15, "kicking": -15, "athleticism": 2},
    "OT":   {"passing": -20, "rushing": -15, "receiving": -18, "blocking": 18, "pass_rush": -18, "run_defense": -5,  "coverage": -20, "kicking": -18, "athleticism": -5},
    "OG":   {"passing": -20, "rushing": -15, "receiving": -18, "blocking": 16, "pass_rush": -18, "run_defense": -5,  "coverage": -20, "kicking": -18, "athleticism": -6},
    "C":    {"passing": -18, "rushing": -15, "receiving": -18, "blocking": 14, "pass_rush": -18, "run_defense": -5,  "coverage": -20, "kicking": -18, "athleticism": -6},
    "EDGE": {"passing": -20, "rushing": -18, "receiving": -18, "blocking": -10, "pass_rush": 18, "run_defense": 8,  "coverage": -15, "kicking": -18, "athleticism": 6},
    "DT":   {"passing": -20, "rushing": -18, "receiving": -18, "blocking": -8, "pass_rush": 10,  "run_defense": 16, "coverage": -18, "kicking": -18, "athleticism": 2},
    "LB":   {"passing": -18, "rushing": -12, "receiving": -10, "blocking": -12, "pass_rush": 6,  "run_defense": 14, "coverage": 4,   "kicking": -18, "athleticism": 6},
    "CB":   {"passing": -18, "rushing": -14, "receiving": -5,  "blocking": -15, "pass_rush": -10, "run_defense": -8, "coverage": 18, "kicking": -18, "athleticism": 10},
    "S":    {"passing": -18, "rushing": -14, "receiving": -6,  "blocking": -14, "pass_rush": -6, "run_defense": 6,   "coverage": 12, "kicking": -18, "athleticism": 8},
    "K":    {"passing": -20, "rushing": -20, "receiving": -20, "blocking": -20, "pass_rush": -20, "run_defense": -20, "coverage": -20, "kicking": 35, "athleticism": -10},
}

# Positions whose weakest-player-on-the-team matters most for the cap number
# below, kept out of this generator but documented here for later agents.
SECONDARY_POSITIONS = ("CB", "S")


def clamp(value: float, low: int = 25, high: int = 99) -> int:
    return max(low, min(high, round(value)))


def make_player(rng: random.Random, player_id: str, team_id: str, position: str, is_starter: bool) -> dict:
    base = rng.gauss(72 if is_starter else 62, 6)
    bias = POSITION_BIAS[position]
    ratings = {key: clamp(base + bias.get(key, 0) + rng.gauss(0, 5)) for key in RATING_KEYS}

    if team_id == OUR_TEAM and position in SECONDARY_POSITIONS:
        ratings["coverage"] = clamp(ratings["coverage"] - 18)

    age = rng.randint(21, 35)
    overall = sum(ratings.values()) / len(ratings)
    # Better players earn more; very young players are still on rookie deals.
    salary = max(0.9, (overall - 50) * 0.9 + rng.gauss(0, 3))
    if age <= 23:
        salary = min(salary, 5.0)

    return {
        "id": player_id,
        "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        "team_id": team_id,
        "position": position,
        "age": age,
        "salary": round(salary, 1),
        "contract_years": rng.randint(1, 5),
        "games_missed_last_season": max(0, round(rng.expovariate(1 / 3) + (age - 29) * 0.5)),
        "ratings": ratings,
    }


def enforce_hard_cap(players: list[dict], cap: float) -> None:
    """Scale a team's salaries down in place if they generated over the cap.

    The league must be legal under the cap from the moment it's generated,
    not just after a future Contracts agent checks it.
    """
    total = sum(p["salary"] for p in players)
    target = cap * 0.95  # leave real teams a little room, like real front offices do
    if total > target:
        factor = target / total
        for player in players:
            player["salary"] = round(player["salary"] * factor, 1)


def generate() -> dict:
    rng = random.Random(SEED)
    teams, players = [], []

    for team_id, city, nickname in TEAMS:
        teams.append({"id": team_id, "city": city, "name": nickname})
        team_players = []
        for index, position in enumerate(ROSTER_POSITIONS):
            # The first player listed at each position is that position's starter.
            is_starter = position not in ROSTER_POSITIONS[:index]
            team_players.append(make_player(rng, f"{team_id}-{index + 1:02d}", team_id, position, is_starter))
        enforce_hard_cap(team_players, RULES["salary_cap"])
        players.extend(team_players)

    return {"our_team": OUR_TEAM, "rules": RULES, "teams": teams, "players": players}


if __name__ == "__main__":
    league = generate()
    out_path = Path(__file__).parent / "league.json"
    out_path.write_text(json.dumps(league, indent=2))
    print(f"Wrote {len(league['teams'])} teams and {len(league['players'])} players to {out_path}")
