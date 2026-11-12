# Front Office

An AI-run American football front office, played as an interactive terminal
game. You are the owner; each week your General Manager briefs you, you give
orders, and a hierarchy of agents scouts, trades and manages the roster against
rival AI general managers. See `ROADMAP.md` for the game design and the build
plan; a "How to play" section arrives with the game loop (task G2).

The league is fictional: six teams of 48 players, a 17-game season, and a hard
$255M salary cap. Our team, the Harbor City Herons (`HAR`), has $5.5M of cap
space and a weak secondary.

## Layout

```
agents/     agent + team definitions, and the plain-Python tools they call
servers/    MCP servers (League Office, Trade Desk, Simulator) - from 1.1
skills/     markdown know-how + helper scripts - from 1.5
data/       league.json (generated season start), league.db (SQLite, the live league), draft_results.json
draft/      standalone draft simulator - players, rules, valuation, engine, CPU agent
tests/      checks that run without an API key
private/    slides, scripts, proposal, schedule exports (git-ignored, never posted)
ROADMAP.md  the build plan, task by task
run.py      entry point (Analytics agent)
draft_day.py entry point (draft simulator)
```

## Setup (0.1)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # then put your OPENROUTER_API_KEY in .env
python data/generate_league.py
```

## 0.2: one agent, plain Python tools

The Analytics agent reads the league through four plain Python functions in
`agents/tools.py` (no MCP yet) and returns a structured `RosterReport`. It runs
on DeepSeek V4.1 Flash through OpenRouter.
`compare_to_league` does the league-wide math in code, comparing each team's
starters position by position, so the model gets ranks and gaps instead of
reading all 288 players itself. `get_roster` takes an optional position filter.

```powershell
python run.py                                                      # default question about our team
python run.py "How does our offensive line compare to the league?" # ask anything
python run.py --debug                          # watch every tool call
pytest                                         # tool checks, no API key needed
```

Done when: the agent reliably calls `get_roster` and its answer matches the data.

## 1.1: the League Office MCP server

`servers/league_office.py` serves the four league tools over MCP (stdio), using
the `MCPServer` class from mcp 2.x. The functions still live in
`agents/tools.py`; the server registers them as read-only tools, and their
docstrings become the tool descriptions.

```powershell
python -m servers.league_office   # run from the project root; speaks MCP on stdin/stdout
pytest tests/test_league_office.py
```

The Analytics agent now reads the league only through this server: `run.py`
starts it as a subprocess with Agno's `MCPTools` (which needs `fastmcp`) and
runs the agent async. `python run.py` works the same as before.

The league lives in SQLite (`agents/league_db.py`): tables for teams,
players, ratings and contracts, plus positions and rules. `data/league.json`
is only the seed for the start of the season; `data/league.db` is built from
it the first time a tool runs, and is not committed.

```powershell
python -m agents.league_db         # rebuild league.db from league.json
pytest tests/test_league_db.py     # uses scratch databases, never data/league.db
```

Done when: an MCP client lists the four tools and gets the same JSON as the
plain Python functions, both in-process and over stdio; the tools read
rosters and contracts from SQLite; and the agent's answer still matches the data.

## Draft Day: a 6-team, 53-round snake draft (standalone)

A separate, self-contained draft simulator - it doesn't read or write
`data/league.json`/`league.db` and isn't used by the Analytics agent above
(its own roster size and $220M cap are independent numbers, not the main
league's 48-player/$255M rules). It builds a fresh 53-man roster for each of
6 teams by drafting from a pool of ~385 real NFL players, rated with their
actual Madden NFL 26 overall rating (pulled from playerratingspro.com in
November 2026 - see `draft/players.py`). Long snapper is the one exception:
Madden doesn't publish LS ratings, so those eight are a rough estimate.

```powershell
python draft_day.py                 # choose your team interactively
python draft_day.py --team HAR       # control Harbor City directly
python draft_day.py --watch          # just watch all 6 CPU GMs draft
python draft_day.py --no-llm         # CPU picks use heuristic scoring only, no API calls
pytest tests/test_draft.py           # engine checks, no API key needed
```

- **Random order, snake format**: a fresh random draft order each run; the order reverses every round.
- **Roster shape**: `draft/roster_rules.ROSTER_TEMPLATE` sets exactly how many of each position fill the 53 spots - a position closes the moment a team hits its target, which is what "positions of need" means here.
- **Value and need**: `draft/valuation.py` scores every available player by estimated market value ($M, shown on the board) tilted toward whichever open position the team needs most urgently.
- **Salary cap**: drafted players get a rookie-scale salary from `draft/roster_rules.rookie_salary` (higher picks cost more, decaying by pick number); a $220M hard cap applies, and no team can draft a player it can't afford.
- **CPU GMs**: the 5 teams you don't control are each drafted by the same kind of OpenRouter/DeepSeek agent as Analytics (`draft/agent.py`), given a shortlist of the best value/need players and a randomly assigned front-office philosophy (best-player-available, need-first, trenches-first, or premium-positions-first) so the six teams draft differently. Pass `--no-llm` to skip the API and use the underlying heuristic directly instead.
- **You draft too**: on your team's turn, `board`, `board <POS>`, `needs`, `best`, and `pick <id>` from the command line.
- Results are written to `data/draft_results.json` (draft order, every team's final roster and payroll, and the full pick-by-pick log).
