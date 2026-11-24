# Front Office Roadmap

The build plan from the Front Office Build Schedule (Google Sheets), one row per
task. Fourteen weeks, from the week of Oct 26, 2026 to the week of Jan 25, 2027.
Task numbers match the chart; the README and code use the same numbers.

Status as of Nov 19, 2026 (week 4).

**Change on Nov 11: the project is now an interactive game.** The original
tasks keep their numbers and meaning, so earlier progress reports stay correct.
Six new game tasks use a `G` prefix (G1 - G6), and the season simulator (3.1)
moves up from W9 - W11 to W3 - W4, because the game loop needs it from the
start.

**Change on Nov 12: a rookie draft joins the plan (G7).** Each new game opens
with a draft run by a new Draft agent, built alongside the W4 - W5 tasks.

**Also Nov 12: the owner can call the plays (G8).** The season simulator (3.1)
plays every game snap by snap instead of picking a final score, and runs to
W5. Each week the owner can sim a game, watch it drive by drive, or call the
Herons' plays. The game loop (G2) is now a web page, built from the test bench
(`ui/`), instead of a terminal menu.

## The game

You are the owner of the Harbor City Herons. Each week of the 17-week season
your General Manager briefs you, you give orders, and the front office carries
them out against five rival AI GMs. Games are simulated from team ratings. You
win by making the playoffs, and then the championship, without ever going over
the hard cap.

### One week, as the player sees it

The game is a web page (G2); this sketch shows what a week contains, not its
layout.

```
=== Week 6: Herons 3-2, 3rd of 6 ===  Cap space: $5.5M   Trade deadline: week 9

GM briefing
  We lost 17-24 at Iron Falls. Safety coverage still ranks 6th of 6.
  Mesa Verde will move a starting safety ($4.1M) for a mid-round pick.

  1. Ask the front office a question
  2. Give an order          ("upgrade safety, stay under $5M")
  3. Review proposed moves  (1 waiting: trade with MES)
  4. Roster, standings, cap
  5. Play this week's games
  6. Save and quit
>
```

### Design rules

- **The owner gives orders; the agents do the work.** You set priorities and
  approve or veto moves. The GM decides how to carry out your orders.
- **Plain Python owns the rules and the simulation.** Cap checks, roster
  limits, the trade deadline, schedules and game results are code, not model
  output. The agents only make decisions and write text.
- **Seeded and repeatable.** The same save and seed give the same season, and
  the same play calls give the same game, so tests and the demo are
  predictable.
- **Playable before the AI is finished.** Menus, standings and simulated games
  work with no API key. Each agent plugs into the loop as it is built.
- **Every move is legal and grounded.** The League Office rejects illegal moves
  and says why. No agent can invent a player.

## Schedule

| Week | Dates          | Tasks in progress                      |
| ---- | -------------- | -------------------------------------- |
| W1   | Oct 26 - Nov 1 | 0.1, 0.2 (done)                        |
| W2   | Nov 2 - Nov 8  | 1.1 (done)                             |
| W3   | Nov 9 - Nov 15 | 1.2, G1 (done), 3.1                    |
| W4   | Nov 16 - 22    | 3.1, G2, G8 (done), 1.3, G7            |
| W5   | Nov 23 - 29    | 3.1, 1.3, 1.4, G3 (done early), G7     |
| W6   | Nov 30 - Dec 6 | 1.5, 2.1 (done early), G8 (done early) |
| W7   | Dec 7 - 13     | 2.1, G4, 2.2 (done early), G8 (done early) |
| W8   | Dec 14 - 20    | 2.2, G5 (done early)                   |
| W9   | Dec 21 - 27    | 2.3 (done early)                       |
| W10  | Dec 28 - Jan 3 | 3.2 (done early), G6 (done early)      |
| W11  | Jan 4 - 10     | 3.2 (done early), 4.2 (done early)     |
| W12  | Jan 11 - 17    | 4.1 (done early), 4.3, 4.5             |
| W13  | Jan 18 - 24    | 4.4 (stretch, done early), 5.1         |
| W14  | Jan 25 - 31    | 5.1, 5.2                               |

Milestones: the game is **playable with no AI** at the end of W4 (G2), the GM
**briefs the owner** each week at the end of W5 (G3), the owner **calls plays
at key moments** by the end of W7 (G8), and **trades work inside the game** by
the deadline task in W9 (2.3).

## Phase 0: Setup and first agent

