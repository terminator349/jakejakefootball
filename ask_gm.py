"""Ask the General Manager, who consults Analytics, Cap & Contracts and Draft (task 1.4).

    python ask_gm.py
    python ask_gm.py "Where are we weakest, and can we afford to fix it?"
    python ask_gm.py --debug      # print every delegation, tool call and model message
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from agents import gm

DEFAULT_QUESTION = ("We're 1 game out of a playoff spot. Where is our roster weakest, "
                    "and can we afford a player who fixes it?")


def money(m: float) -> str:
    return f"${m:.1f}M" if m >= 0 else f"-${-m:.1f}M"


def print_run(run: dict) -> None:
    for d in run["delegations"]:
        print(f"\nGM -> {d['member']}: {d['task']}")
    for s in run["specialists"]:
        report = s["report"]
        answer = report.get("answer") if isinstance(report, dict) else report
        tools = ", ".join(c["tool"] for c in s["tool_calls"]) or "no tools"
        print(f"\n--- {s['name']} ({tools}) ---\n{answer}")
    report = run["report"]
    if report is None:
        print(f"\n=== GM ===\n{run['text']}")
        return
    print(f"\n=== GM, after asking {', '.join(run['consulted']) or 'no one'} ===")
    print(report["answer"])
    print(f"\nRecommendation: {report['recommendation']}")
    print("Evidence:")
    for line in report["evidence"]:
        print(f"  - {line}")
    print(f"Our payroll: {money(report['payroll'])}  (cap space {money(report['cap_space'])})")
    cost = f", ${run['cost']:.4f}" if run["cost"] is not None else ""
    print(f"\n{run['seconds']}s{cost}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--debug", action="store_true", help="show delegations, tool calls and model messages")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set. Add your OpenRouter key to .env (see .env.example).")
    print_run(asyncio.run(gm.ask(args.question, debug=args.debug)))


if __name__ == "__main__":
    main()
