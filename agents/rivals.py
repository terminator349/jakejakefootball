"""The rival GMs (tasks 2.2 and G5): the other five teams' front offices.

2.2: a rival answers the offers made to it, accepting, rejecting or countering.
G5: between weeks, the rivals act on their own: they trade with each other and
make offers to us, so the league changes even when the owner does nothing.

Plain Python owns every number and every limit. A rival scores a trade with the
same formula every team uses (agents/negotiation.py), and the counteroffers it
may make are worked out here: one more player from the team that offered,
chosen so the trade then scores enough for the rival and is legal. With an API
key, the rival's GM makes the call inside those limits and writes the reply,
in its team's own voice:

    accept   only if the trade scores at least its margin, less a little latitude
    counter  only with one of the options worked out here
    reject   always allowed

Its decision is then carried out on the Trade Desk (2.1), which checks the
league rules again. Without a key, or if the model's answer breaks those
limits, the rules decide on their own: accept at the margin, else counter with
the best option, else reject.

Between weeks everything is plain Python and seeded by the season's seed and
the week, so the same save and the same moves give the same league. The
rivals then answer any of our offers still open, take back their own offers to
us from an earlier week, and, before the deadline, may make one trade between
themselves and one offer to us.
"""

import json
import random
from pathlib import Path
from typing import Literal

from agno.agent import Agent
from pydantic import BaseModel, Field

from agents import negotiation, orders, rules
from agents import trade_desk as desk
from agents.league_db import connect, load_league

OUR_TEAM = "HAR"
COUNTER_OPTIONS = 3
LATITUDE = 0.5          # how far below its margin a rival's GM may still say yes
TRY_CHANCE = 0.35       # each week, the chance each rival looks for a trade with another rival
OFFER_CHANCE = 0.4      # each week, the chance a rival makes us an offer
TARGETS_TRIED = 6       # players a rival looks at for each of its two weakest positions
OUR_FLOOR = -1.0        # a rival's offer to us must look at least this good from our side

# Each rival front office's character, for the voice of its GM's replies.
PERSONAS = {
    "MES": "the Mesa Verde Coyotes. You want to win now: you'll pay for a starter, and you talk like it.",
    "IRN": "the Iron Falls Foundry. You're patient builders: you like young players and fair contracts, and you're plain-spoken.",
    "LAK": "the Lakeshore Loons. You trade on the numbers and say so, briefly.",
    "SUM": "the Summit Sherpas. You're deep and careful: you protect your depth and ask for a lot.",
    "DEL": "the Delta Bay Gators. You're aggressive and friendly, and you like a deal that gets done.",
}


# ---- Scoring and counteroffers (plain Python) ---------------------------------------------

def _fits(league: dict, team: str, sends: list[str], gets: list[str], by_id: dict) -> bool:
    """Roster size and the hard cap for one team after a trade, from the league in memory."""
    rules_ = league["rules"]
    roster = [p for p in league["players"] if p["team_id"] == team]
    size = len(roster) - len(sends) + len(gets)
    payroll = sum(p["salary"] for p in roster) - sum(by_id[p]["salary"] for p in sends) \
        + sum(by_id[p]["salary"] for p in gets)
    return rules_["roster_min"] <= size <= rules_["roster_max"] and payroll <= rules_["salary_cap"] + 1e-9


def _legal(league: dict, a: str, a_sends: list[str], b: str, b_sends: list[str], by_id: dict) -> bool:
    return _fits(league, a, a_sends, b_sends, by_id) and _fits(league, b, b_sends, a_sends, by_id)


def _scores(league: dict, a: str, a_sends: list[str], b: str, b_sends: list[str]) -> tuple[dict, dict]:
    return (negotiation.appraise(desk._side(league, a, a_sends, b_sends)),
            negotiation.appraise(desk._side(league, b, b_sends, a_sends)))