### 0.1 Project setup and league data (W1) - Done
Virtual environment, project layout, and `data/generate_league.py`: a fictional
league of six teams with 48 players each, a 17-game season and a hard $255M cap.
Our team, the Harbor City Herons (`HAR`), has $5.5M of cap space and a planted
weakness in the secondary.

### 0.2 Analytics agent and roster tools (W1) - Done
The Analytics agent (DeepSeek V4.1 Flash through OpenRouter) answers roster
questions with four tools (`list_teams`, `get_roster`, `compare_to_league`,
`get_league_rules`) and returns a structured `RosterReport`. The league was
converted from basketball to American football in this step.

## Phase 1: Foundation and a playable season

### 1.1 League Office MCP server: SQLite rosters, contracts (W2) - Done
`servers/league_office.py` serves the four tools over MCP (stdio) as read-only
tools, and the Analytics agent reads the league only through it. Rosters and
contracts live in SQLite (`data/league.db`, built from the `data/league.json`
seed by `agents/league_db.py`), and the tools give the same results as before.

### 1.2 Rule checks: roster size, hard cap, trade deadline (W3) - Done
The League Office rejects illegal moves: rosters outside the min/max size, any
move that puts a team over the hard cap, and trades after the deadline week.
The game relies on these checks: every move the owner approves goes through
them, and a rejected move shows the rule it broke.

### G1 Game state and save files (W3) - Done
New SQLite tables for the current week, the 17-week schedule (each rival three
or four times), game results, standings and a log of every move. "New game"
copies the `league.json` seed into a fresh save; "Load game" continues one.

### 3.1 Season simulator: play by play (W3 - W5, moved up from W9 - W11) - Done
Plays each game one snap at a time, in plain Python with a seeded random number
generator and no model calls. The game state is the down, distance, yard line,
clock, score and timeouts. Each snap, the offense picks a play (inside or
outside run, short or deep pass, play action, screen, punt, field goal) and the
defense a call (base, blitz, cover 2, deep zone, run stuff). The ratings of the
players on the field decide the result: a deep pass sets QB arm strength and WR
speed against CB and safety coverage, an inside run sets RB rushing and OL run
blocking against DL run defense and LB tackling. Plain-Python tendencies, by
situation, call plays for any team the owner isn't coaching.

Every play goes into a play log, and player game stats build box scores and
season stats. Results and standings update as in G1. Tests tune the engine over
many seeded games: about 20 - 24 points and 60 - 65 plays per team on average,
with the better-rated team winning more often.

Built in stages: "Sim it" (a game in one step) by W4 so G2 is playable, then
"Watch it" (drive by drive, from the play log) in W5.

Progress, Nov 12: "Sim it" is done and tuned (see the README).

Progress, Nov 17: "Watch it" is done: drive summaries from the play log, and
drive-by-drive playback in the test bench. Late in a half the AI now manages
the clock (hurry-up, timeouts, spikes, a last field goal, kneels). 3.1 is done;
G2 builds the real game screen on it.

### G2 Web game loop (W4) - Done
The week above as a web page, grown from the test bench in `ui/`: roster,
standings, schedule and cap, play the week, save and quit. Fully playable with
no API key, with no agent features yet.

Done Nov 17: the game is at `/` and the test bench moved to `/bench`, sharing
`ui/static/`. Each week shows plain-Python front-office notes until the G3
briefing, and the menu's agent options say which task brings them.

### G7 Rookie draft and the Draft agent (W4 - W5, added Nov 12)
Before week 1 of a new game, the six teams hold a rookie draft. A seeded pool of
prospects is generated with the league, and the draft order comes from a seeded
lottery, since there is no previous season to rank teams by. There are at most
five rounds, because rosters start at 48 of a 53-player maximum. The Draft
agent scouts the pool and recommends picks. The owner makes the Herons' picks
on its advice, and the agent picks for the rival teams until the rival GMs
(2.2) take over. With no API key, every team takes the best prospect left.

The draft is the league's first way to add a player rather than trade one, so
the League Office gets a signing check beside the 1.2 rules: a pick joins only
if the roster stays at or under the maximum and the payroll under the hard cap,
on a rookie contract set by draft position. Each pick goes into the move log
(G1), and the save keeps the prospect pool and the draft order.

