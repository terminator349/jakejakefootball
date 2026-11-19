# Front Office

An AI-run American football front office, played as an interactive web game.
You are the owner; each week your General Manager briefs you, you give orders,
and a hierarchy of agents scouts, trades and manages the roster against rival
AI general managers. On game day you can sim the game, watch it drive by
drive, or call the plays yourself. See "How to play" below, and `ROADMAP.md`
for the game design and the build plan.

The league is fictional: six teams of 48 players, a 17-game season, and a hard
$255M salary cap. Our team, the Harbor City Herons (`HAR`), has $5.5M of cap
space and a weak secondary.

## Layout

```
agents/     agent + team definitions, and the plain-Python tools they call
servers/    MCP servers: League Office (1.1), Trade Desk (2.1)
skills/     markdown know-how + helper scripts - from 1.5
data/       league.json (generated season start), league.db (SQLite, the default league), draft_results.json
saves/      one SQLite database per saved game (git-ignored) - from G1
draft/      standalone draft simulator - players, rules, valuation, engine, CPU agent
tests/      checks that run without an API key
ui/         the game (game.html), the test bench (bench.html) and what they share (static/)
private/    slides, scripts, proposal, schedule exports (git-ignored, never posted)
ROADMAP.md  the build plan, task by task
run.py      entry point (Analytics agent)
check_cap.py entry point (Cap & Contracts agent)
ask_gm.py   entry point (the GM and its specialists)
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

## How to play (G2)

```powershell
python -m ui.server      # then open http://127.0.0.1:8765
```

No API key is needed to play. The GM's briefing and asking the front office
need `OPENROUTER_API_KEY` in `.env`; the other agents join the game as they are
built.

1. **Start a game.** Give it a name (and a seed if you want a season you can
   repeat). Each game is its own save in `saves/`, saved as you play. Continue
   or load a game from the same screen.
2. **Each week** shows the matchup, both records, and **your GM's briefing**
   (G3, below): our record and standing, last week's result and standouts, the
   other results, our biggest weakness and who plays there, the cap, the trade
   deadline and this week's opponent. Without a key, or while the GM writes it,
   plain notes read from the league stand in. **Ask the front office** puts any question to your GM, who asks Analytics,
   Cap & Contracts or Draft and answers you with a recommendation, the numbers
   behind it and what each specialist said (1.4, below). **Give an order**
   ("Upgrade safety. Stay under $5M a year.") and your GM proposes trades that
   follow it; **approve** or **veto** each one under **Proposed moves** (G4,
   below). Nothing goes to another team until you approve it.
3. **Play the week.** **Sim it** plays every game and shows the results.
   **Watch it** plays the week, then shows our game drive by drive, with a
   scoreboard and the ball on the field, before any other score. **Call it**
   puts you on the sideline (G8, below).
4. **Results**: our score, every game of the week with its box score, the
   standings, and a replay of our game. Then go on to the next week.
5. **Roster, Standings, Schedule and Cap** tabs: any team's roster with
   ratings, contracts and starters; our 17 games with results, box scores and
   replays; payroll, cap space, the biggest contracts and who is in a final year.
6. **Save & quit** goes back to the title screen. The save already holds
   everything; load it to carry on from the same week.

After week 17 the game shows the final standings; the playoffs are G6.
`agents/game_loop.py` builds the week in plain Python, and
`pytest tests/test_game_loop.py tests/test_ui.py` checks it and the page's API.

### Call it (G8)

Pick **at key moments** or **every snap** next to the button, then press
**Call it**. At key moments the game sims until a moment worth calling and
hands you the call:

- **On offense**: a 4th down, the red zone, the two-minute drill (end of either
  half) and overtime.
- **On defense**: they're in our red zone, overtime, or the last two minutes of
  a one-score game.

Every snap hands you each call, except the ones a defensive call can't change
(their punts, field goals, kneels and spikes).

- **Offense**: six plays, each with a number for how our players match up
  against theirs for it (their defensive call, which you don't see, matters
  too), plus punt, field goal (with its distance), kneel and spike.
- **Defense**: five calls, each saying what it stops and what it's weak
  against, with their best matchups against us listed underneath.

Number keys 1 - 9 make a call. The screen shows the score, clock, timeouts, the
ball and the first-down line, the plays since your last call and the drive
chart. Switch levels or **Sim the rest of the game** at any time. When it ends,
the rest of the week is played and the results follow.

A called game survives **Save & quit** and a restart. The save keeps only your
calls (the `live_games` table, schema version 3), and `agents/live.py` rebuilds
the game by replaying the seed with them, so the same calls always give the
same game. **Sim it** is refused while a game is being called, so it can't be
thrown away. Trading during a called game (from the bench) would change the
replay; the game itself has no way to do it. `pytest tests/test_live.py`
checks it.

## Test bench (local web UI)

A page for trying out everything built so far, running the real code, at
http://127.0.0.1:8765/bench on the same server as the game:

- **Game & saves**: start, load and list saves; sim the week with the 3.1
  simulator or type scores by hand; advance the week; standings and the full
  schedule. Click a result for its box score, drive chart and play-by-play, or
  **Watch** it drive by drive.
- **League**: teams, payroll and cap space; any roster; each team's biggest gaps
  from `compare_to_league`; the rules.
- **Trades**: pick players on both sides, check the trade against the 1.2 rules
  or make it, and see the move log.
- **MCP servers**: starts the League Office or the Trade Desk over stdio, as
  the agents do, lists its tools and calls any of them with your arguments.
- **Agents**: asks the GM's team, Analytics or Cap & Contracts a question
  (needs `OPENROUTER_API_KEY` in `.env`) and shows the report, every tool call
  and the run's tokens and cost. For the GM: each task it gave a specialist, and
  each specialist's report and tool calls.

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

## 3.1: the season simulator ("Sim it" and "Watch it")

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
  `step()` also takes a person's calls, which is how G8 lets the owner call them.
- **The clock**: a snap takes a few seconds off at the whistle. If the clock
  keeps running, the huddle and the walk to the line run off before the next
  snap, unless a team calls a timeout or the offense spikes the ball. Late in a
  half the AI hurries (earlier when two scores down) and stops running the ball
  when it can't stop the clock. It calls timeouts (on defense, only while it can
  still get the ball back), spikes when out of timeouts, kicks a field goal
  before time runs out, throws it deep on the last snap, and kneels to finish a
  win once the defense can't stop the clock. A half can now end before the next snap; `step()` then
  returns `None`.
- **Repeatable**: separate random streams for calls and for what happens on the
  field. The same season seed plays the same season.
- **Saving games** (`agents/season.py`): `play_week()` plays the current week's
  unplayed games with the rosters as they stand, and saves each score, every
  snap (`plays` table) and every player's stats (`player_game_stats`).
  `box_score(game_id)` returns team totals, player lines, the drives and the
  play-by-play.
- **Drives** (`drives()` in `agents/simulator.py`): the play log grouped into
  possessions, each with where and when it started, plays, yards, time used,
  how it ended (touchdown, field goal, punt, turnover, downs, end of half...)
  and the score after it. About 11 drives a team, as in the NFL.
- **Watch it** (test bench): a scoreboard, a field with the ball, the drive so
  far and the first-down line, and the drive chart as it grows. Step a play or
  a drive at a time, autoplay, or skip to the end.
- **Tuned** over hundreds of seeded games, per team per game: about 22 points
  and 65 scrimmage plays, 64% completions, 7.1 yards a pass, 4.3 a carry, 2.1
  sacks and 4.3 punts. Home teams win about 54%, and under 1% of games end tied.
  The Herons win about 30% of their games, and the Odom trade from 1.2 lifts
  that by about six points.

```powershell
pytest tests/test_simulator.py
```

Done when: games look like football over hundreds of seeds, the play log
rebuilds the score, drive by drive, and the end of each half is played like a
real one. Calling the plays yourself is G8 (see "Call it" above).

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

## 1.4: the GM's team, the first agent-to-agent link

`agents/gm.py` puts a General Manager in charge of every agent built so far,
as an Agno `Team` in coordinate mode. The owner asks the GM; the GM decides
which specialists the question needs, writes each a specific task, and
combines their answers. It has no data tools of its own, so every number it
gives comes from a specialist.

```
Owner -> GM -> Analytics        League Office: rosters, ratings, rankings
            -> Cap & Contracts  League Office: payroll, cap fit, trade checks
            -> Draft            Draft Day results and the draft class
