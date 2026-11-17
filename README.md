# Front Office

An AI-run American football front office, played as an interactive web game.
You are the owner; each week your General Manager briefs you, you give orders,
and a hierarchy of agents scouts, trades and manages the roster against rival
AI general managers. On game day you can sim the game, watch it drive by
drive, or call the plays yourself. See `ROADMAP.md` for the game design and the build
plan; a "How to play" section arrives with the game loop (task G2).

The league is fictional: six teams of 48 players, a 17-game season, and a hard
$255M salary cap. Our team, the Harbor City Herons (`HAR`), has $5.5M of cap
space and a weak secondary.

## Layout

```
agents/     agent + team definitions, and the plain-Python tools they call
servers/    MCP servers (League Office, Trade Desk, Simulator) - from 1.1
skills/     markdown know-how + helper scripts - from 1.5
data/       league.json (generated season start), league.db (SQLite, the default league), draft_results.json
saves/      one SQLite database per saved game (git-ignored) - from G1
draft/      standalone draft simulator - players, rules, valuation, engine, CPU agent
tests/      checks that run without an API key
ui/         a local web page for trying out everything built so far
private/    slides, scripts, proposal, schedule exports (git-ignored, never posted)
ROADMAP.md  the build plan, task by task
run.py      entry point (Analytics agent)
check_cap.py entry point (Cap & Contracts agent)
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

## Test bench (local web UI)

A page for trying out everything built so far, running the real code:

```powershell
python -m ui.server      # then open http://127.0.0.1:8765
```

- **Game & saves**: start, load and list saves; sim the week with the 3.1
  simulator or type scores by hand; advance the week; standings and the full
  schedule. Click a result for its box score and play-by-play.
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
  `data/league.db` is rebuilt automatically. A save one version behind is
  upgraded in place (G1 saves gain the 3.1 tables); anything older is refused
  with a message, never rebuilt.

```powershell
python -m servers.league_office --db saves/herons.db   # serve a saved game
pytest tests/test_season.py tests/test_saves.py
```

Done when: a new game starts at week 1 with a fair 17-week schedule, results
and standings agree, every trade is logged, and a loaded game continues where
it stopped.

## 3.1: the season simulator (first stage: "Sim it")

`agents/simulator.py` plays a game one snap at a time, in plain Python with no
model calls. `Game.step()` runs one snap: the offense picks a play (inside or
outside run, short or deep pass, play action, screen, punt, field goal, kneel)
and the defense a call (base, blitz, cover 2, deep zone, run stuff). The
result comes from the starters' unit strengths (run blocking against run
defense, deep passing against deep coverage, pass rush against pass blocking),
how the two calls match up, and a seeded random number generator. Big
mismatches have diminishing returns, so a weak unit hurts but isn't hopeless.

- **Play callers**: teams the owner isn't coaching use plain-Python tendencies
  by down, distance, score and clock, leaning toward what works against that
  defense. Every offense throws more against our secondary than anyone else's.
  `step()` also takes a person's calls, ready for G8.
- **Repeatable**: separate random streams for calls and for what happens on the
  field. The same season seed plays the same season.
- **Saving games** (`agents/season.py`): `play_week()` plays the current week's
  unplayed games with the rosters as they stand, and saves each score, every
  snap (`plays` table) and every player's stats (`player_game_stats`).
  `box_score(game_id)` returns team totals, player lines and the play-by-play.
- **Tuned** over hundreds of seeded games, per team per game: about 21 points
  and 65 scrimmage plays, 64% completions, 7.1 yards a pass, 4.3 a carry, 1.9
  sacks and 4.4 punts. Home teams win 52%, and under 1% of games end tied. The
  Herons win about a third of their games, and the Odom trade from 1.2 lifts
  that by about six points.

```powershell
pytest tests/test_simulator.py
```

Still to come in 3.1: "Watch it" (drive by drive) in W5, and smarter late-game
calls (spikes, the hurry-up when far behind) as part of it.

## 1.3: the Cap & Contracts agent

A second specialist, `agents/cap_contracts.py`, reads the same League Office
server and answers whether a roster move is legal under the hard $255M cap.
Two new read-only tools joined `servers/league_office.py`:
`check_cap_fit(team_id, new_salary)` tests one new contract against a team's
cap space and reports `salary_to_clear` if it doesn't fit; `validate_cap_compliance()`
scans every team and flags any that are over the cap. The agent returns a
structured `CapReport` (payroll, cap space, `fits_under_cap`, `salary_to_clear`),
using the same DeepSeek V4.1 Flash + parser-model pattern as Analytics.

```powershell
python check_cap.py                                                  # is the league legal right now?
python check_cap.py "Can we sign a free agent safety for $6M/year?"  # ask about a specific move
python check_cap.py --debug                           # watch every tool call
pytest tests/test_cap_contracts.py                    # agent checks, no API key needed
```

Done when: `check_cap_fit` correctly reports whether a hypothetical salary fits
each team's cap space and how much must be cleared if it doesn't, and
`validate_cap_compliance` confirms every team is at or under $255M.

## Draft Day: a 6-team, 53-round snake draft (standalone)

A separate, self-contained draft simulator - it doesn't read or write
`data/league.json`/`league.db` and its 53-man roster shape is its own (not
the main league's 48-player rosters), but it shares the main league's $255M
hard cap: `draft/roster_rules.SALARY_CAP` reads it from the same rules the
Cap & Contracts agent uses, so there's one cap number for the whole project,
not two. The Draft GM agent (`draft/agent.py`) carries the same `check_cap_fit`
and `validate_cap_compliance` tools as Cap & Contracts, bound to the draft's
own in-memory teams by `draft/tools.build_cap_tools` - same cap arithmetic
(`agents.tools.cap_math`), different team data. It builds a fresh 53-man
roster for each of 6 teams by drafting from a pool of ~385 real NFL players,
rated with their
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
- **Salary cap**: drafted players get a rookie-scale salary from `draft/roster_rules.rookie_salary` (higher picks cost more, decaying by pick number); the $255M hard cap applies, and no team can draft a player it can't afford. `eligible_for()` pre-filters the pool to what a team can afford, and the CPU GM's own `check_cap_fit`/`validate_cap_compliance` tools double-check a pick before it's made.
- **CPU GMs**: the 5 teams you don't control are each drafted by the same kind of OpenRouter/DeepSeek agent as Analytics (`draft/agent.py`), given a shortlist of the best value/need players, cap-checking tools, and a randomly assigned front-office philosophy (best-player-available, need-first, trenches-first, or premium-positions-first) so the six teams draft differently. Pass `--no-llm` to skip the API and use the underlying heuristic directly instead.
- **You draft too**: on your team's turn, `board`, `board <POS>`, `needs`, `best`, and `pick <id>` from the command line.
- Results are written to `data/draft_results.json` (draft order, every team's final roster and payroll, and the full pick-by-pick log).
