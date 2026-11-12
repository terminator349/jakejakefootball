"""The season simulator (task 3.1): plays a game one snap at a time.

Plain Python, no model calls. A Game holds the state of play (quarter, clock,
score, possession, down, distance, yard line, timeouts) and runs one snap per
step(). Each snap the offense picks a play and the defense a call; the ratings
of the starters on the field, the matchup between the two calls and a seeded
random number generator decide the result. Every snap goes into a play log,
and player stats add up as the game goes.

Teams the owner isn't coaching call their plays with plain-Python tendencies
(call_offense, call_defense). Those tendencies lean toward plays where the
offense's starters beat the defense's, so a weak unit gets attacked: a team
with poor safeties sees more deep passes.

Two random streams keep games repeatable: one for the AI's calls and one for
what happens on the field. The same seed gives the same game, and so do the
same seed and the same calls from a person (task G8).

Yard lines count from the offense's own goal line: 0 is its own end zone, 100
the opponent's.
"""

import math
import random
from dataclasses import dataclass, field

QUARTER_SECONDS = 15 * 60
OVERTIME_SECONDS = 10 * 60
TIMEOUTS_PER_HALF = 3
HOME_EDGE = 0.6  # rating points added to the home side's units

RUNS = ("run_inside", "run_outside")
PASSES = ("pass_short", "pass_deep", "play_action", "screen")
OFFENSE_PLAYS = RUNS + PASSES
FOURTH_DOWN = ("punt", "field_goal")
DEFENSE_CALLS = ("base", "blitz", "cover_2", "deep_zone", "run_stuff")

# How each defensive call shifts each play, in rating points (positive helps the offense).
MATCHUP = {
    "run_inside":  {"base": 0, "blitz": 1, "cover_2": 3, "deep_zone": 5, "run_stuff": -7},
    "run_outside": {"base": 0, "blitz": 3, "cover_2": -1, "deep_zone": 4, "run_stuff": -5},
    "pass_short":  {"base": 0, "blitz": 2, "cover_2": -4, "deep_zone": 3, "run_stuff": 5},
    "pass_deep":   {"base": 0, "blitz": 4, "cover_2": -3, "deep_zone": -8, "run_stuff": 6},
    "play_action": {"base": 1, "blitz": -3, "cover_2": 0, "deep_zone": -4, "run_stuff": 8},
    "screen":      {"base": -1, "blitz": 7, "cover_2": 0, "deep_zone": 3, "run_stuff": -2},
}

# Which offensive unit and which defensive unit meet on each play.
UNITS = {
    "run_inside": ("inside_run", "run_defense"),
    "run_outside": ("outside_run", "run_defense"),
    "pass_short": ("short_pass", "short_coverage"),
    "pass_deep": ("deep_pass", "deep_coverage"),
    "play_action": ("deep_pass", "deep_coverage"),
    "screen": ("screen", "screen_defense"),
}


# ---- Teams ---------------------------------------------------------------

def soften(gap: float, limit: float = 10.0) -> float:
    """Diminishing returns on a mismatch between units: small gaps count almost in
    full, a 17-point gap counts as about 9, and no gap counts for more than 10."""
    return limit * math.tanh(gap / limit)


def _mean(players: list[dict], rating: str) -> float:
    values = [p["overall"] if rating == "overall" else p["ratings"][rating] for p in players]
    return sum(values) / len(values) if values else 50.0


@dataclass
class Lineup:
    """A team's starters and backups by position, best first, and its unit strengths."""

    team_id: str
    depth: dict[str, list[dict]]
    units: dict[str, float] = field(default_factory=dict)

    def starters(self, position: str, count: int) -> list[dict]:
        return self.depth.get(position, [])[:count]