```

- **Specialists keep their own tools.** Analytics and Cap & Contracts each start
  their own League Office server with their own slice of its tools, pointed at
  the same league (the loaded save, in the game).
- **They hand work on.** Later specialists see what earlier ones said in the
  same run (`share_member_interactions`), so the GM can ask Analytics for the
  weakness and a target salary, then ask Cap & Contracts whether that salary
  fits.
- **The Draft desk** (`agents/draft_desk.py`) is new. The Draft GM agent
  (`draft/agent.py`) only makes picks, one at a time, so the GM's team gets a
  desk that reads Draft Day's results (`data/draft_results.json`) through three
  plain Python tools. `draft_summary` grades every team's class (average
  overall, players rated 90+, market value against rookie salary, rank) so
  teams compare in one call; `team_draft` and `best_undrafted` name the players.
  Draft Day's rosters are not the league's, and the desk says so. When the
  draft moves into the game (G7), these tools read the save's prospect pool.
- **Grounded**: `GMReport` (answer, recommendation, evidence) is filled by a
  parser model, as for the specialists. The money line is always our payroll
  and cap space, from the league. `summarize()` adds who was asked, each task,
  each specialist's grounded report and tool calls, and the run's total tokens
  and cost (the GM's calls plus the specialists'). DeepSeek's structured output
  now and then runs on into whitespace; then the GM's own text is parsed again
  (up to twice), and if that fails too, the owner sees the GM's text as written.
- **Guards**: at most six delegations a question, each specialist asked about
  its own area only, and each with its own tool-call limit.

A question takes from under a minute to about two and a half, and costs from a
tenth of a cent to about two cents, depending on how many specialists it needs.

```powershell
python ask_gm.py                                                  # weakest spot, and can we afford a fix?
python ask_gm.py "Which team did best on Draft Day?"
python ask_gm.py --debug                          # every delegation, tool call and model message
pytest tests/test_gm.py                           # team and Draft desk checks, no API key needed
```

Done when: the GM routes a question to the right specialists, passes one's
findings to the next, and answers the owner with their numbers, in the game
and on the bench.

## G3: the GM's weekly briefing

At the start of each week the GM writes the owner a short briefing
(`agents/briefing.py`): a headline, two to four short paragraphs and one line
on what it's watching.

- **Plain Python owns the numbers.** `facts()` reads everything the briefing may
  say from the league: the record and standing (from week 2), last week's score,
  yards, turnovers and our standout lines from the box score, the other results,
  the biggest weakness with its rank, rating, league average and the starters
  there, the biggest strength, payroll and cap space, roster size, the trade
  deadline and this week's opponent.
- **The GM only writes.** One model call with the facts as JSON and no tools
  (DeepSeek V4.1 Flash, about 15-25 seconds and a tenth of a cent).
- **Every number is checked.** `unknown_numbers()` lists any number in the
  briefing that isn't in the facts (so "won by 7" fails when the facts only
  have the score). A draft that fails goes back to the GM with those numbers
  named; after three tries, or with no key, the owner gets the plain notes, and
  the page says why.
- **Written once a week.** A briefing that checks out is kept in the save
  (`briefings` table, schema version 4; older saves are upgraded), so the owner
  reads the same one every time they open the week. The week screen asks for it
  when it isn't there yet and shows the notes until it arrives.

```powershell
pytest tests/test_briefing.py      # facts, the number check, rewrites and storage, no API key needed
```

Done when: each week opens with a briefing whose every number comes from the
league data, and the game is still playable without a key.

## 1.5: skills

`skills/` holds the front office's know-how as Agent Skills: each one is a
folder with a `SKILL.md` (a name, a description and the instructions), helper
scripts and reference notes. An agent given a skill sees only its name and
description until a question calls for it. Then it loads the instructions and
runs the scripts with Agno's skill tools (`get_skill_instructions`,
`get_skill_reference`, `get_skill_script`). `agents/skills.py` loads them, and
Agno checks each folder against the format as it does.

```
skills/
  salary-cap-rules/   the hard cap, roster limits, the deadline, no dead money
    scripts/cap_check.py          a signing or a many-for-many trade against every rule
    references/worked-examples.md
  player-valuation/   market value from the league's own salaries, surplus, age
    scripts/value_player.py       market value, verdict, and value for the job (--key)
  roster-impact/      how ratings feed the simulator's units
    scripts/unit_impact.py        how much one swap moves each unit, from build_lineup itself
    references/units.md
  front-office-memo/  the house style for anything the owner reads
    scripts/check_memo.py         numbers not in the facts, and style problems
    references/examples.md        a good briefing, a bad one, a good answer
