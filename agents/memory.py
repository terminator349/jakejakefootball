"""The front office's memory (task 4.2).

The GM and its staff remember the season: the owner's orders, every move the GM
proposed and what the owner decided (in the owner's own words, when there are
any), the trades made and the offers answered, Scouting's reports, the weekly
briefings, and the GM's answers to the owner's questions.

Plain Python keeps it, and no model writes it. Almost all of it was already in
the save: orders and the GM's moves (G4), trade proposals (2.1), scouting
reports (4.1) and briefings (G3). This module reads them back into one timeline,
`timeline()`. The GM's answers to the owner's questions were the one thing not
kept, so they get a table of their own (gm_answers). Because the memory is the
save, it lasts from week to week and comes back when a saved game is loaded; a
new game starts with none.

Who remembers what. `recall()` picks what bears on the job, always keeping the
owner's decisions and the trades made, and `text()` writes it for a prompt:

    the GM answering a question   the season so far
    the GM's order search          the season, and everything about the order's positions and players
    the pro scouts                 each target's history (offers made for him, moves vetoed)
    the weekly briefing            what was decided since last week

Plain Python also holds the GM to the owner's past decisions: a trade the owner
vetoed is refused if the GM files it again (orders.check_move).
"""

import json
from pathlib import Path

from agents.league_db import connect

OUR_TEAM = "HAR"
RECALLED = 14       # entries a prompt gets, beyond the owner's decisions and the trades made
LONG = 320          # characters of a GM answer kept in the timeline

# Within a week: the briefing first, then questions and orders, then what came of them.
RANK = {"briefing": 0, "answer": 1, "order": 2, "scouting": 3, "proposed": 4, "approved": 4, "vetoed": 4,
        "void": 4, "our_offer": 5, "offer_to_us": 5, "trade": 5}  # offers and trades in the order they happened
# Kinds that are the owner's own decisions, or their results: always recalled.
DECISIONS = {"approved", "vetoed", "trade"}


def _names(db) -> dict[str, dict]:
    return {r["id"]: {"name": r["name"], "position": r["position"]}
            for r in db.execute("SELECT id, name, position FROM players")}


def _cities(db) -> dict[str, str]:
    return {r["id"]: r["city"] for r in db.execute("SELECT id, city FROM teams")}


def _who(ids: list[str], names: dict) -> str:
    people = [f"{names[i]['name']} ({names[i]['position']})" if i in names else i for i in ids]
    if not people:
        return "nobody"
    return people[0] if len(people) == 1 else ", ".join(people[:-1]) + " and " + people[-1]


def _quote(words: str | None) -> str:
    words = (words or "").strip()
    return f': "{words}"' if words else ""


def _entry(week: int, kind: str, text: str, players=(), teams=(), positions=(), owner_words=None) -> dict:
    return {"week": week, "kind": kind, "text": text, "players": list(players), "teams": list(teams),
            "positions": sorted(set(positions)), "owner_words": (owner_words or "").strip() or None}


def _orders(db) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM orders ORDER BY id"):
        terms = json.loads(r["terms"])
        state = "it stands" if r["status"] == "active" else "since cancelled"
        out.append(_entry(r["week"], "order", f'You gave order #{r["id"]}: "{r["text"]}" ({state}).',
                          players=terms.get("protected_player_ids", []), positions=terms.get("positions", []),
                          owner_words=r["text"]))
    return out


def _moves(db, names, cities) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM gm_proposals ORDER BY id"):
        sends, gets = json.loads(r["sends"]), json.loads(r["receives"])
        deal = f"sending {_who(sends, names)} to {cities[r['team_id']]} for {_who(gets, names)}"
        positions = [names[p]["position"] for p in gets if p in names]
        common = dict(players=sends + gets, teams=[r["team_id"]], positions=positions)
        if r["status"] == "waiting":
            out.append(_entry(r["week"], "proposed", f"I proposed {deal} (move #{r['id']}); it waits for you.",
                              **common))
        elif r["status"] == "approved":
            out.append(_entry(r["decided_week"] or r["week"], "approved",
                              f"You approved my move #{r['id']}, {deal}{_quote(r['owner_note'])}.",
                              owner_words=r["owner_note"], **common))
        elif r["status"] == "vetoed":
            out.append(_entry(r["decided_week"] or r["week"], "vetoed",
                              f"You vetoed my move #{r['id']}, {deal}{_quote(r['owner_note'])}.",
                              owner_words=r["owner_note"], **common))
        else:
            out.append(_entry(r["decided_week"] or r["week"], "void",
                              f"My move #{r['id']}, {deal}, went void: {r['owner_note'] or 'it no longer passed'}",
                              **common))
    return out