def build_lineup(team_id: str, players: list[dict], starters_per_position: dict[str, int]) -> Lineup:
    """Depth charts by overall rating (as get_roster lists them) and unit strengths on a
    25-99 scale, from the starters only."""
    depth = {pos: sorted((p for p in players if p["position"] == pos), key=lambda p: -p["overall"])
             for pos in starters_per_position}
    s = {pos: depth[pos][:n] for pos, n in starters_per_position.items()}
    qb, rb, wr, te, ol = s["QB"], s["RB"], s["WR"], s["TE"], s["OL"]
    dl, lb, cb, saf = s["DL"], s["LB"], s["CB"], s["S"]
    receivers = 0.6 * _mean(wr, "route_running") + 0.4 * _mean(wr, "hands")
    units = {
        "inside_run": 0.40 * _mean(rb, "rushing") + 0.10 * _mean(rb, "speed")
                      + 0.35 * _mean(ol, "run_blocking") + 0.10 * _mean(ol, "strength") + 0.05 * _mean(te, "blocking"),
        "outside_run": 0.30 * _mean(rb, "rushing") + 0.25 * _mean(rb, "speed")
                       + 0.30 * _mean(ol, "run_blocking") + 0.15 * _mean(te, "blocking"),
        "short_pass": 0.35 * _mean(qb, "accuracy") + 0.15 * _mean(qb, "decision_making")
                      + 0.35 * receivers + 0.15 * _mean(te, "receiving"),
        "deep_pass": 0.30 * _mean(qb, "arm_strength") + 0.20 * _mean(qb, "accuracy")
                     + 0.35 * _mean(wr, "speed") + 0.15 * _mean(wr, "route_running"),
        "screen": 0.40 * _mean(rb, "receiving") + 0.30 * _mean(rb, "speed") + 0.30 * _mean(ol, "pass_blocking"),
        "pass_block": 0.75 * _mean(ol, "pass_blocking") + 0.15 * _mean(ol, "strength")
                      + 0.10 * _mean(rb, "pass_protection"),
        "run_defense": 0.40 * _mean(dl, "run_defense") + 0.15 * _mean(dl, "strength")
                       + 0.25 * _mean(lb, "run_defense") + 0.20 * _mean(lb, "tackling"),
        "pass_rush": 0.70 * _mean(dl, "pass_rush") + 0.30 * _mean(lb, "pass_rush"),
        "short_coverage": 0.45 * _mean(cb, "coverage") + 0.30 * _mean(lb, "coverage") + 0.25 * _mean(saf, "coverage"),
        "deep_coverage": 0.40 * _mean(cb, "coverage") + 0.10 * _mean(cb, "speed")
                         + 0.40 * _mean(saf, "coverage") + 0.10 * _mean(saf, "speed"),
        "screen_defense": 0.50 * _mean(lb, "tackling") + 0.25 * _mean(lb, "coverage") + 0.25 * _mean(saf, "tackling"),
        "tackling": (_mean(lb, "tackling") + _mean(cb, "tackling") + _mean(saf, "tackling")) / 3,
        "decision": _mean(qb, "decision_making"),
        "mobility": _mean(qb, "mobility"),
        "kick_power": _mean(s["K"], "kick_power"),
        "kick_accuracy": _mean(s["K"], "kick_accuracy"),
        "punt_power": _mean(s["P"], "kick_power"),
    }
    return Lineup(team_id, depth, units)


# ---- Game state ------------------------------------------------------------

@dataclass
class Situation:
    """What a play caller sees before the snap."""

    quarter: int
    clock: int                 # seconds left in the quarter (or overtime)
    offense: str
    defense: str
    down: int
    distance: int
    yardline: int              # from the offense's own goal line
    score: dict[str, int]
    timeouts: dict[str, int]

    @property
    def lead(self) -> int:
        """The offense's lead (negative when behind)."""
        return self.score[self.offense] - self.score[self.defense]

    @property
    def late(self) -> bool:
        return self.quarter >= 4 and self.clock <= 5 * 60


def field_goal_distance(yardline: int) -> int:
    return 100 - yardline + 17  # the snap is 7 yards behind the line, plus the end zone


