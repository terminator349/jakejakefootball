"""Ask the Cap & Contracts agent whether a roster move fits under the salary cap.

    python check_cap.py
    python check_cap.py "Can we sign a free agent safety to a $6M/year contract?"
    python check_cap.py --debug      # print every tool call and model message
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from agents.cap_contracts import CapReport, build_cap_contracts_agent, ground_report, league_office_tools

DEFAULT_QUESTION = "Is every team in the league legal under the $255M hard cap right now?"


def print_report(report: CapReport) -> None:
    print(f"\n=== Cap & Contracts report: {report.team_id} ===")
    print(report.answer)
    print("Evidence:")
    for line in report.evidence:
        print(f"  - {line}")
    if report.cap_space >= 0:
        cap_status = f"${report.cap_space:.1f}M of cap space"
    else:
        cap_status = f"${-report.cap_space:.1f}M OVER the cap"
    print(f"Payroll:          ${report.payroll:.1f}M  ({cap_status})")
    print(f"Fits under cap:   {report.fits_under_cap}")
    if not report.fits_under_cap:
        print(f"Salary to clear:  ${report.salary_to_clear:.1f}M")


async def ask(question: str, debug: bool):
    # Start the League Office server for this run; it stops when the block ends.
    async with league_office_tools() as league_office:
        agent = build_cap_contracts_agent(league_office, debug=debug)
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

    if isinstance(response.content, CapReport):
        print_report(ground_report(response.content))
    else:
        # The model didn't return the schema; show what it did say.
        print(response.content)


if __name__ == "__main__":
    main()