def _card(p: dict) -> dict:
    return {"id": p["id"], "name": p["name"], "position": p["position"], "overall": p["overall"],
            "salary": p["salary"], "years_left": p["contract_years"]}


def counter_options(league: dict, proposer: str, proposer_sends: list[str], rival: str,
                    rival_sends: list[str], limit: int = COUNTER_OPTIONS) -> list[dict]:
    """Counteroffers the rival may make: the same trade plus one more of the proposer's
    players, legal and scoring at least the rival's margin. Asks that still leave the
    proposer better off come first, and the smallest asks first among those."""
    by_id = {p["id"]: p for p in league["players"]}
    needed = negotiation.margin()
    options = []
    for p in league["players"]:
        if p["team_id"] != proposer or p["id"] in proposer_sends:
            continue
        sends = proposer_sends + [p["id"]]
        if not _legal(league, proposer, sends, rival, rival_sends, by_id):
            continue
        theirs, ours = _scores(league, proposer, sends, rival, rival_sends)
        if ours["score"] >= needed:
            options.append({"add": _card(p), "rival_score": ours["score"], "proposer_score": theirs["score"]})
    options.sort(key=lambda o: (o["proposer_score"] < 0, o["rival_score"]))
    return options[:limit]


def policy(appraisal: dict, options: list[dict]) -> tuple[str, int | None]:
    """What the rules decide on their own: accept at the margin, else the best counter, else no."""
    if appraisal["score"] >= appraisal["margin"]:
        return "accept", None
    if appraisal["verdict"] == "counter" and options:
        return "counter", 0
    return "reject", None


def policy_message(decision: str, option: dict | None) -> str:
    if decision == "accept":
        return "Deal."
    if decision == "counter":
        add = option["add"]
        return f"Close. Add {add['name']} ({add['position']}) and you have a deal."
    return "That doesn't work for us: it costs us more than it gives us."


# ---- The rival's GM (a model, inside those limits) -------------------------------------------

class RivalDecision(BaseModel):
    decision: Literal["accept", "reject", "counter"] = Field(description="Your answer to the offer.")
    option: int | None = Field(description="For a counter, the number of the counteroffer you choose "
                                           "(1, 2 or 3). Null otherwise.")
    message: str = Field(description="One or two sentences to the other team's GM, in your own voice. "
                                     "Name only players and numbers given to you.")


def build_rival_gm(team_id: str, debug: bool = False) -> Agent:
    from agents.analytics import specialist_model
    return Agent(
        name=f"{team_id} GM", model=specialist_model(), output_schema=RivalDecision, debug_mode=debug,
        instructions=[
            f"You are the general manager of {PERSONAS[team_id]}",
            "Another team has offered you a trade. You get what the trade does for your team, the score your "
            "front office puts on it, and the answers you may give. Choose one, and write the other GM a short "
            "reply in your own voice.",
            "You may accept only if accepting is listed as allowed. You may counter only with one of the listed "
            "counteroffers, by its number. You may always reject.",
            "Use only the players and numbers in the message. Don't promise anything beyond this trade.",
            "Write like a GM on the phone: talk about the players, by full name, and what your team needs. Never mention "
            "the answer's number, your front office's score or margin, or unit names with underscores.",
        ])


def _side_text(side: dict, appraisal: dict) -> str:
    def players(cards):
        return ", ".join(f"{p['name']} ({p['position']}, {p['overall']} overall, ${p['salary']:.2f}M, "
                         f"{p['years_left']} yrs)" for p in cards) or "nobody"
    units = ", ".join(f"{u['unit']} {u['change']:+.2f}" for u in side["unit_changes"][:5]) or "none"
    return (f"You get: {players(side['gets'])}\nYou give: {players(side['gives'])}\n"
            f"Your payroll changes by ${side['salary_change']:+.2f}M. Your units: {units}.\n"
            f"Your front office's score: {appraisal['score']:+.2f} (you accept at {appraisal['margin']:+.2f}).")