```

| Who               | Skills                                                 |
|-------------------|--------------------------------------------------------|
| Analytics         | player-valuation, roster-impact                        |
| Cap & Contracts   | salary-cap-rules                                       |
| The GM            | front-office-memo, always on (in its instructions)     |
| The briefing      | front-office-memo, always on, and its checks           |

- **The scripts use the league's own code**, not a copy of the rules:
  `cap_check.py` uses the League Office's `cap_math` and the rules in
  `data/league.json`, and `unit_impact.py` builds two lineups with the
  simulator's `build_lineup`, the same but for one starter. Their numbers are
  the engine's.
- **roster-impact is a fourth skill**, beyond the plan's three. Every veteran
  in this league is paid about fairly for his overall, so value alone can't
  tell two safeties apart. The difference is in the ratings the job uses: a
  coverage safety needs coverage. `value_player.py --key coverage=85` prices a
  player on that rating, and `unit_impact.py` shows how far he'd move the weak
  unit.
- **The memo skill is always on** for the GM and the briefing, since everything
  they write goes to the owner: its "House style", "Answering the owner" and
  "The weekly briefing" sections are part of their instructions
  (`skills.section()`). The briefing also checks its measurable rules
  (`agents/memo.py`): a headline of at most 12 words, two to four paragraphs of
  at most three sentences each, and no hype words. A draft that breaks them goes
  back with the problems named. Numbers stay the hard rule: if the style still
  isn't right after three tries, the owner gets the first draft whose numbers
  checked.
- **Analytics can make up to 18 tool calls** (it was 10): loading two skills and
  running their scripts on a few candidates takes 5-8 calls on top of the
  League Office's.

Tried live, a safety question went to Analytics: it priced the targets with
`value_player.py`, measured each against our weaker starter with
`unit_impact.py`, and the GM's answer cited the result ("+9.00 deep
coverage"). Cap & Contracts then checked the salary. The question took about
70 seconds and cost under a cent. A briefing written under the house style
passed both checks on its first try.

```powershell
python skills/salary-cap-rules/scripts/cap_check.py trade --payroll 249.48 --roster 48 --out 4.1 2.98 --in 9.87 --week 3
python skills/player-valuation/scripts/value_player.py --position S --overall 70 --salary 4.1 --age 34 --key coverage=52
python skills/roster-impact/scripts/unit_impact.py --position S --current coverage=52,tackling=78,speed=81 --candidate coverage=83,tackling=71,speed=80
pytest tests/test_skills.py        # every skill, script and assignment, no API key needed
```

Done when: each specialist loads its skills and runs their scripts when a
question calls for it, and everything written to the owner follows the house
style.

## 2.1: the Trade Desk MCP server

The League Office only reads the league. `servers/trade_desk.py` is the second
MCP server, and the one place trades happen: a team evaluates a trade,
proposes it, and the team it's offered to accepts, rejects or counters it.
The logic is plain Python in `agents/trade_desk.py`, and proposals are kept in
the league database (`trade_proposals`, schema version 5; older saves are
upgraded when they're opened).

```
propose  ->  open  ->  accept    the rules are checked again, then the players move
                   ->  reject
                   ->  counter   a new open proposal the other way; the first is "countered"
                   ->  withdraw  by the team that made it
                   ->  void      it broke a rule when accepted, or one of its players was traded
