# Player Profiles

Sample players for the Front Office game, one for each way it can be played.
Each profile says how that person plays a week, what the game must give them,
which roadmap tasks already cover it, and where the roadmap leaves a gap. The
gaps are collected at the end as decisions for the roadmap. For a full season
played step by step, see `GAMEPLAY_EXAMPLE.md`.

Draft of Nov 12, 2026, brought up to date Nov 19 (after 1.4, G3, G8 and 1.5),
for review. Nothing here changes `ROADMAP.md` yet. Tasks marked "done" are
built; the rest are planned.

## 1. The Delegator: "Let my GM run it"

**Who:** Plays for the story, not the spreadsheets. Wants a season done in an
evening.

**A typical week:** Reads the GM briefing, approves or vetoes what the GM
proposes, presses **Sim it**. Rarely opens the roster screen. Gives one
standing order early ("win now, don't touch the quarterback") and expects it
to be remembered.

**Needs:** Short, trustworthy briefings; proposals that already fit the cap;
standing orders that last all season.

**Covered by:** G3 (briefing, done: every number checked against the league's
facts), 1.4 (GM team, done), 1.3 (Cap & Contracts, done), G4 (orders and
approvals), 4.2 (memory of standing orders).

**Gaps:**
- No way to say "sim to the deadline" or "auto-approve anything under $1M".
  Seventeen weeks of one click each, plus reading each briefing, may be slow
  for this player.

## 2. The Cap Hawk: "Show me the numbers"

**Who:** Knows the salary cap well and wants to build trades personally.

**A typical week:** Opens the Roster and Cap tabs first. Asks the front
office pointed questions ("who on Delta Bay has a safety under $4M with two
years left?"). Writes trades personally rather than waiting for the GM to
propose them, and expects a clear reason when one is illegal.

**Needs:** Full roster and contract tables; a way to write a specific trade;
exact rule reasons (1.2 gives these: "HAR's payroll would be $258.35M, $3.35M
over the $255.0M hard cap.").

**Covered by:** G2 (Roster and Cap tabs, done), 1.2 (rule checks, done), 1.3
and 1.4 (questions to the GM, done; the `salary-cap-rules` skill from 1.5
backs the answers), 2.1 (Trade Desk).

**Gaps:**
- The roadmap only has the owner *giving orders* that the GM turns into
  proposals (G4). The test bench's Trades tab already writes a trade by hand
  and checks it against 1.2, but the game has nothing like it.
- Players change teams only by trade, plus rookies in the G7 draft. There are
  no releases or free agents, so cap room can only be made by trading salary
  away.

## 3. The Contender: "Championship or bust"

**Who:** Plays to win, takes risks at the deadline, picks Hard difficulty.

**A typical week:** Pushes the GM for upgrades in weeks 6 to 9, overpays for
starters, calls the big moments personally, then rides the roster through
the playoffs.

**Needs:** Rival GMs that bargain hard (2.2, 4.5); a deadline that feels like
an event (2.3); games the owner can sway (G8); playoffs worth playing (G6).

**Covered by:** G8 (Call it, done: key moments or every snap), 2.2, 2.3, G5,
G6, 4.5.

**Gaps:**
- The briefing mock-up in the roadmap mentions trading "a mid-round pick", but
  the league has no draft picks to trade (G7 drafts rookies but doesn't make
  picks tradeable). Without picks, every trade must be players for players,
  which makes buying at the deadline hard.
- With one season and no future, overpaying has no cost. Contract years are
  in the data (`contract_years`) and the `player-valuation` skill (1.5) reads
  them, but nothing in the season depends on them.

## 4. The Rebuilder: "Get younger, win later"

**Who:** Enjoys long-term team building more than this season's record.

**A typical week:** Sells older veterans for younger players, ignores the
standings.

**Needs:** A reason to care about age and contract years; a game that lasts
longer than one season.

**Covered by:** Little. G7's rookie draft is the one young-player moment, but
the win condition is this season's playoffs and the game ends after G6.

**Gaps:**
- One season only; no second season, aging or contract expiry.
- One win condition. A rebuilder "loses" by design.

This profile may be out of scope for the course. It is listed so the decision
is made on purpose.

## 5. The Newcomer: "What's a hard cap?"

**Who:** Likes sports management games but doesn't know American football's
roster or cap rules.

**A typical week:** Reads every briefing closely, often asks the GM "why?",
tries a move, and learns from the rejection.

**Needs:** Plain-English explanations; rejections that teach the rule; a
forgiving difficulty.

**Covered by:** 1.2 (rejections name the rule and the numbers, done), G3
(briefings, done), 1.4 (asking the GM "why?", done), 1.5 (`salary-cap-rules`
skill, done), G8 (each play call says what it stops and what it's weak
against, done), 4.5 (Easy).

**Gaps:**
- "How to play" lives only in the README. The game itself has no help screen.
- No glossary of positions and ratings (what "S coverage 61" means).

## 6. The Offline Player: "No API key"

**Who:** A classmate or grader who clones the repo and runs it without an
OpenRouter key.

**A typical week:** Views the roster, plays the week's games (sim, watch or
call), checks the standings.

**Needs:** A full season that works with no key (a design rule), and a clear
message when an AI feature is unavailable.

**Covered by:** G2 (done: playable with no key; the briefing falls back to
plain notes, and Ask the front office says it needs a key), 3.1 and G8 (done:
no model calls), G7 (with no key every team takes the best prospect left).

**Gaps:**
- Orders and proposed moves (G4) still need a defined no-key behavior: shown
  with a "needs a key" message like Ask, or a simple rule-based GM.
- Rival GMs (G5) also act on their own; without a key, does the league just
  stay still?

## 7. The Demo Audience: "Show me in ten minutes"

**Who:** The instructor and class at the final presentation (task 5.2).

**A typical week:** Doesn't play. Watches a few weeks, a called drive and a
deadline trade, and wants to see the agent hierarchy working.

**Needs:** A predictable, seeded run; a fast way to reach the interesting part
(the deadline); the org-chart screen showing who did what (4.3); the cost of a
season (5.1).

**Covered by:** Seeded saves (G1, done), G8 (a called game is a good live
moment, done), the GM's answer showing which specialist said what (1.4,
done), 4.3, 5.1, 5.2.

