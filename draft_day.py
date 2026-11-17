"""Run the 6-team, 53-round snake draft.

    python draft_day.py                 # choose your team interactively
    python draft_day.py --team HAR       # control Harbor City directly
    python draft_day.py --watch          # just watch all 6 CPU GMs draft
    python draft_day.py --no-llm         # CPU picks use heuristic scoring only, no API calls
    python draft_day.py --seed 7         # reproducible draft order, for testing

CPU teams are drafted by an LLM agent (agents/analytics.py's sibling, in
draft/agent.py) that sees a shortlist of the best-value/best-need players and
picks one; your team is drafted by you, from the command line.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

from draft.engine import DraftEngine
from draft.players import Player
from draft.roster_rules import ROSTER_TEMPLATE, ROUNDS, SALARY_CAP, TEAMS, rookie_salary
from draft.team import Team
from draft.valuation import market_value, pick_score

BOARD_SIZE = 20


def choose_user_team() -> str | None:
    print("\nTeams:")
    for team_id, city, name in TEAMS:
        print(f"  {team_id}  {city} {name}")
    while True:
        raw = input("\nWhich team do you want to control? (team id, 'random', or 'watch') > ").strip().lower()
        if raw == "watch":
            return None
        if raw == "random":
            return random.choice(TEAMS)[0]
        for team_id, _, _ in TEAMS:
            if raw == team_id.lower():
                return team_id
        print(f"Not a valid team id. Choices: {', '.join(t[0] for t in TEAMS)}")


def print_board(players: list[Player], overall_pick: int) -> None:
    if not players:
        print("  (nothing available at that position)")
        return
    print(f"  {'ID':<8}{'NAME':<24}{'POS':<5}{'OVR':<5}{'VALUE $M':<10}{'COST $M':<10}")
    for p in players:
        cost = rookie_salary(overall_pick, p.position)
        print(f"  {p.id:<8}{p.name:<24}{p.position:<5}{p.overall:<5}{market_value(p.overall, p.position):<10}{cost:<10}")


def print_needs(team: Team) -> None:
    counts = team.position_counts()
    print(f"\n{team.display_name}: {len(team.roster)}/53 filled | "
          f"cap room ${team.cap_room():.1f}M of ${SALARY_CAP:.1f}M")
    needs = team.needs()
    if needs:
        need_str = ", ".join(f"{pos} (have {counts.get(pos, 0)}/{ROSTER_TEMPLATE[pos]})" for pos in needs)
        print(f"Open needs: {need_str}")
    else:
        print("Roster complete.")


def print_help() -> None:
    print(
        "  board            top available, eligible players (value+need ranked)\n"
        "  board <POS>      every available, eligible player at that position (e.g. 'board wr')\n"
        "  needs            your roster counts, cap room and open positions\n"
        "  best             auto-pick the engine's top-ranked choice for you\n"
        "  pick <id>        draft that player, e.g. 'pick WR-07'\n"
        "  help             show this again"
    )


def find_by_id(players: list[Player], player_id: str) -> Player | None:
    for p in players:
        if p.id.lower() == player_id.lower():
            return p
    return None


def user_turn(engine, team: Team, round_number: int, overall_pick: int) -> Player:
    print(f"\n=== Pick #{overall_pick} (Round {round_number}) - YOUR PICK: {team.display_name} ===")
    print_needs(team)
    eligible = engine.eligible_for(team, overall_pick)
    ranked = engine.ranked(team, overall_pick)
    print_board(ranked[:BOARD_SIZE], overall_pick)
    while True:
        raw = input("\nyour move ('help' for commands) > ").strip()
        parts = raw.split()
        if not parts:
            print_board(ranked[:BOARD_SIZE], overall_pick)
            continue
        cmd = parts[0].lower()
        if cmd in ("board", "list"):
            if len(parts) > 1:
                pos = parts[1].upper()
                subset = sorted((p for p in eligible if p.position == pos), key=lambda p: p.overall, reverse=True)
                print_board(subset, overall_pick)
            else:
                print_board(ranked[:BOARD_SIZE], overall_pick)
        elif cmd == "needs":
            print_needs(team)
        elif cmd == "best":
            if ranked:
                return ranked[0]
            print("No eligible players left - this shouldn't happen.")
        elif cmd == "pick":
            if len(parts) < 2:
                print("Usage: pick <player_id>")
                continue
            player = find_by_id(eligible, parts[1])
            if player is None:
                print(f"'{parts[1]}' isn't an available, eligible player id. Type 'board' to see choices.")
                continue
            return player
        elif cmd == "help":
            print_help()
        else:
            print("Didn't understand that. Type 'help' for commands.")


def on_pick(team: Team, player: Player, round_number: int, overall_pick: int) -> None:
    tag = "YOU " if team.is_user else team.id
    print(f"Pick {overall_pick:>3} (Rd {round_number:>2}) {tag:>4}  draft {player.position:<4} "
          f"{player.name:<24} (OVR {player.overall}, ${player.salary:.1f}M)")


def print_final_summary(engine: DraftEngine) -> None:
    print("\n" + "=" * 72)
    print("DRAFT COMPLETE")
    print("=" * 72)
    for team in engine.teams:
        tag = " (YOU)" if team.is_user else ""
        print(f"\n{team.display_name}{tag} - {len(team.roster)} players, "
              f"${team.payroll():.1f}M payroll, ${team.cap_room():.1f}M cap room")
        counts = team.position_counts()
        print("  " + ", ".join(f"{pos}:{counts.get(pos, 0)}" for pos in ROSTER_TEMPLATE))
        if team.payroll() > SALARY_CAP:
            print("  *** OVER THE HARD CAP - illegal roster ***")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", help="Team id to control (e.g. HAR). Omit to be prompted.")
    parser.add_argument("--watch", action="store_true", help="Control no team; watch all 6 CPU GMs draft.")
    parser.add_argument("--no-llm", action="store_true",
                         help="CPU picks use heuristic value+need scoring only - no API calls, instant, free.")
    parser.add_argument("--seed", type=int, default=None, help="Seed the random draft order, for a reproducible run.")
    parser.add_argument("--debug", action="store_true", help="Show each CPU GM agent's model calls.")
    args = parser.parse_args()

    load_dotenv()
    if not args.no_llm and not os.getenv("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set (needed for the CPU GMs). Add it to .env, "
                 "or pass --no-llm to use heuristic-only CPU picks.")

    valid_ids = {t[0] for t in TEAMS}
    if args.watch:
        user_team_id = None
    elif args.team:
        user_team_id = args.team.upper()
        if user_team_id not in valid_ids:
            sys.exit(f"Unknown team id {args.team!r}. Valid ids: {sorted(valid_ids)}")
    else:
        user_team_id = choose_user_team()

    print(f"\nStarting a {len(TEAMS)}-team, {ROUNDS}-round snake draft "
          f"({'LLM' if not args.no_llm else 'heuristic'} CPU GMs)...")
    engine = DraftEngine(user_team_id=user_team_id, seed=args.seed, use_llm=not args.no_llm, debug=args.debug)

    print("\nRandom draft order (round 1 order; even rounds snake back):")
    for i, team in enumerate(engine.draft_order, start=1):
        tag = "  <- YOU" if team.is_user else (f"  ({team.philosophy.split(':')[0]})" if team.philosophy else "")
        print(f"  {i}. {team.display_name}{tag}")

    engine.run(on_user_turn=user_turn, on_pick=on_pick)

    print_final_summary(engine)
    out_path = Path(__file__).parent / "data" / "draft_results.json"
    out_path.write_text(json.dumps(engine.to_dict(), indent=2))
    print(f"\nWrote full draft results to {out_path}")


if __name__ == "__main__":
    main()
