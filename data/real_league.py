"""Build the real league (task 4.4): the six franchises filled with real NFL players.

    python data/nflverse_fetch.py    # once: the public 2025 data, about 7 MB, into data/nflverse/
    python data/real_league.py       # writes data/league_real.json

The game is played on data/league.json, a generated league, unless the owner picks
"Real 2025 players" at New game. Then the save is built from league_real.json,
which this script writes from nflverse's 2025 regular season: rosters, season
stats, Pro Football Reference's advanced stats and snap counts.

How a real player becomes a game player:

- Who's in: at each position, the players who played the most in 2025 (snaps;
  kicks and punts for K and P), as many as six 48-man rosters hold.
- Ratings: each skill (a cornerback's coverage, a QB's accuracy...) is scored
  from the stats that show it (passer rating allowed, completion % over expected...),
  rate stats pulled toward the average on few attempts. Players are ranked by
  that score, and the ranks are given the generated league's ratings for that
  skill, so a real league plays on the same scale and the simulator stays balanced.
  Where no stat shows a skill (an offensive lineman's blocking, a defensive back's
  speed), the score uses what does exist (playing time, the team's sack and rushing
  numbers, weight, age); RATING_SOURCES says which.
- Teams: the six franchises draft each position in turns, starters first, so they
  come out even. The Herons get the weakest starting secondary, as in the generated league.
- Salaries: nflverse's contract file ends with deals signed in 2022, so salaries use
  the game's own pay scale on each player's rating (data/generate_league.py), with
  players in their first four seasons on rookie deals by real draft position. Each
  team's payroll matches the generated league's, so the Herons have $5.5M of cap space.
- Age is on Sep 1, 2025; games missed are the team's games he sat out between his
  first and last game, plus the rest of the season if he ended it on injured reserve.
"""

import csv
import gzip
import json
import random
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import generate_league as gen

SEASON = 2025
DATA_DIR = Path(__file__).parent
RAW_DIR = DATA_DIR / "nflverse"
OUT_FILE = DATA_DIR / "league_real.json"
SEED = 2025
SEASON_START = date(2025, 9, 1)
ROOKIE_SEASONS = 4      # players in their first four seasons are on rookie deals
OFFENSE = {"QB", "RB", "WR", "TE", "OL"}
SECONDARY = ("CB", "S")
VOLUME_WEIGHT = 0.5     # playing time counts in every rating: coaches play their better players

# Which stats score each rating, for the docs and the tests (the code is in SKILLS below).
RATING_SOURCES = {
    "QB": {"accuracy": "completion % over expected, on-target %", "arm_strength": "intended air yards per throw, 20+ yard completions",
           "decision_making": "EPA per dropback, interception and sack rates", "mobility": "rushing yards per game, rushing EPA"},
    "RB": {"rushing": "rushing EPA per carry, yards after contact, carries", "receiving": "receiving yards per game, yards per target",
           "pass_protection": "share of snaps (no public stat)", "speed": "20+ and 40+ yard runs per carry"},
    "WR": {"route_running": "targets per game, yards per target", "hands": "catch rate, drop %",
           "speed": "average depth of target, 20+ yard catches"},
    "TE": {"receiving": "receiving yards per game, yards per target", "blocking": "snaps not spent as a target (no public stat)",
           "speed": "yards after catch per catch"},
    "OL": {"pass_blocking": "share of snaps, the team's sack rate (no public stat per lineman)",
           "run_blocking": "share of snaps, the team's rushing EPA per carry", "strength": "weight, share of snaps"},
    "DL": {"pass_rush": "pressures, sacks and QB hits per game", "run_defense": "tackles for loss and solo tackles per game",
           "strength": "weight, share of snaps"},
    "LB": {"run_defense": "tackles and tackles for loss per game", "coverage": "yards per target and passer rating allowed",
           "tackling": "missed tackle %", "pass_rush": "pressures and sacks per game"},
    "CB": {"coverage": "passer rating and yards per target allowed, passes defended, interceptions",
           "speed": "age, passes defended (no public stat)", "tackling": "missed tackle %, solo tackles per game"},
    "S": {"coverage": "passer rating and yards per target allowed, passes defended, interceptions",
          "speed": "age, passes defended (no public stat)", "tackling": "missed tackle %, solo tackles per game"},
    "K": {"kick_power": "longest field goal, 50+ yard field goals", "kick_accuracy": "field goal and extra point %"},
    "P": {"kick_power": "gross yards per punt", "kick_accuracy": "net yards per punt, punts inside the 20"},
}


# ---- Reading the data -------------------------------------------------------------