```

| Tool                  | What it does                                                   | Annotation      |
|-----------------------|----------------------------------------------------------------|-----------------|
| `evaluate_trade`      | the rule check, plus each side's value, payroll and unit changes | read-only     |
| `list_proposals`      | proposals by team and status                                   | read-only       |
| `get_proposal`        | one proposal, and whether it would pass the rules right now    | read-only       |
| `trade_log`           | every trade made this season                                   | read-only       |
| `propose_trade`       | offer a trade; an illegal one is refused and not stored        | writes          |
| `counter_proposal`    | answer an offer with other terms                               | writes          |
| `withdraw_proposal`   | take back your own offer                                       | writes          |
| `respond_to_proposal` | accept (makes the trade) or reject                             | destructive     |

- **Legal at both ends.** A proposal is checked against the 1.2 rules when
  it's made and again inside the transaction that moves the players
  (`rules.make_trade_in`), so an offer from week 3 can't go through after the
  deadline or after a roster change made it illegal. An accept that fails the
  rules makes the proposal void, with the rule in its answer, and moves nobody.
- **One trade, one set of players.** When a trade goes through, every other
  open proposal with one of its players is voided, naming who moved.
- **The desk does the arithmetic.** `evaluate_trade` gives, for each team, the
  players in and out with their market value and surplus (the
  player-valuation skill's own formula, loaded from its script), the payroll
  change, new starters, starters lost or benched, and how each simulator unit
  moves (`build_lineup` on the real rosters before and after). An agent can
  quote these numbers instead of working them out, which matters under the
  briefing's number check (G3).
- **Who may act is checked by team id**: only the team an offer was made to
  can answer it, and only the team that made it can withdraw it. The owner's
  approval of the Herons' own offers comes before the desk, in G4.

The GM evaluates trades on the desk, and the moves the owner approves are
proposed on it as the Herons' offers (G4). The rival GMs (2.2) will answer
them. On the bench, the **MCP servers** tab can start
either server and call any tool; the Trade Desk's writes change the loaded
league.

```powershell
python -m servers.trade_desk                         # over stdio, for an MCP client
python -m servers.trade_desk --db saves/herons.db    # a saved game
pytest tests/test_trade_desk.py                      # no API key needed
```

Done when: a trade can be evaluated, proposed, countered and accepted over
MCP, every step is checked against the league rules, and only an accepted
proposal moves players.

## G4: orders and approvals

The owner gives the GM an order in plain words, the GM turns it into proposed
moves, and the owner approves or vetoes each one. Nothing goes to another team
until it's approved. The logic is in `agents/orders.py`; orders and proposed
moves are kept in the save (`orders` and `gm_proposals`, schema version 6).

```
"Upgrade safety. Stay under $5M a year. Don't trade Okafor."
  -> the GM reads it into terms        positions S; nobody over $5.00M; don't trade Mateo Okafor (HAR-01)
  -> the GM searches and files moves   each one checked by plain Python before the owner sees it
  -> Approve and send                  checked again, then our offer on the Trade Desk (2.1)
  -> Veto                              dropped
