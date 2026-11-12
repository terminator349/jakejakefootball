# Front Office

An AI-run football front office. You are the owner; a hierarchy of agents
scouts, trades and manages the roster against rival AI general managers.

## Layout

```
agents/     agent + team definitions, and the plain-Python tools they call
servers/    MCP servers (League Office, Trade Desk, Simulator) - from Step 2
skills/     markdown know-how + helper scripts - from Step 4
data/       generated league data (and later the SQLite db)
draft/      standalone draft simulator - players, rules, valuation, engine, CPU agent
tests/      checks that run without an API key
run.py      entry point (Analytics agent)
draft_day.py entry point (draft simulator)
```

## Setup (Step 0)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # then put your OPENROUTER_API_KEY in .env
python data/generate_league.py
```

## Step 1: one agent, plain Python tools

The Analytics agent reads the league through four plain Python functions in
`agents/tools.py` (no MCP yet) and returns a structured `RosterReport`. It runs
on DeepSeek V4.1 Flash through OpenRouter.
`compare_to_league` does the league-wide math in code, so the model gets ranks
and gaps instead of reading all 138 players itself.

The league is football: positions from QB to K, nine ratings (passing,
rushing, receiving, blocking, pass_rush, run_defense, coverage, kicking,
athleticism), and an NFL-style **hard** salary cap - no luxury tax overage
like basketball's, a team is simply never allowed over the cap. Our team
(HAR) is deliberately generated weak at secondary coverage, so there's a
real planted weakness for the agent to find.

```powershell
python run.py                                  # default question about our team
python run.py "Who is our best defender?"      # ask anything
python run.py --debug                          # watch every tool call
pytest                                         # tool checks, no API key needed
```

Done when: the agent reliably calls `get_roster` and its answer matches the data.

## Draft Day: a 6-team, 53-round snake draft (standalone)

A separate, self-contained draft simulator - it doesn't read or write
`data/league.json` and isn't used by the Analytics agent above. It builds a
fresh 53-man roster for each of the same 6 teams by drafting from a pool of
~385 real NFL players, rated with their actual Madden NFL 26 overall rating
(pulled from playerratingspro.com in November 2026 - see `draft/players.py`).
Long snapper is the one exception: Madden doesn't publish LS ratings, so
those eight are a rough estimate.

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
- **Salary cap**: drafted players get a rookie-scale salary from `draft/roster_rules.rookie_salary` (higher picks cost more, decaying by pick number); the same $220M hard cap as the Step 0/1 league applies, and no team can draft a player it can't afford.
- **CPU GMs**: the 5 teams you don't control are each drafted by the same kind of OpenRouter/DeepSeek agent as Analytics (`draft/agent.py`), given a shortlist of the best value/need players and a randomly assigned front-office philosophy (best-player-available, need-first, trenches-first, or premium-positions-first) so the six teams draft differently. Pass `--no-llm` to skip the API and use the underlying heuristic directly instead.
- **You draft too**: on your team's turn, `board`, `board <POS>`, `needs`, `best`, and `pick <id>` from the command line.
- Results are written to `data/draft_results.json` (draft order, every team's final roster and payroll, and the full pick-by-pick log).