def num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rows(name: str) -> list[dict]:
    path = RAW_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python data/nflverse_fetch.py")
    opener = gzip.open if name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def game_position(roster_row: dict, stats_position: str = "") -> str | None:
    """The game's position for a real player, or None for one the game doesn't have (long snappers)."""
    pos, depth = roster_row["position"], roster_row["depth_chart_position"]
    if pos in ("QB", "RB", "WR", "TE", "OL", "DL", "LB", "K", "P"):
        return pos
    if pos == "DB":
        if depth in ("FS", "SS", "S") or (depth not in ("CB",) and stats_position in ("SAF", "FS", "SS", "S")):
            return "S"
        return "CB"
    return None


def load_players() -> list[dict]:
    """Everyone who played a 2025 regular-season snap, with his stats joined on."""
    roster = _rows(f"roster_{SEASON}.csv")
    by_pfr = {r["pfr_id"]: r for r in roster if r["pfr_id"]}
    by_name_team = {(r["full_name"], r["team"]): r for r in roster}
    stats = {r["player_id"]: r for r in _rows(f"stats_player_reg_{SEASON}.csv")}
    adv = {kind: {r["pfr_id"]: r for r in _rows(f"advstats_season_{kind}.csv") if r["season"] == str(SEASON)}
           for kind in ("pass", "rush", "rec", "def")}

    snaps = [r for r in _rows(f"snap_counts_{SEASON}.csv") if r["game_type"] == "REG"]
    team_games: dict[str, set] = defaultdict(set)
    side_max: dict[tuple, float] = defaultdict(float)  # (game, team, side) -> the team's snaps that game
    for r in snaps:
        team_games[r["team"]].add(int(r["week"]))
        for side in ("offense", "defense"):
            side_max[(r["game_id"], r["team"], side)] = max(side_max[(r["game_id"], r["team"], side)], num(r[f"{side}_snaps"]))

    played: dict[str, dict] = {}
    for r in snaps:
        p = played.setdefault(r["pfr_player_id"], {"name": r["player"], "pfr_id": r["pfr_player_id"], "weeks": {},
                                                   "offense": 0.0, "defense": 0.0, "offense_of": 0.0, "defense_of": 0.0})
        week = int(r["week"])
        p["team"] = r["team"] if week >= max(p["weeks"], default=0) else p["team"]
        if num(r["offense_snaps"]) + num(r["defense_snaps"]) + num(r["st_snaps"]) > 0:
            p["weeks"][week] = r["team"]
        for side in ("offense", "defense"):
            p[side] += num(r[f"{side}_snaps"])
            p[f"{side}_of"] += side_max[(r["game_id"], r["team"], side)]

    players = []
    for p in played.values():
        row = by_pfr.get(p["pfr_id"]) or by_name_team.get((p["name"], p["team"]))
        if row is None:
            continue
        s = stats.get(row["gsis_id"], {})
        position = game_position(row, s.get("position", ""))
        if position is None:
            continue
        side = "offense" if position in OFFENSE else "defense"
        team = p["team"]
        games = len(p["weeks"])
        first, last = (min(p["weeks"]), max(p["weeks"])) if p["weeks"] else (0, 0)
        sat_out = len([w for w in team_games[team] if first <= w <= last and w not in p["weeks"]])
        if row["status"] == "RES":
            sat_out += len([w for w in team_games[team] if w > last])
        players.append({
            "name": row["full_name"], "nfl_team": team, "position": position, "games": games,
            "snap_share": p[side] / p[f"{side}_of"] if p[f"{side}_of"] else 0.0,
            "snaps": p[side], "weight": num(row["weight"]), "age": _age(row),
            "years_exp": int(num(row["years_exp"])), "rookie_year": int(num(row["rookie_year"])) or None,
            "draft_number": int(num(row["draft_number"])) or None,
            "games_missed": min(17, sat_out),
            "stats": s, "pass": adv["pass"].get(p["pfr_id"], {}), "rush": adv["rush"].get(p["pfr_id"], {}),
            "rec": adv["rec"].get(p["pfr_id"], {}), "def": adv["def"].get(p["pfr_id"], {}),
        })
    _add_team_line_stats(players, list(stats.values()))
    return players


def _age(row: dict) -> int:
    try:
        born = date.fromisoformat(row["birth_date"])
    except ValueError:
        return 22 + int(num(row["years_exp"]))
    return SEASON_START.year - born.year - ((SEASON_START.month, SEASON_START.day) < (born.month, born.day))


