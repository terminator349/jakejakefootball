"""How a front office scores a trade from its own side (tasks 2.2 and G5).

One formula, used everywhere a trade is judged: by the rival GMs answering an
offer, by the rivals making offers of their own between weeks, by the Trade
Desk's evaluation, and by our GM through the negotiation skill. So our GM can
know, before it proposes, whether the other side will take it.

    score = market value gained                     (the player-valuation formula, $M per season)
            - SALARY_WEIGHT x salary taken on       ($M per season; money matters, but less than talent)
            + UNIT_VALUE x points the units move    (the simulator's units, 25-99; tackling isn't used by any play)

A team accepts a trade that scores at least its margin. The margin is how
much a team wants to win a trade; difficulty (task 4.5) will set it, and
"normal" is the default until then. Plain Python, no model.
"""

SALARY_WEIGHT = 0.5
UNIT_VALUE = 0.3          # $M per point of unit strength
IGNORED_UNITS = {"tackling"}  # computed by the simulator, used by no play

MARGINS = {"easy": -0.5, "normal": 0.25, "hard": 1.0}
DIFFICULTY = "normal"
# A rival making an offer of its own wants a little more than one answering ours.
OFFER_PREMIUM = 0.5
# Below this, an offer isn't worth a counter: the gap is too big to close with one player.
REJECT_BELOW = -6.0


def margin(difficulty: str = DIFFICULTY) -> float:
    return MARGINS[difficulty]


def unit_points(unit_changes: list[dict]) -> float:
    return round(sum(u["change"] for u in unit_changes if u["unit"] not in IGNORED_UNITS), 2)


def score(market_value_change: float, salary_change: float, unit_change_points: float) -> float:
    return round(market_value_change - SALARY_WEIGHT * salary_change + UNIT_VALUE * unit_change_points, 2)


def appraise(side: dict, difficulty: str = DIFFICULTY) -> dict:
    """One team's side of a trade (agents/trade_desk._side) as that team scores it."""
    points = unit_points(side["unit_changes"])
    value = score(side["market_value_change"], side["salary_change"], points)
    needed = margin(difficulty)
    verdict = "accept" if value >= needed else "reject" if value < REJECT_BELOW else "counter"
    return {"score": value, "margin": needed, "verdict": verdict,
            "parts": {"market_value_change": side["market_value_change"], "salary_change": side["salary_change"],
                      "unit_points": points}}