def decision_prompt(offer: dict, side: dict, appraisal: dict, options: list[dict], may_accept: bool) -> str:
    lines = [f"{offer['from_team_id']} offers you a trade."]
    if offer["note"]:
        lines.append(f"Their note: \"{offer['note']}\"")
    lines += [_side_text(side, appraisal), "", "Answers you may give:",
              "- accept" + ("" if may_accept else " (NOT allowed: it doesn't score enough)"), "- reject"]
    for i, o in enumerate(options, 1):
        add = o["add"]
        lines.append(f"- counter {i}: ask for {add['name']} ({add['position']}, {add['overall']} overall, "
                     f"${add['salary']:.2f}M) as well; your score would be {o['rival_score']:+.2f}")
    if not options:
        lines.append("- (no counteroffer works)")
    return "\n".join(lines)


async def _model_decision(agent: Agent, prompt: str, may_accept: bool, options: list[dict]):
    run = await agent.arun(prompt)
    usage = orders._usage(run)
    d = run.content
    if not isinstance(d, RivalDecision) or not d.message.strip():
        return None, usage
    if d.decision == "accept" and not may_accept:
        return None, usage
    if d.decision == "counter":
        if not d.option or not 1 <= d.option <= len(options):
            return None, usage
        return ("counter", d.option - 1, d.message.strip()), usage
    return (d.decision, None, d.message.strip()), usage


# ---- Answering an offer (2.2) ----------------------------------------------------------------

def _prepare(proposal_id: int, db_file: Path | None) -> dict:
    """Everything a rival weighs before answering an open offer made to it."""
    offer = desk.proposal(proposal_id, db_file)
    rival, proposer = offer["to_team_id"], offer["from_team_id"]
    if rival == OUR_TEAM:
        raise orders.OrderError(f"Proposal #{proposal_id} was made to us: the owner answers it.")
    if offer["status"] != "open":
        raise orders.OrderError(f"Proposal #{proposal_id} is {offer['status']}, not open.")
    ctx = {"offer": offer, "rival": rival, "proposer": proposer,
           "sends": [p["id"] for p in offer["sends"]],          # what the proposer gives
           "receives": [p["id"] for p in offer["receives"]]}    # what the rival gives
    if offer["rules_now"]["legal"]:
        league = load_league(db_file)
        ctx["side"] = desk._side(league, rival, ctx["receives"], ctx["sends"])
        ctx["appraisal"] = negotiation.appraise(ctx["side"])
        ctx["options"] = counter_options(league, proposer, ctx["sends"], rival, ctx["receives"])
    return ctx


def _carry_out(ctx: dict, decision: str, index: int | None, message: str | None, by: str,
               cost: float | None, db_file: Path | None) -> dict:
    pid, rival = ctx["offer"]["id"], ctx["rival"]
    out = {"proposal_id": pid, "team_id": rival, "by": by, "cost": cost, "appraisal": ctx.get("appraisal")}
    if "appraisal" not in ctx:  # the league changed since it was offered
        message = "It breaks the league rules now: " + " ".join(
            v["message"] for v in ctx["offer"]["rules_now"]["violations"])
        desk.respond(pid, rival, "reject", message, db_file)
        return {**out, "decision": "reject", "message": message, "offer": desk.proposal(pid, db_file)}
    option = ctx["options"][index] if index is not None else None
    message = message or policy_message(decision, option)
    if decision == "counter":
        made = desk.counter(pid, rival, ctx["receives"], ctx["sends"] + [option["add"]["id"]], message, db_file)
        out["counter"] = made.get("proposal")
        if not made["proposed"]:  # the league changed under us: say no instead
            desk.respond(pid, rival, "reject", message, db_file)
            decision = "reject"
    else:
        out["trade"] = desk.respond(pid, rival, decision, message, db_file).get("trade")
    return {**out, "decision": decision, "message": message, "offer": desk.proposal(pid, db_file)}