def _add_team_line_stats(players: list[dict], stats: list[dict]) -> None:
    """No stat grades one lineman, so an offensive line shares its team's numbers."""
    carries, rush_epa, dropbacks, sacks = (defaultdict(float) for _ in range(4))
    for s in stats:
        team = s["recent_team"]
        carries[team] += num(s["carries"])
        rush_epa[team] += num(s["rushing_epa"])
        dropbacks[team] += num(s["attempts"]) + num(s["sacks_suffered"])
        sacks[team] += num(s["sacks_suffered"])
    for p in players:
        t = p["nfl_team"]
        p["team_rush_epa"] = rush_epa[t] / carries[t] if carries[t] else 0.0
        p["team_sack_rate"] = sacks[t] / dropbacks[t] if dropbacks[t] else 0.0


# ---- Scoring each skill -------------------------------------------------------------

def per_game(*keys, source="stats"):
    return lambda p: (sum(num(p[source].get(k)) for k in keys) / max(1, p["games"]), None)


def ratio(top, bottom, source="stats", k=0):
    """A rate stat, with how many attempts it rests on (so few attempts count for less)."""
    def f(p):
        n = sum(num(p[source].get(b)) for b in (bottom if isinstance(bottom, tuple) else (bottom,)))
        t = sum(num(p[source].get(x)) for x in (top if isinstance(top, tuple) else (top,)))
        return (t / n if n else None, n)
    f.k = k
    return f


def field(key, source, n_key=None, k=0):
    """A stat already given as a rate (e.g. passer rating allowed), weighed by n_key's count."""
    def f(p):
        n = num(p[source].get(n_key)) if n_key else None
        value = p[source].get(key)
        return (num(value) if value not in (None, "", "NA") and (n is None or n > 0) else None, n)
    f.k = k
    return f


def plain(key):
    return lambda p: (p[key], None)


def missed_tackles(p):
    total = num(p["def"].get("comb")) + num(p["def"].get("m_tkl"))
    return (num(p["def"].get("m_tkl")) / total if total else None, total)
missed_tackles.k = 25


def blocking_snaps(p):
    return (p["snap_share"] * (1 - min(1.0, num(p["stats"].get("targets")) / max(1.0, p["snaps"]) * 4)), None)


COVERAGE = [(field("rat", "def", "tgt", 40), -1.0), (field("yds_tgt", "def", "tgt", 40), -1.0),
            (per_game("def_pass_defended"), 0.6), (per_game("def_interceptions"), 0.4)]
DB_TACKLING = [(missed_tackles, -1.0), (per_game("def_tackles_solo"), 0.5)]
DB_SPEED = [(plain("age"), -1.0), (per_game("def_pass_defended"), 0.4)]

