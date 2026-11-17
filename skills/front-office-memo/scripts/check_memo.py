#!/usr/bin/env python3
"""Check a memo to the owner against the facts it was written from, and the house style.

    check_memo.py --facts '{"record": "2-1", "cap_space": "$5.5M"}' \\
                  --headline "Herons 2-1" --text "We are 2-1.

    We have $5.5M of cap space."

Paragraphs in --text are separated by blank lines. --facts is JSON (or any text
holding the numbers). Prints JSON: numbers not in the facts, style problems, and
whether the memo is ready to send. The weekly briefing is checked the same way
(agents/memo.py).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agents import memo  # noqa: E402


def check(facts: str, text: str, headline: str = "") -> dict:
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    unknown = memo.unknown_numbers(f"{headline} {text}", facts)
    style = memo.style_problems(headline, paragraphs)
    return {"numbers_not_in_the_facts": unknown, "style_problems": style, "ready": not unknown and not style}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--facts", required=True, help="the facts the memo was written from, as JSON")
    parser.add_argument("--text", required=True, help="the memo's paragraphs, separated by blank lines")
    parser.add_argument("--headline", default="", help="the memo's headline, if it has one")
    args = parser.parse_args(argv)
    print(json.dumps(check(args.facts, args.text, args.headline), indent=2))


if __name__ == "__main__":
    main()
