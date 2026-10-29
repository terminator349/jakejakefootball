"""Ask the Analytics agent a question about our roster.

    python run.py
    python run.py "Who is our best defender?"
    python run.py --debug      # print every tool call and model message
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from agents.analytics import RosterReport, build_analytics_agent

DEFAULT_QUESTION = "We're 2 games out of a playoff spot. Where is our roster weakest, and what should we look for?"


def print_report(report: RosterReport) -> None:
    print(f"\n=== Analytics report: {report.team_id} ===")
    print(report.answer)
    print(f"\nWeakest area:   {report.weakest_area}")
    print("Evidence:")
    for line in report.evidence:
        print(f"  - {line}")
    print(f"Target profile: {report.target_profile}")
    if report.room_under_tax >= 0:
        tax_status = f"${report.room_under_tax:.1f}M under the tax line"
    else:
        tax_status = f"${-report.room_under_tax:.1f}M OVER the tax line"
    print(f"Payroll:        ${report.payroll:.1f}M  ({tax_status})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--debug", action="store_true", help="show tool calls and model messages")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set. Add your OpenRouter key to .env (see .env.example).")

    agent = build_analytics_agent(debug=args.debug)
    response = agent.run(args.question)

    if isinstance(response.content, RosterReport):
        print_report(response.content)
    else:
        # The model didn't return the schema; show what it did say.
        print(response.content)


if __name__ == "__main__":
    main()