**Gaps:**
- No "start at week 8" or prepared save for the demo; reaching the deadline
  live means playing seven weeks first. (The bench can sim weeks quickly,
  which helps prepare a save by hand.)

## Decisions for the roadmap

| # | Gap | Profiles | Possible change |
| - | --- | -------- | --------------- |
| 1 | Owner can't write a trade in the game | Cap Hawk | Add "propose my own trade" to G4, checked by 1.2 (the bench's Trades tab shows the pieces exist) |
| 2 | No releases or free agents | Cap Hawk, Contender | New task, or state that trades and the G7 draft are the only moves |
| 3 | No draft picks to trade | Contender | Make G7's picks tradeable in the Trade Desk (2.1), or drop picks from the mock-up |
| 4 | Contract years and age don't matter in one season | Contender, Rebuilder | Leave for later, or weigh them in proposals (the `player-valuation` skill already reads them) |
| 5 | One season, one win condition | Rebuilder | Mark as out of scope, or a stretch goal |
| 6 | No in-game help screen or glossary | Newcomer | Add to G2 (or to 4.3's polish week) |
| 7 | No-key behavior of G4 and G5 undefined | Offline | Add a line to G4 and G5, following G2's "needs a key" message |
| 8 | No fast-forward or auto-approve | Delegator, Demo | "Sim to week N" in the game; a demo save in 5.2 |
| 9 | The standalone rookie scale prices the Herons out of G7 | Every profile | Give G7 its own rookie scale, small enough to fit the Herons' $5.52M of cap space (see `GAMEPLAY_EXAMPLE.md`, assumption 3) |