def _offers(db, names, cities) -> list[dict]:
    """Our offers and how they were answered, and the offers made to us."""
    out = []
    rows = db.execute("SELECT * FROM trade_proposals WHERE (from_team_id = ? OR to_team_id = ?) AND status != 'open' "
                      "ORDER BY id", (OUR_TEAM, OUR_TEAM)).fetchall()
    for r in rows:
        ours = r["from_team_id"] == OUR_TEAM
        other = r["to_team_id"] if ours else r["from_team_id"]
        city = cities[other]
        we_send, we_get = (json.loads(r["sends"]), json.loads(r["receives"])) if ours else \
            (json.loads(r["receives"]), json.loads(r["sends"]))
        got = f"{_who(we_get, names)} for {_who(we_send, names)}"
        positions = [names[p]["position"] for p in we_get + we_send if p in names]
        common = dict(players=we_send + we_get, teams=[other], positions=positions)
        week, status, said = r["decided_week"] or r["week"], r["status"], r["response"]
        if status == "accepted":
            text = (f"Trade made: {city} accepted our offer, so we got {got}." if ours else
                    f"Trade made: you accepted {city}'s {'counteroffer' if r['counter_of'] else 'offer'}, "
                    f"so we got {got}{_quote(said)}.")
            out.append(_entry(week, "trade", text, owner_words=None if ours else said, **common))
        elif ours:
            what = {"rejected": f"{city} turned down our offer of {got}{_quote(said)}.",
                    "countered": f"{city} countered our offer of {got}.",
                    "withdrawn": f"Our offer to {city} of {got} was withdrawn{_quote(said)}.",
                    "void": f"Our offer to {city} of {got} went void{_quote(said)}."}[status]
            out.append(_entry(week, "our_offer", what, **common))
        elif status == "rejected":
            out.append(_entry(week, "offer_to_us", f"You turned down {city}'s offer of {got}{_quote(said)}.",
                              owner_words=said, **common))
        elif status in ("withdrawn", "void"):
            out.append(_entry(week, "offer_to_us", f"{city}'s offer of {got} expired unanswered.", **common))
    return out


def _scouting(db) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM scouting_reports ORDER BY id"):
        targets = json.loads(r["targets"])
        best = [f"{t['name']} ({t['position']}, {t['team']}) {t['grade']}" for t in targets[:4]]
        text = f"Scouting reported on {', '.join(json.loads(r['positions']))}: {r['summary']}" + \
            (f" Graded: {'; '.join(best)}." if best else "")
        out.append(_entry(r["week"], "scouting", text, players=[t["player_id"] for t in targets],
                          teams=[t["team_id"] for t in targets], positions=json.loads(r["positions"])))
    return out


def _briefings(db) -> list[dict]:
    return [_entry(r["week"], "briefing", f"My briefing: {json.loads(r['briefing'])['headline']}")
            for r in db.execute("SELECT week, briefing FROM briefings ORDER BY week")]


def _answers(db) -> list[dict]:
    out = []
    for r in db.execute("SELECT * FROM gm_answers ORDER BY id"):
        answer = r["answer"] if len(r["answer"]) <= LONG else r["answer"][:LONG].rsplit(" ", 1)[0] + "..."
        rec = (r["recommendation"] or "").strip()
        text = f'You asked: "{r["question"]}" I answered: {answer}' + \
            (f" I recommended: {rec}" if rec.rstrip(".").lower() not in ("", "none") else "")
        out.append(_entry(r["week"], "answer", text, owner_words=r["question"]))
    return out


