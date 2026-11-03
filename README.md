# Front Office

An AI-run American football front office. You are the owner; a hierarchy of
agents scouts, trades and manages the roster against rival AI general managers.

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