def call_offense(sit: Situation, offense: Lineup, defense: Lineup, rng: random.Random) -> str:
    """The AI's play call for the offense, from the situation and the matchups."""
    lead, late = sit.lead, sit.late
    if sit.quarter >= 4 and lead > 0 and sit.clock <= 40 * (4 - sit.down) + 5:
        return "kneel"
    if sit.down == 4:
        fg_range = field_goal_distance(sit.yardline) <= 45 + (offense.units["kick_power"] - 60) * 0.5
        if sit.quarter >= 4 and lead < 0 and sit.clock <= 300:
            if fg_range and -3 <= lead and sit.clock <= 30:
                return "field_goal"
            return rng.choice(PASSES[:3]) if sit.distance > 3 else "run_inside"
        if sit.distance <= 1 and 35 <= sit.yardline and rng.random() < 0.45:
            return "run_inside"
        if fg_range:
            return "field_goal"
        if sit.yardline >= 60 and sit.distance <= 3 and rng.random() < 0.5:
            return "pass_short" if sit.distance > 1 else "run_inside"
        return "punt"

    weights = {"run_inside": 0.36, "run_outside": 0.20, "pass_short": 0.24,
               "pass_deep": 0.07, "play_action": 0.08, "screen": 0.06}
    if sit.distance <= 2:
        for p in RUNS:
            weights[p] *= 2.0
        weights["pass_deep"] *= 0.5
    elif sit.distance >= 8:
        for p in PASSES:
            weights[p] *= 1.4
        for p in RUNS:
            weights[p] *= 0.25 if sit.down >= 3 else 0.7
    if sit.down == 1 and sit.distance >= 10:
        weights["play_action"] *= 1.5
    if late and lead < 0:
        for p in PASSES:
            weights[p] *= 2.0
        for p in RUNS:
            weights[p] *= 0.4
    elif late and lead > 0:
        for p in RUNS:
            weights[p] *= 1.8
    if sit.yardline >= 90:
        weights["pass_deep"] = 0.0
        weights["play_action"] *= 1.3
        for p in RUNS:
            weights[p] *= 1.4
    # Lean toward what works against this defense: a weak unit gets attacked.
    for play, (unit, against) in UNITS.items():
        weights[play] *= math.exp(0.03 * soften(offense.units[unit] - defense.units[against]))
    plays = list(weights)
    return rng.choices(plays, [weights[p] for p in plays])[0]


def call_defense(sit: Situation, defense: Lineup, offense: Lineup, rng: random.Random) -> str:
    """The AI's defensive call."""
    if sit.distance <= 2:
        weights = {"base": 0.30, "blitz": 0.15, "cover_2": 0.10, "deep_zone": 0.0, "run_stuff": 0.45}
    elif sit.down >= 3 and sit.distance >= 7:
        weights = {"base": 0.15, "blitz": 0.25, "cover_2": 0.30, "deep_zone": 0.30, "run_stuff": 0.0}
    else:
        weights = {"base": 0.45, "blitz": 0.12, "cover_2": 0.20, "deep_zone": 0.10, "run_stuff": 0.13}
    if sit.late and sit.lead < 0:  # the defense is ahead late: keep everything in front
        weights["deep_zone"] = weights["deep_zone"] * 2 + 0.2
        weights["blitz"] *= 0.5
    calls = list(weights)
    return rng.choices(calls, [weights[c] for c in calls])[0]


# ---- The game --------------------------------------------------------------

