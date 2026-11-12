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
data/       league.json (generated season start) and league.db (SQLite, the default league)
saves/      one SQLite database per saved game (git-ignored) - from G1
tests/      checks that run without an API key
ui/         a local web page for trying out everything built so far
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

## Test bench (local web UI)

A page for trying out everything built so far, running the real code:

```powershell
python -m ui.server      # then open http://127.0.0.1:8765
```

- **Game & saves**: start, load and list saves; enter scores or fill a week with
  random ones (a stand-in for the simulator, 3.1); advance the week; standings
  and the full schedule.
- **League**: teams, payroll and cap space; any roster; each team's biggest gaps
  from `compare_to_league`; the rules.
- **Trades**: pick players on both sides, check the trade against the 1.2 rules
  or make it, and see the move log.
- **League Office (MCP)**: starts the server over stdio, as the agents do, lists
  its tools and calls any of them with your arguments.
- **Analytics agent**: asks the real agent a question (needs `OPENROUTER_API_KEY`
  in `.env`) and shows its report, every tool call and the run's tokens and cost.

Everything reads and changes the loaded league: a save, or `data/league.db`
when none is loaded. The page only listens on this computer, and restarting
it goes back to the default league. `pytest tests/test_ui.py` checks its API.

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

- `check_trade(trade)` lists every rule the trade would break, each with
  a reason the owner can read ("HAR's payroll would be $257.31M, $2.31M over the
  $255.0M hard cap."), plus each team's roster size, payroll and cap space
  after the trade. It changes nothing.
- `make_trade(trade)` runs the same checks and moves the players in
  the league database (a save, or `data/league.db`) only if they all pass; otherwise it raises `IllegalMove` and
  the league is unchanged. It is plain Python for now: the Trade Desk (2.1) and
  the owner's approvals (G4) will call it.

The League Office server serves `check_trade` as a fifth read-only tool. The
Analytics agent still gets only the four data tools; `check_trade` is meant for
Cap & Contracts (1.3). Since G1 the current week comes from the league
database, not from the caller.

```powershell
pytest tests/test_rules.py    # scratch databases, never data/league.db
```

Done when: every illegal trade is refused with the rule it broke, a legal one
changes the rosters, and a refused one changes nothing.

## G1: game state and save files

Every league database now holds a game as well as the league: the current
week, the 17-week schedule with each game's result, and a log of every move.
Standings are an SQL view over the results, so they can't drift from them.

- **Schedule** (`agents/season.py`): made from a season seed when the database
  is built. Every team plays once a week and meets each rival three or four
  times, with 8 or 9 home games and no back-to-back rematches. The same seed
  gives the same schedule.
- **Season**: `record_result` writes a score for a game in the current week
  (the simulator, 3.1, will call it). `advance_week` moves on only once every
  game that week has a result. After week 17 the current week is 18 and the
  regular season is over. `standings` ranks teams by win percentage (a tie is
  half a win), then point difference, then points scored.
- **Saves** (`agents/saves.py`): `new_game(name)` builds `saves/<name>.db` from
  the `league.json` seed with its own season seed. `load_game(name)` makes a
  save the league every tool reads. `list_saves()` shows each save's week and
  our record. A save is never overwritten unless asked.
- **Moves**: `make_trade` logs each trade (the week and every player's old and
  new team) in the same transaction that makes it; `move_log()` reads the log.
  `check_trade` and `make_trade` take the current week from the save.
- **Old databases**: each database records its schema version. An old
  `data/league.db` is rebuilt automatically; an old save is refused with a
  message, never rebuilt.

```powershell
python -m servers.league_office --db saves/herons.db   # serve a saved game
pytest tests/test_season.py tests/test_saves.py
```

Done when: a new game starts at week 1 with a fair 17-week schedule, results
and standings agree, every trade is logged, and a loaded game continues where
it stopped.