### G8 Call the plays (W6 - W7, added Nov 12) - Done
Before each Herons game the owner chooses how to play it: **Sim it**, **Watch
it** drive by drive, or **Call it**. Calling comes in two levels: *key moments*
(the game sims until a 4th down, the red zone, the two-minute drill or
overtime, then hands over the call) and *every snap*. The game-day screen shows
the score, clock, down and distance, the ball on a field strip, the play-call
buttons and a play-by-play log. Rival games are always simmed with the same
engine. Key-moment calling is the target; calling every snap comes after it,
time permitting.

Done Nov 17, both levels, ahead of W6. A game being called is saved as its
seed plus the owner's calls and rebuilt by replaying them, so it survives Save &
quit and a restart. Offensive calls show how our players match up for each
play; defensive calls show what each one stops and the opponent's best
matchups. The owner can switch levels or sim the rest at any time. Coaching's
suggested call (2.1) is still to come.

### 1.3 Cap & Contracts agent (W4 - W5) - Done
A specialist agent that reads payroll and contracts and says whether a move fits
under the cap, and what salary would have to go back to make it fit. In the
game, it checks every move before the GM brings it to the owner.
`check_cap_fit` and `validate_cap_compliance` join the League Office's tools
(still read-only), and `agents/cap_contracts.py` answers with a structured
`CapReport`, the same DeepSeek V4.1 Flash + parser-model pattern as Analytics.
The hard cap is $255M per team.

The standalone draft simulator's own $220M cap was retired in the same step:
`draft/roster_rules.SALARY_CAP` now reads the main league's $255M rule, and
the Draft GM agent (`draft/agent.py`) carries the same `check_cap_fit`/
`validate_cap_compliance` tools as Cap & Contracts - `draft/tools.py` binds
them to the draft's in-memory teams, but both call the same
`agents.tools.cap_math`, so there is one cap rule and one cap tool
implementation for the whole project.

### 1.4 GM team: first agent-to-agent link (W5) - Done
A General Manager agent leads Analytics and Cap & Contracts as an Agno team,
deciding which specialist to ask and combining their answers. In the game, the
GM is the one the owner talks to (menu option 1).

Done Nov 17, ahead of W5. The GM leads every agent built so far: Analytics,
Cap & Contracts, and a new Draft desk that reads Draft Day's results, since the
Draft GM agent itself only makes picks. Specialists see each other's answers
within a question, so a cap check can use the salary Analytics found. In the
game, **Ask the front office** on the week screen goes to the GM, and the
answer shows who was asked and what each said; the bench's Agents tab runs the
GM or either specialist on its own.

### G3 Weekly GM briefing (W5) - Done
At the start of each week, the GM writes a short briefing: record, last week's
results, the biggest weakness and cap space, with every number from the league
data.

Done Nov 17, ahead of W5. Plain Python gathers the week's facts; the GM writes
from them, and a check rejects any number that isn't in them (a failed draft
goes back once with the numbers named, then the plain notes stand in). Each
week's briefing is kept in the save. The front-office-memo skill (1.5) shapes
its style.

### 1.5 Skills: cap rules, player valuation, memos (W6) - Done
Markdown know-how plus helper scripts in `skills/`: `salary-cap-rules`,
`player-valuation` and `front-office-memo`. The `front-office-memo` skill
shapes the weekly briefing.

Done Nov 17, ahead of W6. There are four skills, not three. `roster-impact`
was added because every veteran here is paid about fairly for his overall, so
finding a fix means knowing which ratings a unit uses and how far one player
moves it. Each skill's script runs on the league's own code: the cap math, the
league rules and the simulator's `build_lineup`. Analytics has
player-valuation and roster-impact, and Cap & Contracts has salary-cap-rules;
each loads a skill when a question calls for it. The memo skill is always on
for the GM and the briefing. The briefing also checks its style, sending a
draft back for a long headline, too many sentences or hype words.

## Phase 2: Trades in the game

### 2.1 Trade Desk MCP server (W6 - W7) - Done
A second MCP server for proposing, evaluating and making trades, checked against
the League Office's rules.

Done Nov 19, ahead of W6. `servers/trade_desk.py` serves eight tools: evaluate a
trade, propose it, and accept, reject or counter an offer, plus withdrawing an
offer, listing proposals and the trade log. A proposal is checked against the
1.2 rules when it's made and again in the transaction that moves the players,
and a completed trade voids other open offers for the same players. The
evaluation gives each side's market value (the player-valuation formula),
payroll change, starters and simulator unit changes, so agents quote numbers
rather than compute them. Proposals are kept in the save (schema version 5).
G4 and 2.2 are its first clients.

