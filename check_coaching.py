"""Ask the Coaching agent about the depth chart or the game plan.

    python check_coaching.py
    python check_coaching.py "Our starting safety is hurt. Who should start instead?"
    python check_coaching.py --debug      # print every tool call and model message
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from agents.coaching import CoachingReport, build_coaching_agent, ground_report, league_office_tools

DEFAULT_QUESTION = "What should our game plan be against our next opponent, and does the depth chart need any changes?"


def print_report(report: CoachingReport) -> None:
    print(f"\n=== Coaching report: {report.team_id} ===")
    print(report.answer)
    print("\nDepth chart changes:")
    for line in report.depth_chart_changes or ["  (none)"]:
        print(f"  - {line}")
    print(f"\nGame plan: {report.game_plan}")
    print("Evidence:")
    for line in report.evidence:
        print(f"  - {line}")


async def ask(question: str, debug: bool):
    # Start the League Office server for this run; it stops when the block ends.
    async with league_office_tools() as league_office:
        agent = build_coaching_agent(league_office, debug=debug)
        return await agent.arun(question)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--debug", action="store_true", help="show tool calls and model messages")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set. Add your OpenRouter key to .env (see .env.example).")

    response = asyncio.run(ask(args.question, args.debug))

    if isinstance(response.content, CoachingReport):
        print_report(ground_report(response.content))
    else:
        # The model didn't return the schema; show what it did say.
        print(response.content)


if __name__ == "__main__":
    main()
