"""Draft mechanics: random order, snake sequencing, the available-player pool,
and running the draft end to end.

I/O (printing the board, prompting the human) lives in draft_day.py; this
module only knows how to pick, score and record - `run()` calls back into
`on_user_turn` for the one team a human controls and handles every other
team itself.
"""

import random
from typing import Callable, Optional

from draft.agent import build_draft_agent, choose_pick
from draft.players import Player, build_player_pool
from draft.roster_rules import ROUNDS, TEAMS, rookie_salary
from draft.team import PHILOSOPHIES, Team
from draft.valuation import market_value, pick_score

SHORTLIST_SIZE = 12


def build_teams(user_team_id: Optional[str], rng: random.Random) -> list[Team]:
    teams = []
    philosophies = PHILOSOPHIES[:]
    rng.shuffle(philosophies)
    for index, (team_id, city, name) in enumerate(TEAMS):
        is_user = team_id == user_team_id
        philosophy = "" if is_user else philosophies[index % len(philosophies)]
        teams.append(Team(id=team_id, city=city, name=name, is_user=is_user, philosophy=philosophy))
    return teams


def random_draft_order(teams: list[Team], rng: random.Random) -> list[Team]:
    order = teams[:]
    rng.shuffle(order)
    return order


def snake_pick_order(draft_order: list[Team], rounds: int = ROUNDS):
    """Yield (round_number, pick_in_round, overall_pick, team) in snake order:
    round 1 forward through draft_order, round 2 reversed, round 3 forward, ..."""
    overall = 0
    for round_number in range(1, rounds + 1):
        teams_this_round = draft_order if round_number % 2 == 1 else list(reversed(draft_order))
        for pick_in_round, team in enumerate(teams_this_round, start=1):
            overall += 1
            yield round_number, pick_in_round, overall, team


class DraftEngine:
    def __init__(self, user_team_id: Optional[str] = None, seed: Optional[int] = None,
                 use_llm: bool = True, debug: bool = False):
        self.rng = random.Random(seed)
        self.teams = build_teams(user_team_id, self.rng)
        self.teams_by_id = {team.id: team for team in self.teams}
        self.draft_order = random_draft_order(self.teams, self.rng)
        self.available: list[Player] = build_player_pool()
        self.use_llm = use_llm
        self.agent = build_draft_agent(debug=debug) if use_llm else None
        self.log: list[dict] = []

    def eligible_for(self, team: Team, overall_pick: int) -> list[Player]:
        """Players whose position the team still needs and whose rookie
        salary at this pick slot the team can actually afford."""
        open_positions = set(team.open_positions())
        cap_room = team.cap_room()
        return [
            p for p in self.available
            if p.position in open_positions and rookie_salary(overall_pick, p.position) <= cap_room
        ]

    def ranked(self, team: Team, overall_pick: int) -> list[Player]:
        counts = team.position_counts()
        return sorted(
            self.eligible_for(team, overall_pick),
            key=lambda p: pick_score(p.overall, p.position, counts),
            reverse=True,
        )

    def shortlist(self, team: Team, overall_pick: int, size: int = SHORTLIST_SIZE) -> list[Player]:
        return self.ranked(team, overall_pick)[:size]

    def _finalize_player(self, player: Player, team: Team, overall_pick: int) -> None:
        if player not in self.available:
            raise ValueError(f"{player.name} is not available to draft.")
        player.team_id = team.id
        player.pick_number = overall_pick
        player.salary = rookie_salary(overall_pick, player.position)
        team.add(player)
        self.available.remove(player)
        self.log.append({
            "pick": overall_pick, "team_id": team.id, "player_id": player.id,
            "name": player.name, "position": player.position, "salary": player.salary,
        })

    def cpu_pick(self, team: Team, round_number: int, overall_pick: int) -> Player:
        shortlist = self.shortlist(team, overall_pick)
        if not shortlist:
            # Shouldn't happen with a properly sized pool, but never crash the draft.
            shortlist = self.eligible_for(team, overall_pick) or list(self.available)
        if self.use_llm and self.agent is not None and shortlist:
            board = [
                {
                    "id": p.id, "name": p.name, "position": p.position, "overall": p.overall,
                    "market_value": market_value(p.overall, p.position),
                    "rookie_salary": rookie_salary(overall_pick, p.position),
                }
                for p in shortlist
            ]
            chosen_id = choose_pick(
                self.agent, team.display_name, team.philosophy, overall_pick, round_number,
                team.cap_room(), team.needs(), board,
            )
            if chosen_id:
                return next(p for p in shortlist if p.id == chosen_id)
        return shortlist[0]

    def run(self, on_user_turn: Optional[Callable[["DraftEngine", Team, int, int], Player]] = None,
            on_pick: Optional[Callable[[Team, Player, int, int], None]] = None) -> None:
        """Run the whole draft. `on_user_turn(engine, team, round_number, overall_pick)`
        is called each time the human team is up and must return the Player it drafted.
        `on_pick(team, player, round_number, overall_pick)` fires after every pick
        (human or CPU), so a caller can print progress as the draft happens."""
        for round_number, _, overall_pick, team in snake_pick_order(self.draft_order):
            if team.is_full():
                continue
            if team.is_user and on_user_turn is not None:
                player = on_user_turn(self, team, round_number, overall_pick)
            else:
                player = self.cpu_pick(team, round_number, overall_pick)
            self._finalize_player(player, team, overall_pick)
            if on_pick is not None:
                on_pick(team, player, round_number, overall_pick)

    def to_dict(self) -> dict:
        return {
            "draft_order": [t.id for t in self.draft_order],
            "teams": [
                {
                    "id": t.id, "city": t.city, "name": t.name, "is_user": t.is_user,
                    "philosophy": t.philosophy, "payroll": t.payroll(), "cap_room": t.cap_room(),
                    "players": [p.to_dict() for p in t.roster],
                }
                for t in self.teams
            ],
            "draft_log": self.log,
        }
