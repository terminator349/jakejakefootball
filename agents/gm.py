"""The General Manager: the first agent-to-agent link (task 1.4).

The GM leads the front office's specialists as an Agno Team in coordinate mode:
it reads the owner's question, decides which specialists to ask, writes each one
a specific task, and combines their answers into one reply for the owner. It has
no data tools of its own, so every number it gives comes from a specialist.

    Owner -> GM -> Analytics        (League Office: rosters, ratings, rankings)
                -> Cap & Contracts  (League Office: payroll, cap fit, trade checks)
                -> Draft            (Draft Day results and the draft class)

Each specialist keeps its own tools and structured report. Analytics and Cap &
Contracts each start their own League Office server, with their own slice of
its tools, pointed at the same league. Specialists see what the others said
earlier in the run, so Cap & Contracts can price the player Analytics found.
"""

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from agno.agent import Agent
from agno.team import Team, TeamMode
from pydantic import BaseModel, Field

from agents import analytics, cap_contracts, draft_desk
from agents.analytics import specialist_model
from agents.tools import list_teams

# The same model as the specialists for now (DeepSeek V4.1 Flash): coordinating
# three members is a few short calls, and the specialists do the reading.
GM_MODEL = analytics.SPECIALIST_MODEL

# Delegations per question. A question usually needs one or two specialists,
# sometimes a follow-up; this stops a coordination loop.
DELEGATION_LIMIT = 6

OUR_TEAM = "HAR"

PARSER_PROMPT = (
    "The user message is the general manager of an American football team answering a question "
    "from the team's owner, after consulting the front office's specialists. Fill the output fields "
    "from that answer only: copy its facts and numbers, invent nothing, and do not reply to these "
    "instructions. `answer` is the GM's own direct answer to the owner, in two to four sentences."
)


class GMReport(BaseModel):
    """What the owner reads. Payroll and cap space are replaced with the league's own values."""

    team_id: str = Field(description="Three-letter id of the team the answer is mostly about, e.g. 'HAR'.")
    answer: str = Field(description="The GM's direct answer to the owner, two to four sentences.")
    recommendation: str = Field(description="What the GM recommends the owner do next, one or two sentences. "
                                "'None' if the question didn't call for one.")
    evidence: list[str] = Field(description="The specialists' specific numbers behind the answer.")
    payroll: float = Field(description="Our (HAR) total payroll in $M.")
    cap_space: float = Field(description="Our (HAR) salary cap minus payroll, in $M. Negative means over the cap.")


def ground_report(report: GMReport) -> GMReport:
    """The owner always sees our own payroll and cap space, from the league, not the model:
    whatever the question was about, that's the money they have to work with. The team
    the answer is about is turned into its id, or ours if the league doesn't know it
    (e.g. a question only about Draft Day)."""
    named = analytics.ground_report(report)
    team_id = named.team_id if named is not report else OUR_TEAM
    ours = analytics.ground_report(report.model_copy(update={"team_id": OUR_TEAM}))
    return ours.model_copy(update={"team_id": team_id})


def build_gm_team(analytics_office, cap_office, draft_file: Path = draft_desk.RESULTS_FILE,
                  debug: bool = False) -> Team:
    """The GM and its three specialists. Pass connected League Office tools for the two
    League Office specialists (see `front_office()`, which opens them)."""
    return Team(
        name="General Manager",
        role="General manager of the Harbor City Herons, the owner's one point of contact.",
        mode=TeamMode.coordinate,
        model=specialist_model(),
        members=[
            analytics.build_analytics_agent(analytics_office, debug=debug),
            cap_contracts.build_cap_contracts_agent(cap_office, debug=debug),
            draft_desk.build_draft_desk(draft_file, debug=debug),
        ],
        instructions=[
            "You are the general manager of the Harbor City Herons (team id HAR) in a six-team American "
            "football league. The owner asks you questions; you answer them by consulting your specialists, "
            "because you have no data of your own.",
            "Analytics: roster strengths and weaknesses, how our players and units compare with the league, "
            "and what kind of player would fix a weakness.",
            "Cap & Contracts: payroll, cap space, whether a signing or trade fits under the hard cap, and "
            "how much salary would have to go back to make it fit.",
            "Draft: Draft Day, the separate draft of real NFL players - its order, each team's picks, rookie "
            "salaries and who went undrafted. Its rosters are not the league's rosters.",
            "Ask only the specialists the question needs. When it needs more than one, ask them in order and "
            "pass on what you learned: e.g. ask Analytics for the weakness and a target salary, then ask Cap & "
            "Contracts whether that exact salary fits our cap.",
            "Give each specialist one complete, specific task: the team ids, positions, players and salaries "
            "involved. Ask each specialist at most twice.",
            "Never ask a specialist about something outside its area. If the right specialist can't answer, "
            "tell the owner what you couldn't find out rather than asking someone else.",
            "Use only the numbers your specialists report; never invent players, ratings or salaries. Trust "
            "Cap & Contracts on money and Analytics on talent.",
            "The salary cap is $255M per team and hard: a move that goes over it is illegal, not taxed.",
            "Then answer the owner directly in plain words, say what you recommend, and list the specialists' "
            "key numbers as evidence. Say 'we' and 'our' only for the Herons; name every other team, and keep "
            "each team's players and numbers with that team.",
        ],
        tool_call_limit=DELEGATION_LIMIT,
        # Later specialists see what earlier ones said, so a cap check can use the
        # salary Analytics found without the GM copying every number across.
        share_member_interactions=True,
        store_member_responses=True,
        output_schema=GMReport,
        # The same parser-model pattern as the specialists (see agents/analytics.py).
        parser_model=specialist_model(),
        parser_model_prompt=PARSER_PROMPT,
        debug_mode=debug,
    )


