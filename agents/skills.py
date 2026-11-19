"""The front office's skills (task 1.5): markdown know-how plus helper scripts in skills/.

Each skill is a folder in the Agent Skills format Agno reads: a SKILL.md with a
name and a description, scripts/ and references/. An agent given skills sees
each one's name and description in its system prompt and loads the rest when a
question calls for it, with Agno's get_skill_instructions, get_skill_reference
and get_skill_script tools (the last can run a script and read its output).

    salary-cap-rules   the hard cap, roster limits and deadline; cap_check.py
    player-valuation   market value, surplus and age; value_player.py
    roster-impact      how ratings feed the simulator's units; unit_impact.py
    front-office-memo  the house style for the owner; check_memo.py
    negotiation        how every GM scores a trade, and building an offer they'll take; appraise.py (2.2)

Who has which:

    Analytics          player-valuation, roster-impact
    Cap & Contracts    salary-cap-rules
    the GM             front-office-memo, always on: its rules are in its instructions
    the briefing       front-office-memo, always on, and its checks (agents/memo.py)
    the GM's search    negotiation (G4, 2.2): proposing trades the other side will accept
"""

import re
from pathlib import Path

from agno.skills import LocalSkills, Skills

SKILLS_DIR = Path(__file__).parent.parent / "skills"
ALL = ("salary-cap-rules", "player-valuation", "roster-impact", "front-office-memo", "negotiation")


def load(*names: str) -> Skills:
    """The named skills, checked against the Agent Skills format as they load."""
    unknown = [n for n in names if n not in ALL]
    if unknown:
        raise ValueError(f"Unknown skills {unknown}. Valid: {list(ALL)}")
    return Skills(loaders=[LocalSkills(str(SKILLS_DIR / name)) for name in names])


def section(name: str, heading: str) -> str:
    """One `## heading` section of a skill's SKILL.md, without the heading, for an
    agent that should always follow it rather than load it when it decides to."""
    instructions = load(name).get_skill(name).instructions
    match = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", instructions, re.M | re.S)
    if match is None:
        raise ValueError(f"The {name} skill has no section {heading!r}.")
    return match.group(1).strip()