```

- **The model reads, plain Python holds it to the order.** The GM reads the
  order into `OrderTerms`: the positions to upgrade, the most an incoming
  player may earn, the most our payroll may grow, and our players not to
  trade. The owner sees those terms under the order. A name more than one of
  our players shares ("Okafor") protects all of them, and the summary names
  each one.
- **Every proposed move is checked** (`check_move`) before it's filed: the
  1.2 rules through the Trade Desk's evaluation, no player that *any* standing
  order protects, and this order's salary limits and positions. The GM can
  only file a move through `propose_to_owner`, which hands the problems back
  so it can fix the move or try another. At most three moves per order.
- **The GM's search** uses the League Office's `get_roster`,
  `compare_to_league` and `list_teams`, the Trade Desk's `evaluate_trade`, and
  `trade_targets` (players at a position on the other teams, under a salary).
  It can't propose on the Trade Desk itself; only the owner's approval does.
  Its reasons quote the evaluation's numbers. The scouting team (4.1) takes
  over finding targets later.
- **Orders stand all season** until the owner cancels them, so "never trade
  Okafor" holds for every later order. Cancelling an order voids its moves
  still waiting. An order that only sets a rule needs no search, and after
  the trade deadline the GM says there's nothing it can propose.
- **Approving checks again**: if the league or the orders changed since the
  move was filed, it's void and nothing is sent. Otherwise it goes on the
  Trade Desk as the Herons' open offer. The other team answers it there: the
  rival GMs will from 2.2. Until then it waits, and the bench's **MCP
  servers** tab can answer for them (`respond_to_proposal`). The week screen
  shows what became of each offer.
- **Without a key**, giving an order says it needs one; approving, vetoing and
  cancelling are plain Python and always work.

Tried live on the example order: the GM checked eight trades with
`evaluate_trade` and filed one, Quentin Sato (82 overall, coverage 85,
$3.81M) from Delta Bay for Hunter Dubois, with deep coverage up 8.25 and
$2.71M of cap space left. Every number in its reason came from the tools. The
order took 52 seconds and cost under a cent.

```powershell
pytest tests/test_orders.py    # every check, approval and the game's API, no API key needed
```

Done when: an order in plain words becomes moves that follow it and the
league rules, and the owner approves or vetoes each one before anything goes
to another team.

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
