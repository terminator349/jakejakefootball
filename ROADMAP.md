# Front Office Roadmap

The build plan from the Front Office Build Schedule (Google Sheets), one row per
task. Fourteen weeks, from the week of Oct 26, 2026 to the week of Jan 25, 2027.
Task numbers match the chart; the README and code use the same numbers.

Status as of Nov 3, 2026.

| Week | Dates          | Tasks in progress                   |
| ---- | -------------- | ----------------------------------- |
| W1   | Oct 26 - Nov 1 | 0.1, 0.2                            |
| W2   | Nov 2 - Nov 8  | 1.1                                 |
| W3   | Nov 9 - Nov 15 | 1.2, 1.3                            |
| W4   | Nov 16 - 22    | 1.3, 1.4, 1.5                       |
| W5   | Nov 23 - 29    | 1.5                                 |
| W6   | Nov 30 - Dec 6 | 2.1                                 |
| W7   | Dec 7 - 13     | 2.1, 2.2                            |
| W8   | Dec 14 - 20    | 2.2, 2.3                            |
| W9   | Dec 21 - 27    | 2.3, 3.1                            |
| W10  | Dec 28 - Jan 3 | 3.1, 3.2                            |
| W11  | Jan 4 - 10     | 3.1, 3.2                            |
| W12  | Jan 11 - 17    | 3.2, 4.1, 4.2, 4.3                  |
| W13  | Jan 18 - 24    | 4.1 - 4.5, 5.1                      |
| W14  | Jan 25 - 31    | 5.1, 5.2                            |

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

## Phase 1: Foundation

### 1.1 League Office MCP server: SQLite rosters, contracts (W2) - In progress
- Done: `servers/league_office.py` serves the four tools over MCP (stdio) as
  read-only tools, and the Analytics agent reads the league only through it.
- To do: store rosters and contracts in SQLite instead of `data/league.json`,
  with the tools giving the same results.

### 1.2 Rule checks: roster size, hard cap, trade deadline (W3)
The League Office rejects illegal moves: rosters outside the min/max size, any
move that puts a team over the hard cap, and trades after the deadline week.

### 1.3 Cap & Contracts agent (W3 - W4)
A specialist agent that reads payroll and contracts and says whether a move fits
under the cap, and what salary would have to go back to make it fit.

### 1.4 GM team: first agent-to-agent link (W4)
A General Manager agent leads Analytics and Cap & Contracts as an Agno team,
deciding which specialist to ask and combining their answers.

### 1.5 Skills: cap rules, player valuation, memos (W4 - W5)
Markdown know-how plus helper scripts in `skills/`: `salary-cap-rules`,
`player-valuation` and `front-office-memo`.

## Phase 2: Negotiation

### 2.1 Trade Desk MCP server (W6 - W7)
A second MCP server for proposing, evaluating and making trades, checked against
the League Office's rules.

### 2.2 Rival GM agents and negotiation skill (W7 - W8)
AI general managers for the other five teams, who accept, reject or counter our
offers, and a negotiation skill for our side.

### 2.3 Trade-deadline scenario end to end (W8 - W9)
One full run: find the weakness, value targets, negotiate with rival GMs and
complete a legal trade before the deadline.

## Phase 3: Season loop

### 3.1 Season simulator (W9 - W11)
A 17-game season in plain Python, deciding games from team ratings.

### 3.2 Coaching and Medical agents (W10 - W12)
Specialists for depth charts and game plans (Coaching) and injuries and games
missed (Medical), reporting to the GM during the season.

## Phase 4: Hierarchy and polish

### 4.1 Scouting sub-team (W12 - W13)
A scouting team under the GM, adding a second level to the org chart.

### 4.2 Memory (W12 - W13)
Agents remember past decisions, trades and reports across runs.

### 4.3 Org-chart dashboard (W12 - W13)
A view of the agent hierarchy and what each agent did.

### 4.4 Real stats data (W13, stretch goal)
Load real player data in place of the generated league, if ahead of schedule.

### 4.5 Difficulty levels: easy, normal, hard (W13, stretch goal)
Rival GMs that negotiate more or less shrewdly.

## Phase 5: Testing and submission

### 5.1 Integration testing and cost check (W13 - W14)
End-to-end tests of the full front office, plus a check of what a season costs
in model tokens.

### 5.2 Demo script, backup recording, slides (W14)
The final demo, a recording in case the live demo fails, and presentation slides.

## Throughout
The proposal's standing goals apply to every task: every decision grounded in
league data with no invented players, every move legal under the cap, and
automated tests that check the data and tools without an API key.

## Notes
An earlier draft of the schedule marked a Thanksgiving break (Nov 25 - 29), a
winter break (Dec 19 - Jan 3) and demos at the end of each phase. The current
chart does not, and it schedules 2.3, 3.1 and 3.2 during the old winter break.