# Each rating: [(stat, weight)]; a negative weight means less is better.
SKILLS = {
    "QB": {
        "accuracy": [(field("passing_cpoe", "stats", "attempts", 150), 1.0), (field("on_tgt_pct", "pass", "pass_attempts", 150), 0.7)],
        "arm_strength": [(field("intended_air_yards_per_pass_attempt", "pass", "pass_attempts", 150), 1.0),
                         (ratio("passing_20", "attempts", k=150), 0.7)],
        "decision_making": [(ratio("passing_epa", ("attempts", "sacks_suffered"), k=150), 1.0),
                            (ratio("passing_interceptions", "attempts", k=150), -0.7),
                            (ratio("sacks_suffered", ("attempts", "sacks_suffered"), k=150), -0.4)],
        "mobility": [(per_game("rushing_yards"), 1.0), (ratio("rushing_epa", "carries", k=30), 0.4)],
    },
    "RB": {
        "rushing": [(ratio("rushing_epa", "carries", k=60), 1.0), (field("yac_att", "rush", "att", 60), 0.6), (per_game("carries"), 0.6)],
        "receiving": [(per_game("receiving_yards"), 1.0), (ratio("receiving_yards", "targets", k=20), 0.5)],
        "pass_protection": [(plain("snap_share"), 1.0)],
        "speed": [(ratio(("rushing_20", "rushing_40"), "carries", k=60), 1.0)],
    },
    "WR": {
        "route_running": [(per_game("targets"), 1.0), (ratio("receiving_yards", "targets", k=30), 0.7)],
        "hands": [(ratio("receptions", "targets", k=30), 1.0), (field("drop_percent", "rec", "tgt", 30), -0.6)],
        "speed": [(field("adot", "rec", "tgt", 30), 0.7), (per_game("receiving_20"), 0.7)],
    },
    "TE": {
        "receiving": [(per_game("receiving_yards"), 1.0), (ratio("receiving_yards", "targets", k=20), 0.5)],
        "blocking": [(blocking_snaps, 1.0)],
        "speed": [(ratio("receiving_yards_after_catch", "receptions", k=15), 1.0)],
    },
    "OL": {
        "pass_blocking": [(plain("snap_share"), 1.0), (plain("team_sack_rate"), -0.6)],
        "run_blocking": [(plain("snap_share"), 1.0), (plain("team_rush_epa"), 0.6)],
        "strength": [(plain("weight"), 0.8), (plain("snap_share"), 0.6)],
    },
    "DL": {
        "pass_rush": [(per_game("prss", source="def"), 1.0), (per_game("def_sacks", "def_qb_hits"), 0.8)],
        "run_defense": [(per_game("def_tackles_for_loss"), 1.0), (per_game("def_tackles_solo"), 0.7)],
        "strength": [(plain("weight"), 0.8), (plain("snap_share"), 0.6)],
    },
    "LB": {
        "run_defense": [(per_game("def_tackles_solo", "def_tackle_assists"), 1.0), (per_game("def_tackles_for_loss"), 0.6)],
        "coverage": [(field("yds_tgt", "def", "tgt", 30), -1.0), (field("rat", "def", "tgt", 30), -0.8),
                     (per_game("def_pass_defended"), 0.4)],
        "tackling": [(missed_tackles, -1.0)],
        "pass_rush": [(per_game("prss", source="def"), 1.0), (per_game("def_sacks"), 0.6)],
    },
    "CB": {"coverage": COVERAGE, "speed": DB_SPEED, "tackling": DB_TACKLING},
    "S": {"coverage": COVERAGE, "speed": DB_SPEED, "tackling": DB_TACKLING},
    "K": {
        "kick_power": [(field("fg_long", "stats"), 1.0), (per_game("fg_made_50_59", "fg_made_60_"), 0.8)],
        "kick_accuracy": [(ratio("fg_made", "fg_att", k=10), 1.0), (ratio("pat_made", "pat_att", k=10), 0.4)],
    },
    "P": {
        "kick_power": [(ratio("pt_yards", "pt_att", k=20), 1.0)],
        "kick_accuracy": [(ratio("pt_net_yards", "pt_att", k=20), 1.0), (ratio("pt_inside_20", "pt_att", k=20), 0.6)],
    },
}


def playing_time(p: dict) -> float:
    """How much he played: snaps, or kicks and punts for a kicker or punter."""
    s = p["stats"]
    if p["position"] == "K":
        return num(s.get("fg_att")) + num(s.get("pat_att"))
    if p["position"] == "P":
        return num(s.get("pt_att"))
    return p["snaps"]


def _zscores(values: list[float]) -> list[float]:
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values) or 1.0
    return [(v - mean) / sd for v in values]


def stat_column(pool: list[dict], stat) -> list[float]:
    """One stat for every player in the pool, rate stats pulled toward the pool's
    average by their attempts, and a missing rate set to that average."""
    raw = [stat(p) for p in pool]
    k = getattr(stat, "k", 0)
    weighted = [(v, n) for v, n in raw if v is not None and n]
    prior = (sum(v * n for v, n in weighted) / sum(n for _, n in weighted) if weighted
             else statistics.fmean([v for v, _ in raw if v is not None] or [0.0]))
    out = []
    for v, n in raw:
        if v is None:
            out.append(prior)
        elif n is not None and k:
            out.append((v * n + prior * k) / (n + k))
        else:
            out.append(v)
    return out


def skill_scores(pool: list[dict], position: str) -> dict[str, list[float]]:
    """Each skill's score for every player in the pool (z-scores, higher is better)."""
    volume = _zscores([playing_time(p) for p in pool])
    scores = {}
    for skill, parts in SKILLS[position].items():
        total = [VOLUME_WEIGHT * v for v in volume]
        for stat, weight in parts:
            for i, z in enumerate(_zscores(stat_column(pool, stat))):
                total[i] += weight * z
        scores[skill] = total
    return scores


def on_scale(scores: list[float], scale: list[int]) -> list[int]:
    """Give the ranks of `scores` the values of `scale`: the best score gets the
    highest rating on the scale, the median the median, and so on."""
    scale = sorted(scale)
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    out = [0] * len(scores)
    for rank, i in enumerate(order):
        q = rank / (len(scores) - 1) if len(scores) > 1 else 0.5
        out[i] = scale[round(q * (len(scale) - 1))]
    return out


# ---- Building the league -----------------------------------------------------------

