"""What a player is worth, and how badly a team needs their position.

Two separate numbers, combined into one pick score:
  - market_value: "what would this player cost on the open market" ($M/yr),
    from their overall rating and position premium. Shown on the draft board.
  - need_score: how urgently a team's roster wants this position right now,
    from the roster_rules.ROSTER_TEMPLATE gap. 0 once a position is full.

pick_score blends the two so the draft isn't pure best-player-available (a
team wouldn't draft a 9th wide receiver just because he grades out a point
higher than the backup long snapper they still need) but value still leads.
"""

from draft.roster_rules import POSITION_PREMIUM, ROSTER_TEMPLATE


def market_value(overall: int, position: str) -> float:
    base = max(0.5, (overall - 45) * 0.42)
    return round(base * POSITION_PREMIUM.get(position, 1.0), 1)


def need_score(position_counts: dict[str, int], position: str) -> float:
    """0.0 once the position is full; otherwise higher the bigger the gap,
    with a bonus if the team doesn't have a single player there yet."""
    target = ROSTER_TEMPLATE[position]
    have = position_counts.get(position, 0)
    if have >= target:
        return 0.0
    gap_fraction = (target - have) / target
    starter_bonus = 1.5 if have == 0 else 1.0
    return gap_fraction * starter_bonus


def pick_score(overall: int, position: str, position_counts: dict[str, int], need_weight: float = 0.6) -> float:
    """Value, tilted toward need. need_weight in [0, 1]: 0 = pure best-player-
    available, higher = more willing to take a worse player at a bigger need."""
    value = market_value(overall, position)
    need = need_score(position_counts, position)
    return value * (1.0 + need_weight * need)