### G4 Owner orders and approvals (W7) - Done
The owner gives an order in plain words ("upgrade safety, stay under $5M").
The GM turns it into proposed moves, and the owner approves or vetoes each one
before anything goes to the Trade Desk.

Done Nov 19, ahead of W7. The GM reads an order into terms (positions,
salary limits, players not to trade) that plain Python enforces: every move
it files is checked against the 1.2 rules, every standing order and the
order's limits, and checked again when the owner approves it. An approved
move goes on the Trade Desk as the Herons' offer. Orders stand all season, so
part of 4.2's "standing orders" is done here; remembering past decisions is
still 4.2's. The rival GMs (2.2) answer them.

### 2.2 Rival GM agents and negotiation skill (W7 - W8) - Done
AI general managers for the other five teams, who accept, reject or counter our
offers, and a negotiation skill for our side.

Done Nov 19, ahead of W7. Every GM scores a trade by one formula (market value
gained, half the salary taken on, and unit points), which the Trade Desk's
evaluation now gives for each side. Plain Python works out the score and up to
three counteroffers, and the rival's GM chooses within those limits and writes
the reply; without a key the rules answer. The negotiation skill explains the
formula to our GM's search (G4), so its proposals clear the other side's margin.

### G5 Rival GMs act on their own (W8) - Done
Rival GMs make offers to us and trade with each other between weeks, so the
league changes even when the owner does nothing.

Done Nov 19 with 2.2. After each week, plain Python and the season's seed
decide whether a rival trades with another (only if both sides score it above
their margin) or makes us an offer, which lasts a week and shows under Offers
to us with our GM's read on it. A seeded season has about two rival trades
and two or three offers to us.

### 2.3 Trade deadline in the game (W9) - Done
The trade-deadline scenario becomes a game event: find the weakness, value
targets, negotiate with rival GMs and complete a legal trade. The GM warns the
owner in the weeks before, and the Trade Desk closes after week 9.

Done Nov 19, ahead of W9. From two weeks out the week screen counts down, and
the briefing's facts carry the warning and, once we've traded, what our trades
did to the unit (rating and rank before and now, and the gap to the team
above). "Work the deadline" saves an order for the biggest weakness and has the
GM's search work it, or a plain-Python search without a key. The owner
approves, the rival's GM answers, and a counter can be accepted. Past the
deadline, waiting moves are void and the offers close.

## Phase 3: The full season

### 3.2 Coaching and Medical agents (W10 - W11) - Done early (built W4, Nov 19)
Built ahead of schedule, alongside 1.3/G2/G7, at the owner's request. Two new
specialists, `agents/coaching.py` and `agents/medical.py`, read the same League
Office server with their own tool slices, the same DeepSeek + parser-model
pattern as Analytics and Cap & Contracts.

The simulator (3.1) now rolls a small, independent chance (its own random
stream, so the 3.1 tuning is untouched) that the player central to a run, sack,
scramble, catch or interception is hurt and leaves the game - about 4-5 games
missed per team per season. `agents/league_db.py` gained an `injuries` table
(who, since which week, back which week) and a `depth_chart` table (an
explicit order Coaching can set at one position, ignored automatically the
moment it no longer names exactly that roster there, e.g. after a trade).
Four new League Office tools: `get_depth_chart`/`set_depth_chart` (the only
one that isn't read-only) and `get_injury_report`/`get_team_tendencies` (each
play type's share of an opponent's calls so far this season, from the 3.1 play
log). A hurt starter is replaced by the next healthy player down the chart
automatically, in `build_lineup`/`Lineup.starters`; a position with no healthy
backup (K, P) plays its one option hurt rather than fielding nobody.

Medical reports who's out and how much longer, and which position it leaves
thinnest; Coaching sets the depth chart around that and plans the next game
around the opponent's tendencies. Built before this merge caught up with 1.4,
G3, G8 and 1.5, already landed on `main` in the meantime - so neither agent was
wired into the GM's Team at first.

Done Nov 24: both are now members of the GM's Team (`agents/gm.py`), alongside
Analytics, Cap & Contracts and Scouting - the owner can ask the GM about an
injury or the depth chart and it delegates to Medical or Coaching like any
other specialist. Call It (G8) still doesn't ask Coaching for a suggested call
during a live game; that remains open.