def answer_by_rules(proposal_id: int, db_file: Path | None = None) -> dict:
    """The rival answers by the rules alone: no model, the same answer every time."""
    ctx = _prepare(proposal_id, db_file)
    decision, index = policy(ctx["appraisal"], ctx["options"]) if "appraisal" in ctx else ("reject", None)
    return _carry_out(ctx, decision, index, None, "rules", None, db_file)


async def answer_offer(proposal_id: int, db_file: Path | None = None, use_model: bool = True,
                       agent: Agent | None = None) -> dict:
    """The rival an open offer was made to answers it, and the answer is carried out on
    the Trade Desk. With `use_model`, the rival's GM decides within the limits and writes
    the reply; if its answer breaks them, the rules decide."""
    ctx = _prepare(proposal_id, db_file)
    if not use_model or "appraisal" not in ctx:
        decision, index = policy(ctx["appraisal"], ctx["options"]) if "appraisal" in ctx else ("reject", None)
        return _carry_out(ctx, decision, index, None, "rules", None, db_file)
    appraisal, options = ctx["appraisal"], ctx["options"]
    may_accept = appraisal["score"] >= appraisal["margin"] - LATITUDE
    made, usage = await _model_decision(agent or build_rival_gm(ctx["rival"]),
                                        decision_prompt(ctx["offer"], ctx["side"], appraisal, options, may_accept),
                                        may_accept, options)
    if made is None:
        decision, index = policy(appraisal, options)
        return _carry_out(ctx, decision, index, None, "rules", usage["cost"], db_file)
    decision, index, message = made
    return _carry_out(ctx, decision, index, message, "model", usage["cost"], db_file)


# ---- Offers to us: the owner answers ------------------------------------------------------

def _protected(db_file: Path | None) -> dict[str, dict]:
    return {pid: o for o in orders.orders("active", db_file) for pid in o["terms"]["protected_player_ids"]}


def offers_to_us(db_file: Path | None = None) -> list[dict]:
    """Open offers to the Herons, each with what it does for us and our GM's read on it."""
    out = []
    protected = _protected(db_file)
    for offer in desk.proposals(OUR_TEAM, "open", db_file):
        if offer["to_team_id"] != OUR_TEAM:
            continue
        we_send = [p["id"] for p in offer["receives"]]
        we_get = [p["id"] for p in offer["sends"]]
        evaluation = desk.evaluate(rules.Trade(OUR_TEAM, we_send, offer["from_team_id"], we_get), db_file)
        item = {**offer, "legal_now": evaluation["legal"],
                "problems": [v["message"] for v in evaluation["rules"]["violations"]]}
        if "teams" in evaluation:
            ours = evaluation["teams"][OUR_TEAM]
            item["evaluation"] = summary = orders._summary(evaluation)
            names = {p["id"]: p["name"] for p in load_league(db_file)["players"]}
            for key in ("new_starters", "benched", "starters_lost"):
                summary[key] = [{"id": p, "name": names.get(p, p)} for p in summary[key]]
            item["appraisal"] = ours["appraisal"]
            clashes = [f"{p['name']} ({p['id']}) is protected by your order #{protected[p['id']]['id']} "
                       f"(\"{protected[p['id']]['text']}\")." for p in ours["gives"] if p["id"] in protected]
            item["advice"] = advise(ours["appraisal"], clashes, evaluation["legal"])
            item["clashes"] = clashes
        out.append(item)
    return out


def advise(appraisal: dict, clashes: list[str], legal: bool) -> str:
    """Our GM's read on an offer, by the same measure every team uses (the negotiation skill)."""
    if not legal:
        return "It breaks the league rules now, so it can't go through."
    score = appraisal["score"]
    read = (f"By the league's measure it's worth {score:+.2f} to us"
            + (": I'd take it." if score >= appraisal["margin"] and not clashes else
               "; it's close to even." if abs(score) < appraisal["margin"] else
               ": it costs us more than it gives." if score < 0 else "."))
    if clashes:
        read += " But it breaks your orders: " + " ".join(clashes) + " I'd say no unless you've changed your mind."
    return read