def timeline(db_file: Path | None = None) -> list[dict]:
    """Everything the front office remembers this season, oldest first."""
    db = connect(db_file)
    try:
        names, cities = _names(db), _cities(db)
        entries = (_orders(db) + _moves(db, names, cities) + _offers(db, names, cities) + _scouting(db)
                   + _briefings(db) + _answers(db))
    finally:
        db.close()
    return sorted(entries, key=lambda e: (e["week"], RANK[e["kind"]]))  # stable: each source keeps its order


def _about(entry: dict, positions, players) -> bool:
    return bool(set(entry["positions"]) & set(positions) or set(entry["players"]) & set(players))


def recall(db_file: Path | None = None, positions=(), players=(), limit: int = RECALLED,
           since_week: int | None = None) -> list[dict]:
    """What bears on a job, oldest first: the owner's decisions and the trades made, always;
    everything about the given positions or players; then the most recent of the rest, up to
    `limit` entries in all (the decisions always come, even past the limit)."""
    entries = [e for e in timeline(db_file) if since_week is None or e["week"] >= since_week]
    keep = {i for i, e in enumerate(entries) if e["kind"] in DECISIONS or e["kind"] == "offer_to_us"
            and e["owner_words"]}
    keep |= {i for i, e in enumerate(entries) if _about(e, positions, players)}
    for i in reversed(range(len(entries))):
        if len(keep) >= limit:
            break
        keep.add(i)
    return [entries[i] for i in sorted(keep)]


def text(entries: list[dict], week: int | None = None) -> str:
    """Memory as a prompt reads it: what happened, then the owner's questions in the order
    they were asked (a week's events aren't timed against each other, but questions are)."""
    head = "What you remember from this season" + (f" (it is week {week} now)" if week else "") + ":"
    if not entries:
        return head + " nothing yet; this is the start of the season."
    events = [e for e in entries if e["kind"] != "answer"]
    asked = [e for e in entries if e["kind"] == "answer"]
    out = [head, "(In these notes \"You\" is the owner and \"I\" is you, the GM.)"]
    out += [f"- Week {e['week']}: {e['text']}" for e in events]
    if asked:
        out.append("The owner's questions to you, oldest first (the last is the most recent):")
        out += [f"- Week {e['week']}: {e['text']}" for e in asked]
    return "\n".join(out)


def about_player(player_id: str, entries: list[dict]) -> list[str]:
    """The lines about one player, for the scouts."""
    return [f"Week {e['week']}: {e['text']}" for e in entries if player_id in e["players"]]


def since_last_week(week: int, db_file: Path | None = None) -> list[str]:
    """What was decided, traded, offered and scouted last week and so far this week, for the briefing."""
    return [f"Week {e['week']}: {e['text']}" for e in timeline(db_file)
            if e["week"] >= week - 1 and e["kind"] not in ("briefing", "answer", "proposed")]


def vetoed(team_id: str, we_send: list[str], we_get: list[str], db_file: Path | None = None) -> dict | None:
    """The owner's veto of this exact trade, if there was one: {week, note}."""
    db = connect(db_file)
    try:
        for r in db.execute("SELECT * FROM gm_proposals WHERE status = 'vetoed' AND team_id = ? ORDER BY id DESC",
                            (team_id,)):
            if (sorted(json.loads(r["sends"])), sorted(json.loads(r["receives"]))) == (sorted(we_send), sorted(we_get)):
                return {"week": r["decided_week"] or r["week"], "note": r["owner_note"] or ""}
        return None
    finally:
        db.close()


def remember_answer(question: str, answer: str, recommendation: str | None = None, consulted=(),
                    cost: float | None = None, db_file: Path | None = None) -> None:
    """Keep the GM's answer to one of the owner's questions."""
    db = connect(db_file)
    try:
        with db:
            week = db.execute("SELECT current_week FROM game").fetchone()[0]
            db.execute("INSERT INTO gm_answers (week, question, answer, recommendation, consulted, cost) "
                       "VALUES (?, ?, ?, ?, ?, ?)",
                       (week, question.strip(), answer.strip(), recommendation, json.dumps(list(consulted)), cost))
    finally:
        db.close()