```powershell
python check_coaching.py                                              # game plan + depth chart for our team
python check_coaching.py "Our starting safety is hurt. Who starts instead?"
python check_medical.py                                               # who's hurt, and how it thins us out
pytest tests/test_coaching.py tests/test_medical.py                    # agent checks, no API key needed
```

Done when: a hurt player sits out exactly as many games as the simulator
rolled and the next man up starts automatically; a depth chart change sticks
until changed again, and a trade or cut silently retires a stale one; and
`get_team_tendencies` reflects only games actually played.

### G6 Playoffs and the end of the season (W10)
The top teams after week 17 play for the championship. The game ends with a
season summary: record, playoff result, moves made and final cap position.

Done Nov 19, ahead of W10. The top four by the standings play semifinals in
week 18 (1 v 4, 2 v 3) and the final in week 19, at the better seed. Playoff
games are simmed, watched or called like any other but don't count in the
standings, and they play overtime until someone scores. Week 20 shows the
season summary: record and standing, how far we went, trades, orders, the GM's
moves and rivals' offers, the final cap position and our season leaders.

## Phase 4: Hierarchy and polish

### 4.1 Scouting sub-team (W12) - Done early (Nov 19)
A scouting team under the GM, adding a second level to the org chart. It finds
trade targets for the GM's proposals, and the Draft agent (G7) moves into it.

Done Nov 19, ahead of W12. A Scouting director (an Agno team under the GM) hands
each position to an offense or defense pro scout. Plain Python lists the players
who would start for us and the one-for-one offer their team should take; the
scouts grade them A, B or C with the new scouting skill. Orders and the deadline
go through Scouting first, and the GM files moves from its report. The Draft desk
(1.4) reports through Scouting; G7's draft agent will join it there.

### 4.2 Memory (W11) - Done early (Nov 24)
Agents remember past decisions, trades and reports. In the game, the GM
remembers the owner's standing orders and past decisions across weeks and saved
games.

Done Nov 24, ahead of W11. Plain Python reads the save back into one timeline
(orders, the GM's moves and the owner's decisions with notes, trades, offers,
scouting reports, briefings, and the GM's answers, now kept). The GM's
questions, its order search, the scouts and the briefing each get what bears
on their job, and a trade the owner vetoed is refused if filed again. Memory
lives in the save, so it lasts across weeks and through save and load.

### 4.3 Org-chart screen (W12) - Done early (built W5, Nov 24)
A screen in the game showing the agent hierarchy and what each agent did this
week. `agents/org_chart.py` builds the hierarchy straight from the GM's own
Team (`agents/gm.py`), so it can't fall out of sync, and reads each
specialist's weekly line from what's already in the save - no model call, no
API key needed. See `README.md`'s 4.3 entry for the full story.

### 4.4 Real stats data (W13, stretch goal) - Done early (Nov 24)
Load real player data in place of the generated league, if ahead of schedule.

Done Nov 24, ahead of W13. "New game" offers "Real 2025 players": the six
franchises filled with real NFL players from nflverse's public 2025 data, each
rated from his real stats on the generated league's scale, so the simulator
stays balanced. The generated league stays the default. Salaries are estimated
from ratings, because nflverse's contract data ends in 2022.

### 4.5 Difficulty levels: easy, normal, hard (W12)
No longer a stretch goal, since a game needs it: chosen at "New game", it sets
how shrewdly rival GMs negotiate and how well rival teams call plays. The
negotiation margins for easy, normal and hard are already in
`agents/negotiation.py` (2.2); 4.5 stores the choice in the save.

## Phase 5: Testing and submission

### 5.1 Integration testing and cost check (W13 - W14)
End-to-end tests of the full front office, including a scripted full-season
playthrough, plus a check of what one season played costs in model tokens,
including Coaching's game-day advice.

### 5.2 Demo script, backup recording, slides (W14)
The demo is a live game: a few weeks of play and a trade at the deadline, with
a recording of a full season as the backup, plus presentation slides.

## Throughout
The proposal's standing goals apply to every task: every decision grounded in
league data with no invented players, every move legal under the cap, and
automated tests that check the data, tools and game rules without an API key.

## Notes
An earlier draft of the schedule marked a Thanksgiving break (Nov 25 - 29), a
winter break (Dec 19 - Jan 3) and demos at the end of each phase. The current
chart does not, and it schedules 2.3, 3.2 and G6 during the old winter break.