def accept_offer(proposal_id: int, note: str = "", db_file: Path | None = None) -> dict:
    """The owner accepts an offer made to us: the trade is made if the rules still pass."""
    return desk.respond(proposal_id, OUR_TEAM, "accept", note, db_file)


def reject_offer(proposal_id: int, note: str = "", db_file: Path | None = None) -> dict:
    return desk.respond(proposal_id, OUR_TEAM, "reject", note, db_file)


# ---- Between weeks (G5) ------------------------------------------------------------------

def _season(db_file: Path | None) -> tuple[int, int]:
    db = connect(db_file)
    try:
        return tuple(db.execute("SELECT current_week, seed FROM game").fetchone())
    finally:
        db.close()


def _weakest_positions(league: dict, team: str, n: int = 2) -> list[str]:
    starters = league["rules"]["starters_per_position"]

    def avg(team_id, pos):
        best = sorted((p["overall"] for p in league["players"] if p["team_id"] == team_id and p["position"] == pos),
                      reverse=True)[:starters[pos]]
        return sum(best) / len(best)
    teams = [t["id"] for t in league["teams"]]
    gaps = {pos: avg(team, pos) - sum(avg(t, pos) for t in teams) / len(teams) for pos in starters}
    return sorted(gaps, key=gaps.get)[:n]


def _targets(league: dict, buyer: str, position: str, sellers: list[str]) -> list[dict]:
    """Players at a position on the sellers' teams who would start for the buyer."""
    n = league["rules"]["starters_per_position"][position]
    ours = sorted((p["overall"] for p in league["players"] if p["team_id"] == buyer and p["position"] == position),
                  reverse=True)
    worst_starter = ours[n - 1] if len(ours) >= n else 0
    found = [p for p in league["players"] if p["team_id"] in sellers and p["position"] == position
             and p["overall"] > worst_starter]
    return sorted(found, key=lambda p: -p["overall"])[:TARGETS_TRIED]


def _package(league: dict, buyer: str, seller: str, target: dict, seller_floor: float, needed: float):
    """The buyer's best single player to send for the target: the buyer scores it at least
    `needed`, the seller at least `seller_floor`, and both rosters stay legal."""
    by_id = {p["id"]: p for p in league["players"]}
    best = None
    for p in league["players"]:
        if p["team_id"] != buyer or not _legal(league, buyer, [p["id"]], seller, [target["id"]], by_id):
            continue
        mine, theirs = _scores(league, buyer, [p["id"]], seller, [target["id"]])
        if mine["score"] >= needed and theirs["score"] >= seller_floor:
            key = theirs["score"]  # the most attractive offer the buyer can still win
            if best is None or key > best[0]:
                best = (key, p, mine["score"], theirs["score"])
    return best


