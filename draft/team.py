"""A drafting team: its roster-so-far, cap usage, and what it still needs."""

from dataclasses import dataclass, field

from draft.players import Player
from draft.roster_rules import ROSTER_TEMPLATE, SALARY_CAP

# Flavor text injected into a CPU team's draft prompt, so the six AI teams
# don't all draft identically. Assigned randomly at draft start (engine.py).
PHILOSOPHIES = [
    "Best player available: take the highest-value player almost regardless of position, "
    "as long as the position isn't already full.",
    "Need-first: fill the biggest roster gaps even if it means passing on a slightly "
    "higher-graded player at a position you've already addressed.",
    "Trenches first: prioritize offensive and defensive line value a bit above the rest "
    "of the roster - you believe games are won up front.",
    "Premium positions first: prioritize quarterback, edge rusher, wide receiver and "
    "cornerback value - the positions that decide games.",
]


@dataclass
class Team:
    id: str
    city: str
    name: str
    is_user: bool = False
    philosophy: str = ""
    roster: list[Player] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.city} {self.name} ({self.id})"

    def position_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for player in self.roster:
            counts[player.position] = counts.get(player.position, 0) + 1
        return counts

    def open_positions(self) -> list[str]:
        """Positions not yet at their roster-template target."""
        counts = self.position_counts()
        return [pos for pos, target in ROSTER_TEMPLATE.items() if counts.get(pos, 0) < target]

    def needs(self) -> dict[str, int]:
        """Positions still short of target, mapped to how many are still needed."""
        counts = self.position_counts()
        return {pos: target - counts.get(pos, 0) for pos, target in ROSTER_TEMPLATE.items()
                if counts.get(pos, 0) < target}

    def payroll(self) -> float:
        return round(sum(p.salary or 0.0 for p in self.roster), 1)

    def cap_room(self) -> float:
        return round(SALARY_CAP - self.payroll(), 1)

    def is_full(self) -> bool:
        return len(self.roster) >= 53

    def add(self, player: Player) -> None:
        self.roster.append(player)
