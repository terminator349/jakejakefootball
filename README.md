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
data/       league.json (generated season start) and league.db (SQLite, the live league)
tests/      checks that run without an API key
private/    slides, scripts, proposal, schedule exports (git-ignored, never posted)
ROADMAP.md  the build plan, task by task
run.py      entry point
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

## 1.2: rule checks

`agents/rules.py` holds the league rules as plain Python. A trade is legal only
if, afterwards, every roster is between 46 and 53 players, no payroll is over
the $255M hard cap, and the week is no later than the week-9 deadline. It must
also be a real trade: two different teams, each sending players it actually has.

- `check_trade(trade, week)` lists every rule the trade would break, each with
  a reason the owner can read ("HAR's payroll would be $257.31M, $2.31M over the
  $255.0M hard cap."), plus each team's roster size, payroll and cap space
  after the trade. It changes nothing.
- `make_trade(trade, week)` runs the same checks and moves the players in
  `data/league.db` only if they all pass; otherwise it raises `IllegalMove` and
  the league is unchanged. It is plain Python for now: the Trade Desk (2.1) and
  the owner's approvals (G4) will call it.

The League Office server serves `check_trade` as a fifth read-only tool. The
Analytics agent still gets only the four data tools; `check_trade` is meant for
Cap & Contracts (1.3). The current week is passed in until the save file holds
it (G1).

```powershell
pytest tests/test_rules.py    # scratch databases, never data/league.db
```

Done when: every illegal trade is refused with the rule it broke, a legal one
changes the rosters, and a refused one changes nothing.