def between_weeks(db_file: Path | None = None) -> dict:
    """What the rivals do once a week is over, after the week has advanced. Returns the news."""
    week, seed = _season(db_file)
    deadline = load_league(db_file)["rules"]["trade_deadline_week"]
    rng = random.Random(f"{seed}-rivals-{week}")
    news = []

    # Our offers still open get an answer from the rules (the owner usually got one at once).
    for offer in desk.proposals(None, "open", db_file):
        if offer["from_team_id"] == OUR_TEAM:
            result = answer_by_rules(offer["id"], db_file)
            news.append(f"{_team_name(load_league(db_file), result['team_id'])} answered our offer "
                        f"#{offer['id']}: {result['decision']}.")
    # Rivals take back their offers to us from an earlier week.
    for offer in desk.proposals(OUR_TEAM, "open", db_file):
        if offer["to_team_id"] == OUR_TEAM and offer["week"] < week:
            desk.withdraw(offer["id"], offer["from_team_id"], db_file,
                          reason=f"The offer expired at the end of week {offer['week']}.")
    if week > deadline:
        return {"week": week, "news": news}

    league = load_league(db_file)
    rivals = [t["id"] for t in league["teams"] if t["id"] != OUR_TEAM]

    # One trade between rivals, at most.
    order = rivals[:]
    rng.shuffle(order)
    for buyer in order:
        if rng.random() >= TRY_CHANCE:
            continue
        made = None
        for position in _weakest_positions(league, buyer):
            for target in _targets(league, buyer, position, [t for t in rivals if t != buyer]):
                # Between rivals, both sides need only their margin: a deal both teams like.
                if (found := _package(league, buyer, target["team_id"], target, negotiation.margin(),
                                      negotiation.margin())):
                    made = (target, found)
                    break
            if made:
                break
        if made:
            target, (_, player, _, _) = made
            offered = desk.propose(buyer, [player["id"]], target["team_id"], [target["id"]],
                                   f"{buyer} needs a {target['position']}.", db_file)
            if offered["proposed"]:
                result = desk.respond(offered["proposal"]["id"], target["team_id"], "accept", "Deal.", db_file)
                if result["accepted"]:
                    news.append(f"{_team_name(league, buyer)} traded {player['name']} ({player['position']}) to "
                                f"{_team_name(league, target['team_id'])} for {target['name']} ({target['position']}).")
                    league = load_league(db_file)
                    break

    # One offer to us, at most, and never twice for the same player from the same team.
    asked = {(o["from_team_id"], p["id"]) for o in desk.proposals(OUR_TEAM, "all", db_file)
             if o["to_team_id"] == OUR_TEAM for p in o["receives"]}
    if rng.random() < OFFER_CHANCE:
        order = rivals[:]
        rng.shuffle(order)
        for buyer in order:
            found = None
            for position in _weakest_positions(league, buyer):
                for target in _targets(league, buyer, position, [OUR_TEAM]):
                    if (buyer, target["id"]) in asked:
                        continue  # we've turned him down (or let the offer go) once this season
                    # An offer to us: the rival wants to win it, and it must look worth a look to us.
                    if (found := _package(league, buyer, OUR_TEAM, target, OUR_FLOOR,
                                          negotiation.margin() + negotiation.OFFER_PREMIUM)):
                        break
                if found:
                    break
            if found:
                _, player, _, _ = found
                note = (f"{_team_name(league, buyer)} would like {target['name']} for {player['name']} "
                        f"({player['position']}, {player['overall']} overall, ${player['salary']:.2f}M).")
                offered = desk.propose(buyer, [player["id"]], OUR_TEAM, [target["id"]], note, db_file)
                if offered["proposed"]:
                    news.append(f"{_team_name(league, buyer)} made us an offer for {target['name']}.")
                break
    return {"week": week, "news": news}


def _team_name(league: dict, team_id: str) -> str:
    team = next(t for t in league["teams"] if t["id"] == team_id)
    return team["city"]


def news(week: int, db_file: Path | None = None) -> list[str]:
    """Trades between other teams made this week, for the week screen."""
    league = load_league(db_file)
    by_id = {p["id"]: p for p in league["players"]}
    lines = []
    for move in rules.move_log(db_file):
        teams = {p["from_team_id"] for p in move["players"]} | {p["to_team_id"] for p in move["players"]}
        if move["week"] != week or OUR_TEAM in teams:
            continue
        a, b = sorted(teams)
        a_out = [p for p in move["players"] if p["from_team_id"] == a]
        b_out = [p for p in move["players"] if p["from_team_id"] == b]

        def names(ps):
            return ", ".join(f"{p['name']} ({by_id[p['player_id']]['position']})" for p in ps) or "nobody"
        lines.append(f"{_team_name(league, a)} traded {names(a_out)} to {_team_name(league, b)} for {names(b_out)}.")
    return lines
