"""Ask the Medical agent about who is currently injured.

    python check_medical.py
    python check_medical.py "How much longer is our starting safety out?"
    python check_medical.py --debug      # print every tool call and model message
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from agents.medical import MedicalReport, build_medical_agent, ground_report, league_office_tools

DEFAULT_QUESTION = "Who's currently injured on our team, and which position group does it leave thinnest?"


def print_report(report: MedicalReport) -> None:
    print(f"\n=== Medical report: {report.team_id} ===")
    print(report.answer)
    print("\nInjuries:")
    for line in report.injuries or ["  (none)"]:
        print(f"  - {line}")
    print(f"\nThinnest position: {report.thinnest_position or '(none)'}")
    print("Evidence:")
    for line in report.evidence:
        print(f"  - {line}")


async def ask(question: str, debug: bool):
    # Start the League Office server for this run; it stops when the block ends.
    async with league_office_tools() as league_office:
        agent = build_medical_agent(league_office, debug=debug)
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

    if isinstance(response.content, MedicalReport):
        print_report(ground_report(response.content))
    else:
        # The model didn't return the schema; show what it did say.
        print(response.content)


if __name__ == "__main__":
    main()