@asynccontextmanager
async def front_office(db_file: Path | None = None, draft_file: Path = draft_desk.RESULTS_FILE,
                       debug: bool = False):
    """Start the League Office servers the specialists need and yield the GM's team.
    Pass a save file to serve that game instead of the default league."""
    async with analytics.league_office_tools(db_file) as analytics_office, \
            cap_contracts.league_office_tools(db_file) as cap_office:
        yield build_gm_team(analytics_office, cap_office, draft_file, debug)


# ---- Reading a run ----------------------------------------------------------------

GROUNDERS = {analytics.RosterReport: analytics.ground_report, cap_contracts.CapReport: cap_contracts.ground_report}


def tool_calls(run) -> list[dict]:
    calls = []
    for call in run.tools or []:
        result = call.result if isinstance(call.result, str) else json.dumps(call.result, default=str)
        calls.append({"tool": call.tool_name, "args": call.tool_args, "error": bool(call.tool_call_error),
                      "result": result})
    return calls


def _content(content):
    """A specialist's report as plain data, grounded in the league where it can be."""
    if isinstance(content, BaseModel):
        ground = GROUNDERS.get(type(content))
        return (ground(content) if ground else content).model_dump()
    return None if content is None else str(content)


def _usage(metrics) -> dict:
    return {"input_tokens": getattr(metrics, "input_tokens", None),
            "output_tokens": getattr(metrics, "output_tokens", None), "cost": getattr(metrics, "cost", None)}


def gm_text(response) -> str | None:
    """The GM's own final answer, as it wrote it, before the parser model read it."""
    for message in reversed(getattr(response, "messages", None) or []):
        if message.role == "assistant" and not message.tool_calls and isinstance(message.content, str) \
                and message.content.strip():
            return message.content
    return None


def summarize(response, seconds: float | None = None, extra_usage: list[dict] = ()) -> dict:
    """Everything the owner (and the test bench) can see about one question: the GM's
    report, each task the GM gave a specialist, and what each specialist did and said.
    `extra_usage` adds model calls made outside the team run (a second parse)."""
    delegations = [{"member": c["args"].get("member_id"), "task": c["args"].get("task")}
                   for c in tool_calls(response) if c["tool"] == "delegate_task_to_member"]
    specialists = [{"name": getattr(r, "agent_name", None) or "?", "report": _content(r.content),
                    "tool_calls": tool_calls(r), **_usage(r.metrics)}
                   for r in response.member_responses or []]
    content = response.content
    report = ground_report(content).model_dump() if isinstance(content, GMReport) else None
    # A team run's metrics are the GM's own calls; the specialists' are on their runs.
    runs = [_usage(response.metrics), *specialists, *extra_usage]

    def total(key):
        values = [r[key] for r in runs if r[key] is not None]
        return sum(values) if values else None

    return {"report": report, "text": None if report else (gm_text(response) or str(content)),
            "consulted": list(dict.fromkeys(s["name"] for s in specialists)),
            "delegations": delegations, "specialists": specialists,
            "seconds": None if seconds is None else round(seconds, 1), "model": response.model,
            "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
            "cost": total("cost")}


# DeepSeek's structured output now and then runs on into whitespace until it hits the
# token limit, and the GM's report is lost though the GM's answer is fine. Parse the
# GM's own text again (no tools, so a plain structured-output call) before giving up.
PARSE_RETRIES = 2


async def reparse(text: str, usage: list[dict]) -> GMReport | None:
    parser = Agent(model=specialist_model(), instructions=[PARSER_PROMPT], output_schema=GMReport)
    for _ in range(PARSE_RETRIES):
        run = await parser.arun(text)
        usage.append(_usage(run.metrics))
        if isinstance(run.content, GMReport):
            return run.content
    return None


async def ask(question: str, db_file: Path | None = None, debug: bool = False) -> dict:
    """Ask the GM one question and return `summarize()` of the run."""
    question = question.strip()
    if not question:
        raise ValueError("Type a question for the GM.")
    started = time.perf_counter()
    usage = []
    async with front_office(db_file, debug=debug) as gm:
        response = await gm.arun(question)
    if not isinstance(response.content, GMReport) and (text := gm_text(response)):
        response.content = await reparse(text, usage) or response.content
    return summarize(response, time.perf_counter() - started, usage)