def rate(players: list[dict], generated: dict) -> dict[str, list[dict]]:
    """The players each position keeps, with their game ratings and overall."""
    chosen = {}
    for position, count in gen.ROSTER_COUNTS.items():
        pool = sorted((p for p in players if p["position"] == position), key=lambda p: -playing_time(p))
        pool = pool[:len(gen.TEAMS) * count]
        scales = {skill: [g["ratings"][skill] for g in generated["players"]
                          if g["position"] == position and g["team_id"] != gen.OUR_TEAM]
                  for skill in gen.POSITION_RATINGS[position]}
        scores = skill_scores(pool, position)
        for skill, column in scores.items():
            for p, value in zip(pool, on_scale(column, scales[skill])):
                p.setdefault("ratings", {})[skill] = value
        for p in pool:
            p["ratings"] = {k: p["ratings"][k] for k in gen.POSITION_RATINGS[position]}
            p["overall"] = round(sum(p["ratings"].values()) / len(p["ratings"]))
        chosen[position] = pool
    return chosen


def split(chosen: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Deal each position's players to the six teams in turns (snake order, starters
    first), so the teams come out even. The Herons get the weakest starting secondary."""
    teams = [t[0] for t in gen.TEAMS]
    rosters = {t: [] for t in teams}
    for i, (position, players) in enumerate(chosen.items()):
        starters = gen.STARTERS[position] * len(teams)
        ranked = sorted(players, key=lambda p: -p["overall"])
        tiers = [ranked[:starters], ranked[starters:]]
        order = teams[i % len(teams):] + teams[:i % len(teams)]
        for t, tier in enumerate(tiers):
            if t:
                order = order[::-1]  # the bench round goes the other way, so nobody picks first twice
            per_team = len(tier) // len(teams)
            if position in SECONDARY:
                by_coverage = sorted(tier, key=lambda p: p["ratings"]["coverage"])
                ours = by_coverage[:per_team]
                rosters[gen.OUR_TEAM] += ours
                tier = [p for p in tier if p not in ours]
                drafting = [t for t in order if t != gen.OUR_TEAM]
            else:
                drafting = order
            for pick, p in enumerate(tier):
                rnd, slot = divmod(pick, len(drafting))
                rosters[drafting[slot if rnd % 2 == 0 else -1 - slot]].append(p)
    return rosters


def rookie_cap(p: dict) -> float | None:
    """A player in his first four seasons is on a rookie deal, worth more the higher he was drafted."""
    if p["rookie_year"] is None or p["rookie_year"] <= SEASON - ROOKIE_SEASONS:
        return None
    pick = p["draft_number"]
    return 3.0 if pick and pick <= 32 else 1.5 if pick and pick <= 100 else 0.5


def contract(p: dict, rng: random.Random) -> tuple[float, int]:
    """Raw pay on the game's scale (before payrolls are scaled) and the years left."""
    raw = gen.TOP_SALARY[p["position"]] * max(0.0, (p["overall"] - 55) / 35) ** 2
    cap = rookie_cap(p)
    if cap is not None:
        return min(raw, cap), max(1, ROOKIE_SEASONS - (SEASON - p["rookie_year"]))
    return raw, rng.randint(1, 5)


def build(players: list[dict], generated: dict) -> dict:
    rosters = split(rate(players, generated))
    payroll = defaultdict(float)
    for g in generated["players"]:
        payroll[g["team_id"]] += g["salary"]
    rng = random.Random(SEED)
    order = list(gen.ROSTER_COUNTS)
    out = []
    for team_id, _, _ in gen.TEAMS:
        roster = sorted(rosters[team_id], key=lambda p: (order.index(p["position"]), -p["overall"], p["name"]))
        team = []
        for n, p in enumerate(roster, 1):
            raw, years = contract(p, rng)
            team.append({"id": f"{team_id}-{n:02d}", "name": p["name"], "team_id": team_id, "position": p["position"],
                         "age": p["age"], "overall": p["overall"], "raw_salary": raw, "contract_years": years,
                         "games_missed_last_season": p["games_missed"], "ratings": p["ratings"],
                         "nfl_team": p["nfl_team"]})
        gen.scale_payroll(team, round(payroll[team_id], 2))
        out += team
    return {"sport": "american_football", "league": "real", "our_team": gen.OUR_TEAM, "rules": generated["rules"],
            "source": f"nflverse {SEASON} regular season (github.com/nflverse/nflverse-data), built by data/real_league.py",
            "teams": generated["teams"], "players": out}


def main() -> None:
    generated = json.loads((DATA_DIR / "league.json").read_text())
    league = build(load_players(), generated)
    OUT_FILE.write_text(json.dumps(league, indent=2))
    print(f"Wrote {len(league['teams'])} teams and {len(league['players'])} real players to {OUT_FILE}")


if __name__ == "__main__":
    main()