class Game:
    """One game between two lineups. Call step() until over, or play() to the end."""

    def __init__(self, home: Lineup, away: Lineup, seed: str | int):
        self.home, self.away = home, away
        self.teams = {home.team_id: home, away.team_id: away}
        self.field_rng = random.Random(f"field-{seed}")
        self.call_rng = random.Random(f"calls-{seed}")
        self.score = {home.team_id: 0, away.team_id: 0}
        self.timeouts = {home.team_id: TIMEOUTS_PER_HALF, away.team_id: TIMEOUTS_PER_HALF}
        self.quarter, self.clock = 1, QUARTER_SECONDS
        self.plays: list[dict] = []
        self.stats: dict[str, dict[str, int]] = {}
        self.player_team = {p["id"]: team.team_id for team in (home, away)
                            for group in team.depth.values() for p in group}
        self.drive = 0
        self.over = False
        # Coin toss: the winner receives; the other team receives after halftime.
        receiver = home.team_id if self.field_rng.random() < 0.5 else away.team_id
        self.second_half_receiver = self._other(receiver)
        self._kickoff(receiving=receiver)

    # -- helpers --
    def _other(self, team_id: str) -> str:
        return self.away.team_id if team_id == self.home.team_id else self.home.team_id

    def situation(self) -> Situation:
        return Situation(self.quarter, self.clock, self.offense, self._other(self.offense), self.down,
                         self.distance, self.yardline, dict(self.score), dict(self.timeouts))

    def _unit(self, team_id: str, unit: str) -> float:
        return self.teams[team_id].units[unit] + (HOME_EDGE if team_id == self.home.team_id else 0)

    def _stat(self, player: dict, key: str, amount: int = 1) -> None:
        line = self.stats.setdefault(player["id"], {})
        line[key] = line.get(key, 0) + amount

    def _pick(self, team_id: str, positions: dict[str, float], rating: str | None = None) -> dict:
        """A player from the starters at the given positions, weighted, and by a rating if given."""
        lineup, rules = self.teams[team_id], {"WR": 3, "TE": 1, "RB": 1, "QB": 1, "DL": 4, "LB": 3, "CB": 2, "S": 2}
        pool, weights = [], []
        for pos, weight in positions.items():
            for p in lineup.starters(pos, rules.get(pos, 1)):
                pool.append(p)
                weights.append(weight * (math.exp((p["ratings"].get(rating, p["overall"]) - 70) / 12) if rating else 1))
        return self.field_rng.choices(pool, weights)[0]

    def _name(self, player: dict) -> str:
        return player["name"].split()[-1]

    def _spot(self) -> str:
        if self.yardline == 50:
            return "midfield"
        return f"{self.offense} {self.yardline}" if self.yardline < 50 else f"{self._other(self.offense)} {100 - self.yardline}"

    def _log(self, call: str, defense_call: str | None, result: str, yards: int, text: str, before: Situation) -> dict:
        entry = {"n": len(self.plays) + 1, "drive": self.drive, "quarter": before.quarter, "clock": before.clock,
                 "offense": before.offense, "down": before.down, "distance": before.distance,
                 "yardline": before.yardline, "call": call, "defense_call": defense_call, "result": result,
                 "yards": yards, "text": text, "home_score": self.score[self.home.team_id],
                 "away_score": self.score[self.away.team_id]}
        self.plays.append(entry)
        return entry

    # -- possessions --
    def _new_possession(self, team_id: str, yardline: int) -> None:
        self.offense, self.yardline = team_id, max(1, min(99, yardline))
        self.down, self.distance = 1, min(10, 100 - self.yardline)
        self.drive += 1

    def _kickoff(self, receiving: str) -> None:
        if self.field_rng.random() < 0.65:
            start = 25
        else:
            start = int(max(8, min(45, self.field_rng.gauss(24, 7))))
        self._new_possession(receiving, start)

    def _score(self, team_id: str, points: int) -> None:
        self.score[team_id] += points
        if self.quarter == 5:  # overtime is sudden death
            self.over = True

    def _touchdown(self) -> str:
        team = self.offense
        self._score(team, 6)
        if self.over:
            return ""
        kicker = self.teams[team].starters("K", 1)[0]
        made = self.field_rng.random() < 0.93 + (self.teams[team].units["kick_accuracy"] - 75) * 0.003
        self._stat(kicker, "xp_att")
        if made:
            self._stat(kicker, "xp_made")
            self.score[team] += 1
        self._kickoff(receiving=self._other(team))
        return "" if made else " Extra point no good."

    def _turnover(self, yardline_for_new_offense: int) -> None:
        self._new_possession(self._other(self.offense), yardline_for_new_offense)

    def _safety(self) -> None:
        defense = self._other(self.offense)
        self._score(defense, 2)
        if not self.over:
            self._new_possession(defense, 35)  # free kick after a safety

    # -- clock --
    def _run_clock(self, seconds: int, stops: bool, before: Situation, out_of_bounds: bool = False) -> None:
        trailing = None
        if before.score[before.offense] != before.score[before.defense]:
            trailing = min(before.score, key=before.score.get)
        two_minute = self.clock <= 120 and self.quarter in (2, 4, 5)
        if out_of_bounds and (two_minute or (self.quarter == 4 and self.clock <= 300)):
            stops = True
        if not stops and two_minute and trailing and self.timeouts[trailing] > 0:
            self.timeouts[trailing] -= 1
            stops = True
        hurry = before.late and before.lead < 0 or (self.quarter == 2 and self.clock <= 120)
        used = self.field_rng.randint(4, 8) if stops else (self.field_rng.randint(12, 20) if hurry else seconds)
        self.clock -= used
        if self.clock <= 0:
            self._end_of_period()

    def _end_of_period(self) -> None:
        if self.quarter == 2:
            self.quarter, self.clock = 3, QUARTER_SECONDS
            self.timeouts = {t: TIMEOUTS_PER_HALF for t in self.timeouts}
            self._kickoff(receiving=self.second_half_receiver)
        elif self.quarter == 4:
            if self.score[self.home.team_id] == self.score[self.away.team_id]:
                self.quarter, self.clock = 5, OVERTIME_SECONDS
                self.timeouts = {t: 2 for t in self.timeouts}
                self._kickoff(receiving=self.home.team_id if self.field_rng.random() < 0.5 else self.away.team_id)
            else:
                self.over = True
        elif self.quarter == 5:
            self.over = True  # overtime ran out: a tie
        else:
            self.quarter, self.clock = self.quarter + 1, QUARTER_SECONDS

    # -- one snap --
    def step(self, offense_call: str | None = None, defense_call: str | None = None) -> dict:
        """Run one snap. Calls left as None are made by the AI. Returns the play's log entry."""
        if self.over:
            raise ValueError("The game is over.")
        sit = self.situation()
        offense, defense = self.teams[sit.offense], self.teams[sit.defense]
        call = offense_call or call_offense(sit, offense, defense, self.call_rng)
        if call in FOURTH_DOWN or call == "kneel":
            return self._special(call, sit)
        if call not in OFFENSE_PLAYS:
            raise ValueError(f"Unknown play {call!r}. Plays: {OFFENSE_PLAYS + FOURTH_DOWN + ('kneel',)}")
        dcall = defense_call or call_defense(sit, defense, offense, self.call_rng)
        if dcall not in DEFENSE_CALLS:
            raise ValueError(f"Unknown defensive call {dcall!r}. Calls: {DEFENSE_CALLS}")
        unit, against = UNITS[call]
        edge = soften(self._unit(sit.offense, unit) - self._unit(sit.defense, against)) + MATCHUP[call][dcall]
        if call in RUNS:
            return self._run(call, dcall, edge, sit)
        return self._pass(call, dcall, edge, sit)

    def _advance(self, call: str, dcall: str, yards: int, sit: Situation, text: str, result: str,
                 seconds: int, stops: bool = False, out_of_bounds: bool = False) -> dict:
        """Move the ball, then handle a touchdown, safety, first down or turnover on downs."""
        rng = self.field_rng
        if self.yardline + yards >= 100:
            yards = 100 - self.yardline
            text += self._touchdown()
            entry = self._log(call, dcall, "touchdown", yards, text.replace("{yards}", f"{yards} yards") + " TOUCHDOWN.", sit)
            self._run_clock(rng.randint(5, 9), True, sit)
            return entry
        if self.yardline + yards <= 0:
            self._safety()
            entry = self._log(call, dcall, "safety", yards, text.replace("{yards}", "") + " SAFETY.", sit)
            self._run_clock(rng.randint(5, 9), True, sit)
            return entry
        self.yardline += yards
        if yards >= self.distance:
            self.down, self.distance = 1, min(10, 100 - self.yardline)
            text += " First down."
        elif self.down == 4:
            text += " Turnover on downs."
            self._turnover(100 - self.yardline)
            result = "turnover_on_downs"
            stops = True
        else:
            self.down, self.distance = self.down + 1, self.distance - yards
        entry = self._log(call, dcall, result, yards, text.replace("{yards}", _yards(yards)), sit)
        self._run_clock(seconds, stops, sit, out_of_bounds)
        return entry

    def _run(self, call: str, dcall: str, edge: float, sit: Situation) -> dict:
        rng = self.field_rng
        carrier = self.teams[sit.offense].starters("RB", 2)
        runner = carrier[0] if len(carrier) < 2 or rng.random() < 0.82 else carrier[1]
        inside = call == "run_inside"
        yards = rng.gauss((3.9 if inside else 4.1) + 0.08 * edge, 3.0 if inside else 4.6)
        if rng.random() < (0.025 if inside else 0.045) + 0.0015 * edge:
            yards += rng.expovariate(1 / 16)
        yards = max(-4, round(yards))
        self._stat(runner, "rush_att")
        if rng.random() < 0.007:
            self._stat(runner, "fumbles_lost")
            spot = self.yardline + max(0, yards)
            text = f"{self._name(runner)} {call.replace('_', ' ')[4:]} run, FUMBLE, recovered by {sit.defense}."
            if spot >= 100:
                spot = 99
            self._turnover(100 - spot)
            entry = self._log(call, dcall, "fumble", yards, text, sit)
            self._run_clock(rng.randint(5, 9), True, sit)
            return entry
        gained = min(yards, 100 - self.yardline)
        self._stat(runner, "rush_yds", gained)
        if self.yardline + yards >= 100:
            self._stat(runner, "rush_td")
        side = "up the middle" if inside else rng.choice(["around left end", "around right end"])
        out_of_bounds = not inside and rng.random() < 0.2
        return self._advance(call, dcall, yards, sit, f"{self._name(runner)} runs {side} for {{yards}}.", "run",
                             rng.randint(34, 46), out_of_bounds=out_of_bounds)

    def _pass(self, call: str, dcall: str, edge: float, sit: Situation) -> dict:
        rng = self.field_rng
        offense, defense = self.teams[sit.offense], self.teams[sit.defense]
        qb = offense.starters("QB", 1)[0]
        hold = {"pass_short": 0.6, "pass_deep": 1.4, "play_action": 1.3, "screen": 0.4}[call]
        rush_edge = self._unit(sit.defense, "pass_rush") - self._unit(sit.offense, "pass_block")
        p_sack = (0.055 + 0.003 * rush_edge) * hold * (1.7 if dcall == "blitz" else 1.0)
        p_sack *= 1 - (offense.units["mobility"] - 70) * 0.01
        if rng.random() < max(0.005, p_sack):
            loss = -rng.randint(3, 10)
            rusher = self._pick(sit.defense, {"DL": 1.0, "LB": 0.4 if dcall != "blitz" else 1.0}, "pass_rush")
            self._stat(qb, "sacked")
            self._stat(rusher, "def_sacks")
            return self._advance(call, dcall, loss, sit, f"{self._name(qb)} sacked by {self._name(rusher)} for a loss of "
                                 f"{-loss}.", "sack", rng.randint(28, 38))
        if call != "screen" and rng.random() < 0.025 + (offense.units["mobility"] - 70) * 0.002:
            yards = max(-2, round(rng.gauss(5, 4)))
            self._stat(qb, "rush_att")
            self._stat(qb, "rush_yds", min(yards, 100 - self.yardline))
            if self.yardline + yards >= 100:
                self._stat(qb, "rush_td")
            return self._advance(call, dcall, yards, sit, f"{self._name(qb)} scrambles for {{yards}}.", "run",
                                 rng.randint(28, 38))

        targets = {"pass_short": ({"WR": 1.0, "TE": 0.8, "RB": 0.35}, "route_running"),
                   "pass_deep": ({"WR": 1.0, "TE": 0.25}, "speed"),
                   "play_action": ({"WR": 1.0, "TE": 0.6}, "route_running"),
                   "screen": ({"RB": 1.0, "WR": 0.25}, "speed")}[call]
        target = self._pick(sit.offense, *targets)
        self._stat(qb, "pass_att")
        self._stat(target, "targets")
        decision = offense.units["decision"]
        p_int = {"pass_short": 0.021, "pass_deep": 0.042, "play_action": 0.03, "screen": 0.008}[call]
        p_int *= max(0.4, 1 + (70 - decision) * 0.025) * max(0.4, 1 - edge * 0.02)
        air = {"pass_short": 7, "pass_deep": 24, "play_action": 15, "screen": -1}[call]
        if rng.random() < p_int:
            picker = self._pick(sit.defense, {"CB": 1.0, "S": 1.0 if call != "pass_short" else 0.6,
                                              "LB": 0.5 if call in ("pass_short", "screen") else 0.0}, "coverage")
            self._stat(qb, "int_thrown")
            self._stat(picker, "def_int")
            spot = min(99, self.yardline + max(air, 1))
            back = max(0, round(rng.gauss(8, 8)))
            text = f"{self._name(qb)} pass intended for {self._name(target)} INTERCEPTED by {self._name(picker)}."
            self._turnover(100 - spot + back)
            entry = self._log(call, dcall, "interception", 0, text, sit)
            self._run_clock(rng.randint(6, 10), True, sit)
            return entry
        p_comp = {"pass_short": 0.71, "pass_deep": 0.42, "play_action": 0.57, "screen": 0.80}[call] + 0.006 * edge
        if rng.random() >= min(0.92, max(0.15, p_comp)):
            text = f"{self._name(qb)} pass {('short' if call == 'pass_short' else 'deep' if call != 'screen' else 'screen')} " \
                   f"to {self._name(target)} incomplete."
            return self._advance(call, dcall, 0, sit, text, "incomplete", 0, stops=True)

        mean, spread = {"pass_short": (7.8, 3.0), "pass_deep": (27.0, 8.0), "play_action": (16.5, 6.0),
                        "screen": (4.5, 4.0)}[call]
        yards = rng.gauss(mean + 0.08 * edge, spread)
        if rng.random() < 0.035 + 0.0015 * edge + (0.03 if call == "screen" else 0):
            yards += rng.expovariate(1 / 14)
        yards = max(-3 if call == "screen" else 1, round(yards))
        gained = min(yards, 100 - self.yardline)
        self._stat(qb, "pass_cmp")
        self._stat(qb, "pass_yds", gained)
        self._stat(target, "rec")
        self._stat(target, "rec_yds", gained)
        if self.yardline + yards >= 100:
            self._stat(qb, "pass_td")
            self._stat(target, "rec_td")
        out_of_bounds = rng.random() < 0.18
        return self._advance(call, dcall, yards, sit, f"{self._name(qb)} pass complete to {self._name(target)} "
                             f"for {{yards}}.", "complete", rng.randint(34, 46), out_of_bounds=out_of_bounds)

    def _special(self, call: str, sit: Situation) -> dict:
        rng = self.field_rng
        team = self.teams[sit.offense]
        if call == "kneel":
            qb = team.starters("QB", 1)[0]
            return self._advance(call, None, -1, sit, f"{self._name(qb)} kneels.", "kneel", 40)
        if call == "punt":
            punter = team.starters("P", 1)[0]
            gross = max(25, round(rng.gauss(43 + (team.units["punt_power"] - 70) * 0.3, 5)))
            self._stat(punter, "punts")
            self._stat(punter, "punt_yds", gross)
            if self.yardline + gross >= 100:
                text, start = f"{self._name(punter)} punts {gross} yards. Touchback.", 20
            else:
                back = max(0, round(rng.gauss(8, 6)))
                start = 100 - (self.yardline + gross) + back
                text = f"{self._name(punter)} punts {gross} yards, returned {back}."
            self._turnover(start)
            entry = self._log(call, None, "punt", 0, text, sit)
            self._run_clock(rng.randint(8, 12), True, sit)
            return entry
        # Field goal
        kicker = team.starters("K", 1)[0]
        distance = field_goal_distance(self.yardline)
        reach = 45 + (team.units["kick_power"] - 60) * 0.5
        p_make = 0.99 - max(0, distance - 25) * 0.013 + (team.units["kick_accuracy"] - 75) * 0.006
        if distance > reach:
            p_make *= 0.25
        self._stat(kicker, "fg_att")
        if rng.random() < min(0.99, max(0.02, p_make)):
            self._stat(kicker, "fg_made")
            self._score(sit.offense, 3)
            text = f"{self._name(kicker)} {distance}-yard field goal is GOOD."
            if not self.over:
                self._kickoff(receiving=sit.defense)
            result = "field_goal"
        else:
            text = f"{self._name(kicker)} {distance}-yard field goal is NO GOOD."
            self._turnover(max(20, 100 - (self.yardline - 7)))
            result = "field_goal_missed"
        entry = self._log(call, None, result, 0, text, sit)
        self._run_clock(rng.randint(5, 9), True, sit)
        return entry

    def play(self) -> "Game":
        """Let the AI call everything until the game ends."""
        while not self.over:
            self.step()
        return self

    def player_stats(self) -> list[dict]:
        return [{"player_id": pid, "team_id": self.player_team[pid], **line} for pid, line in self.stats.items()]


def _yards(n: int) -> str:
    if n == 0:
        return "no gain"
    if n < 0:
        return f"a loss of {-n}"
    return f"{n} yard{'s' if n != 1 else ''}"
