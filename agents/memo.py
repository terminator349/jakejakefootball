"""Checks for anything written to the owner (the front-office-memo skill, task 1.5).

Two kinds of check, shared by the weekly briefing (agents/briefing.py) and the
skill's own script (skills/front-office-memo/scripts/check_memo.py):

- `unknown_numbers`: every number in the text must appear in the facts it was
  written from. A number that isn't there was made up or worked out.
- `style_problems`: the house style's measurable rules - a headline of at most
  12 words, two to four paragraphs of at most three sentences, no hype words.
"""

import json
import re

NUMBER = re.compile(r"\d+(?:\.\d+)?")
HEADLINE_WORDS = 12
PARAGRAPHS = (2, 4)
SENTENCES = 3
HYPE = ("elite", "dominant", "massive", "huge", "incredible", "must-win", "statement game")
# A sentence ends at . ! or ? before a space and a capital, a quote or a number,
# but not after a "$5.5M."-style figure's decimal point or an initial like "A.J.".
SENTENCE_END = re.compile(r"(?<![A-Z]\.[A-Z]\.)(?<=[.!?])\s+(?=[A-Z\"'(0-9])")


def numbers(text: str) -> list[str]:
    """Every number in the text, in order, written one way whatever the commas or
    trailing zeros: "1,200" and "1200" match, as do "5.50" and "5.5"."""
    return [n.rstrip("0").rstrip(".") if "." in n else n.lstrip("0") or "0"
            for n in NUMBER.findall(text.replace(",", ""))]


def unknown_numbers(text: str, facts) -> list[str]:
    """Numbers in the text that aren't in the facts, in the order they first appear.
    `facts` is anything JSON can hold, or a string."""
    allowed = set(numbers(facts if isinstance(facts, str) else json.dumps(facts)))
    return list(dict.fromkeys(n for n in numbers(text) if n not in allowed))


def sentences(paragraph: str) -> list[str]:
    return [s for s in SENTENCE_END.split(paragraph.strip()) if s]


def hype_words(text: str) -> list[str]:
    """The hype words in the text, from the house style's list."""
    return [word for word in HYPE if re.search(rf"\b{re.escape(word)}\b", text.lower())]


def style_problems(headline: str, paragraphs: list[str]) -> list[str]:
    problems = []
    if len(headline.split()) > HEADLINE_WORDS:
        problems.append(f"the headline has {len(headline.split())} words; at most {HEADLINE_WORDS}")
    low, high = PARAGRAPHS
    if not low <= len(paragraphs) <= high:
        problems.append(f"{len(paragraphs)} paragraphs; write {low} to {high}")
    for i, paragraph in enumerate(paragraphs, 1):
        if len(sentences(paragraph)) > SENTENCES:
            problems.append(f"paragraph {i} has {len(sentences(paragraph))} sentences; at most {SENTENCES}")
    if hype := hype_words(" ".join([headline, *paragraphs])):
        problems.append(f"hype words: {', '.join(hype)}")
    return problems
