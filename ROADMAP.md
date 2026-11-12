# Front Office Roadmap

The build plan from the Front Office Build Schedule (Google Sheets), one row per
task. Fourteen weeks, from the week of Oct 26, 2026 to the week of Jan 25, 2027.
Task numbers match the chart; the README and code use the same numbers.

Status as of Nov 11, 2026 (week 3).

**Change on Nov 11: the project is now an interactive game.** The original
tasks keep their numbers and meaning, so earlier progress reports stay correct.
Six new game tasks use a `G` prefix (G1 - G6), and the season simulator (3.1)
moves up from W9 - W11 to W3 - W4, because the game loop needs it from the
start.

## The game

You are the owner of the Harbor City Herons. Each week of the 17-week season
your General Manager briefs you, you give orders, and the front office carries
them out against five rival AI GMs. Games are simulated from team ratings. You
win by making the playoffs, and then the championship, without ever going over
the hard cap.

### One week, as the player sees it

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
- **Seeded and repeatable.** The same save and seed give the same season, so
  tests and the demo are predictable.
- **Playable before the AI is finished.** Menus, standings and simulated games
  work with no API key. Each agent plugs into the loop as it is built.
- **Every move is legal and grounded.** The League Office rejects illegal moves
  and says why. No agent can invent a player.

## Schedule

| Week | Dates          | Tasks in progress                   |
| ---- | -------------- | ----------------------------------- |
| W1   | Oct 26 - Nov 1 | 0.1, 0.2 (done)                     |
| W2   | Nov 2 - Nov 8  | 1.1 (done)                          |
| W3   | Nov 9 - Nov 15 | 1.2, G1, 3.1                        |
| W4   | Nov 16 - 22    | 3.1, G2, 1.3                        |
| W5   | Nov 23 - 29    | 1.3, 1.4, G3                        |
| W6   | Nov 30 - Dec 6 | 1.5, 2.1                            |
| W7   | Dec 7 - 13     | 2.1, G4, 2.2                        |
| W8   | Dec 14 - 20    | 2.2, G5                             |
| W9   | Dec 21 - 27    | 2.3                                 |
| W10  | Dec 28 - Jan 3 | 3.2, G6                             |
| W11  | Jan 4 - 10     | 3.2, 4.2                            |
| W12  | Jan 11 - 17    | 4.1, 4.3, 4.5                       |
| W13  | Jan 18 - 24    | 4.4 (stretch), 5.1                  |
| W14  | Jan 25 - 31    | 5.1, 5.2                            |

Milestones: the game is **playable with no AI** at the end of W4 (G2), the GM
**briefs the owner** each week at the end of W5 (G3), and **trades work inside
the game** by the deadline task in W9 (2.3).

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

### 1.2 Rule checks: roster size, hard cap, trade deadline (W3)
The League Office rejects illegal moves: rosters outside the min/max size, any
move that puts a team over the hard cap, and trades after the deadline week.
The game relies on these checks: every move the owner approves goes through
them, and a rejected move shows the rule it broke.

### G1 Game state and save files (W3)
New SQLite tables for the current week, the 17-week schedule (each rival three
or four times), game results, standings and a log of every move. "New game"
copies the `league.json` seed into a fresh save; "Load game" continues one.

### 3.1 Season simulator (W3 - W4, moved up from W9 - W11)
Decides each game from team ratings with a seeded random number generator, and
updates results and standings. Plain Python, no model calls.

### G2 Terminal game loop (W4)
The weekly menu above: view roster, standings and cap, play the week, save and
quit. Fully playable with no API key, with no agent features yet.

### 1.3 Cap & Contracts agent (W4 - W5)
A specialist agent that reads payroll and contracts and says whether a move fits
under the cap, and what salary would have to go back to make it fit. In the
game, it checks every move before the GM brings it to the owner.

### 1.4 GM team: first agent-to-agent link (W5)
A General Manager agent leads Analytics and Cap & Contracts as an Agno team,
deciding which specialist to ask and combining their answers. In the game, the
GM is the one the owner talks to (menu option 1).

### G3 Weekly GM briefing (W5)
At the start of each week, the GM writes a short briefing: record, last week's
results, the biggest weakness and cap space, with every number from the league
data.

### 1.5 Skills: cap rules, player valuation, memos (W6)
Markdown know-how plus helper scripts in `skills/`: `salary-cap-rules`,
`player-valuation` and `front-office-memo`. The `front-office-memo` skill
shapes the weekly briefing.

## Phase 2: Trades in the game

### 2.1 Trade Desk MCP server (W6 - W7)
A second MCP server for proposing, evaluating and making trades, checked against
the League Office's rules.

### G4 Owner orders and approvals (W7)
The owner gives an order in plain words ("upgrade safety, stay under $5M").
The GM turns it into proposed moves, and the owner approves or vetoes each one
before anything goes to the Trade Desk.

### 2.2 Rival GM agents and negotiation skill (W7 - W8)
AI general managers for the other five teams, who accept, reject or counter our
offers, and a negotiation skill for our side.

### G5 Rival GMs act on their own (W8)
Rival GMs make offers to us and trade with each other between weeks, so the
league changes even when the owner does nothing.

### 2.3 Trade deadline in the game (W9)
The trade-deadline scenario becomes a game event: find the weakness, value
targets, negotiate with rival GMs and complete a legal trade. The GM warns the
owner in the weeks before, and the Trade Desk closes after week 9.

## Phase 3: The full season

### 3.2 Coaching and Medical agents (W10 - W11)
Specialists for depth charts and game plans (Coaching) and injuries and games
missed (Medical), reporting to the GM. The simulator adds injuries; Medical
reports them in the briefing, and Coaching resets the depth chart around them.

### G6 Playoffs and the end of the season (W10)
The top teams after week 17 play for the championship. The game ends with a
season summary: record, playoff result, moves made and final cap position.

## Phase 4: Hierarchy and polish

### 4.1 Scouting sub-team (W12)
A scouting team under the GM, adding a second level to the org chart. It finds
trade targets for the GM's proposals.

### 4.2 Memory (W11)
Agents remember past decisions, trades and reports. In the game, the GM
remembers the owner's standing orders and past decisions across weeks and saved
games.

### 4.3 Org-chart screen (W12)
A screen in the game showing the agent hierarchy and what each agent did this
week.

### 4.4 Real stats data (W13, stretch goal)
Load real player data in place of the generated league, if ahead of schedule.

### 4.5 Difficulty levels: easy, normal, hard (W12)
No longer a stretch goal, since a game needs it: chosen at "New game", it sets
how shrewdly rival GMs negotiate.

## Phase 5: Testing and submission

### 5.1 Integration testing and cost check (W13 - W14)
End-to-end tests of the full front office, including a scripted full-season
playthrough, plus a check of what one season played costs in model tokens.

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
