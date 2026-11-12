"""Ask the Analytics agent a question about our roster.

    python run.py
    python run.py "How does our offensive line compare to the league?"
    python run.py --debug      # print every tool call and model message
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from agents.analytics import RosterReport, build_analytics_agent, ground_report, league_office_tools

DEFAULT_QUESTION = "We're 1 game out of a playoff spot. Where is our roster weakest, and what should we look for?"


def print_report(report: RosterReport) -> None:
    print(f"\n=== Analytics report: {report.team_id} ===")
    print(report.answer)
    print(f"\nWeakest area:   {report.weakest_area}")
    print("Evidence:")
    for line in report.evidence:
        print(f"  - {line}")
    print(f"Target profile: {report.target_profile}")
    if report.cap_space >= 0:
        cap_status = f"${report.cap_space:.1f}M of cap space"
    else:
        cap_status = f"${-report.cap_space:.1f}M OVER the cap"
    print(f"Payroll:        ${report.payroll:.1f}M  ({cap_status})")


async def ask(question: str, debug: bool):
    # Start the League Office server for this run; it stops when the block ends.
    async with league_office_tools() as league_office:
        agent = build_analytics_agent(league_office, debug=debug)
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

    if isinstance(response.content, RosterReport):
        print_report(ground_report(response.content))
    else:
        # The model didn't return the schema; show what it did say.
        print(response.content)


if __name__ == "__main__":
    main()
