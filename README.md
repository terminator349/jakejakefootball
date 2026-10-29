# Front Office

An AI-run football front office. You are the owner; a hierarchy of agents
scouts, trades and manages the roster against rival AI general managers.

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
