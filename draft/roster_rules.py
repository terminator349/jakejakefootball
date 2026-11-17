"""Roster shape, salary cap and rookie-contract rules for the draft.

A real 53-man NFL roster isn't 53 of whatever's best - it's a shape. These
constants are what turn "draft the best player" into "draft the best player
you're still allowed to roster," which is what makes "positions of need"
mean something.
"""

TEAMS = [
    ("HAR", "Harbor City", "Herons"),
    ("MES", "Mesa Verde", "Coyotes"),
    ("IRN", "Iron Falls", "Foundry"),
    ("LAK", "Lakeshore", "Loons"),
    ("SUM", "Summit", "Sherpas"),
    ("DEL", "Delta Bay", "Gators"),
]

ROUNDS = 53
PICKS_PER_ROUND = len(TEAMS)

# Target count per position for a full 53-man roster. Sums to exactly 53, and
# a position is closed to a team the moment it hits its target - that's the
# whole mechanism behind "we already have enough linemen."
ROSTER_TEMPLATE = {
    "QB": 3, "RB": 4, "WR": 7, "TE": 3,
    "OT": 4, "OG": 3, "C": 2,
    "EDGE": 4, "DT": 4, "LB": 6, "CB": 6, "S": 4,
    "K": 1, "P": 1, "LS": 1,
}
assert sum(ROSTER_TEMPLATE.values()) == 53

SALARY_CAP = 220.0  # $M, hard cap - same rule as the Step 0/1 league, no overage allowed.

# How much a position's market value and rookie salary get scaled relative to
# a league-average player at the same overall rating. Rough real-world premium
# positions (QB, the offensive/defensive line edges that protect or hunt the
# quarterback, outside corner) cost more; specialists cost far less.
POSITION_PREMIUM = {
    "QB": 1.35, "EDGE": 1.15, "WR": 1.10, "OT": 1.10, "CB": 1.05,
    "DT": 1.00, "S": 1.00, "LB": 0.95, "TE": 0.95, "RB": 0.90, "OG": 0.90, "C": 0.85,
    "K": 0.40, "P": 0.35, "LS": 0.30,
}


def rookie_salary(overall_pick: int, position: str) -> float:
    """A rookie-wage-scale salary ($M/yr) for the pick slot, position-adjusted.

    Decays from the top of the draft to a league-minimum floor, the same shape
    real rookie scales use, so cap room stays plentiful at a 53-round, 6-team
    draft without needing a trade-picks or restructure mechanic.
    """
    base = max(0.9, 11.0 * (0.985 ** (overall_pick - 1)))
    salary = base * POSITION_PREMIUM.get(position, 1.0)
    return round(min(salary, 14.0), 1)
