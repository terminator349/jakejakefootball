# Front Office

An AI-run American football front office. You are the owner; a hierarchy of
agents scouts, trades and manages the roster against rival AI general managers.

The league is fictional: six teams of 48 players, a 17-game season, and a hard
$255M salary cap. Our team, the Harbor City Herons (`HAR`), has $5.5M of cap
space and a weak secondary.

## Layout

```
agents/     agent + team definitions, and the plain-Python tools they call
servers/    MCP servers (League Office, Trade Desk, Simulator) - from Step 2
skills/     markdown know-how + helper scripts - from Step 4
data/       generated league data (and later the SQLite db)
tests/      checks that run without an API key
run.py      entry point
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
