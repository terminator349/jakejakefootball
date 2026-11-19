# An Example Season

One season of Front Office, from a new game to the end of the playoffs, as the
player sees it. It shows how the finished game should play once every roadmap
task is built; the task numbers in brackets show which task builds each part.

Draft of Nov 12, 2026, brought up to date Nov 19 (after 1.4, G3, G8 and 1.5),
for review.

**What's real here.** The players, salaries, ratings, ranks and cap numbers
come from the actual league data, and every trade below was run through the
1.2 rule checks: the rejections are the exact messages they return. Starting a
game, the briefing's shape, the three ways to play a game and asking the GM a
question work today. **What's made up.** Game scores and records (a real
seeded season gives its own), the agents' wording, and everything from orders
(G4) on, which isn't built yet.

The game is a web page (G2). The screens below are text sketches of what each
page holds, not its layout, and the numbered options are buttons, not
keystrokes.

---

## Starting a new game [G1, G2, 4.5]

```
FRONT OFFICE

  New game:  [ herons-2026 ]  [ Seed (optional) ]  [ Difficulty: Normal ]  Start
  Continue or load:  herons-2026 (week 1)

New season started. You own the Harbor City Herons.
Cap: $255.0M (hard)   Payroll: $249.48M   Cap space: $5.52M   Trade deadline: week 9
```

"New game" copies the league seed into a fresh save file. The same save and
seed always play out the same season. Name and seed work today; the
difficulty choice arrives with 4.5.

## Week 1: the first briefing [G3, 1.4]

```
=== Week 1: Herons 0-0 ===  Lakeshore at Harbor City   Cap space: $5.52M

Your GM's briefing                                            week 1
  Our safeties can't cover, and the cap is tight.

  We open at home against Lakeshore.

  Our safeties' coverage averages 48.5, last of 6 teams; the league
  average is 71.8. Our corners are last too, at 58.5.

  We have $5.52M of cap space, so any fix has to be cheap or send
  salary back.

  Watching: whether Lakeshore throws at our safeties.

  Ask the front office    Give an order (G4)    Review proposed moves (G4)
  Roster · Standings · Schedule · Cap
  Sim it    Watch it    Call it (at key moments / every snap)
```

The briefing is a headline, two to four short paragraphs and one line on what
the GM is watching, in the front-office-memo skill's style (1.5). Plain Python
gathers the week's facts, and a check rejects any number the GM wrote that
isn't one of them, so the GM can quote numbers but never work out new ones.
Without an API key, plain notes from the league stand in.

### Asking a question [1.4, 0.2]

```
Ask the front office: Who are our safeties and how bad are they?

GM: I asked Analytics. Our two starting safeties are both strong tacklers but
    weak in coverage:
      Theo Strickland     34   coverage 52   tackling 78   $4.10M, 2 years left
      Nikola Kowalski     32   coverage 45   tackling 81   $2.98M, 5 years left
    The backups, Grant Tanaka (coverage 42) and Hunter Dubois (40), are no
    better. Teams are throwing at our safeties.

    Asked: Analytics (roster, compare to league)
```

The owner talks only to the GM. The GM decides which specialist to ask, and
the answer shows who was asked and what each said.

### Giving an order [G4]

```
Your order: Upgrade safety. Stay under $5M a year. Don't trade Okafor.

GM: Understood. I'll look for a safety who costs less than $5M and covers well,
    and I won't touch Mateo Okafor. I'll bring you options before anything is
    agreed.
```

Orders are plain words. The GM keeps standing orders, like "don't trade
Okafor", for the rest of the season and in saved games [4.2].

### Playing the week [3.1, G8]

```
Sim it
Week 1 results
  Lakeshore 20  at  Harbor City 23
  Summit    27  at  Iron Falls  24
  Delta Bay 17  at  Mesa Verde  14

Herons 1-0
```

**Sim it** plays every game at once. **Watch it** shows our game drive by
drive. **Call it** hands the owner the Herons' play calls, at key moments or
every snap. Every game is played snap by snap in plain Python with a seeded
random number generator; no model is called, so this works without an API key.

## Weeks 2-5: the GM goes shopping [1.3, 1.2]

The GM and the front office search between weeks. Before any move reaches the
owner, Cap & Contracts checks it against the league rules. Moves that break a
rule are dropped there, with the reason.

```
=== Week 6: Herons 3-2, 3rd of 6 ===  Cap space: $5.52M   Trade deadline: week 9

Your GM's briefing
  Summit has a backup safety who fits your order.

  We lost 17-24 at Iron Falls. Safety coverage still ranks 6th of 6.

  I looked at Lakeshore's Wade Brennan (coverage 88, $9.87M) for Hunter
  Dubois. Cap & Contracts says no: our payroll would be $258.35M, $3.35M
  over the $255.0M hard cap. He'd also break your $5M limit.

  Review proposed moves  (1 waiting: trade with SUM)
```

### Reviewing a proposed move [G4, 2.1]

```
Proposal 1 of 1: trade with Summit (SUM)

  We send   Hunter Dubois     S  28  coverage 40  $1.00M, 5 years left
  We get    Isaiah Odom       S  29  coverage 80  $4.46M, 5 years left

  Why:        Odom would be our best cover safety by 28 points. He's a backup
              in Summit, where Kofi Gaines and Isaiah Thibodeaux start.
  Your order: under $5M a year. Odom earns $4.46M.
  League rules: legal. Rosters stay at 48. Our cap space after: $2.06M.

  Approve    Veto    Ask the GM about it
> Approve
```

Nothing goes to another team until the owner approves it.

### The rival GM answers [2.2]

```
Summit's GM countered:
  "Odom is our insurance at safety. Add Bryce Strickland and you have a deal."

  We send   Hunter Dubois     S   28  coverage 40  $1.00M, 5 years left
            Bryce Strickland  CB  24  coverage 42  $1.08M, 3 years left
  We get    Isaiah Odom       S   29  coverage 80  $4.46M, 5 years left

  League rules: legal. Our roster drops to 47 (minimum 46). Cap space after: $3.14M.

  Accept counter    Refuse    Ask the GM about it
> Ask the GM about it
GM: Strickland is a backup corner, tied with Darius Kessler at the bottom of
    our depth chart. Giving him up costs us almost nothing, and we keep $1.08M
    more of cap space. I'd accept.
> Accept counter

Trade complete. Isaiah Odom joins the Herons.
Payroll: $251.86M   Cap space: $3.14M   Roster: 47
```

The rival GM is an AI agent that accepts, refuses or counters. Our side is
checked again when the counter arrives, and the League Office makes the trade
only if every rule still passes [1.2].

## Week 8: the league moves without you [G5]

```
=== Week 8: Herons 4-3, 3rd of 6 ===  Cap space: $3.14M   Trade deadline: week 9

League news
  Iron Falls traded Devin Dubois (S) to Delta Bay for a backup tackle.

Your GM's briefing
  Mesa Verde wants Theo Strickland; I'd say no.

  The deadline is next week. Mesa Verde offered us Omar Sato (S, $5.26M)
  for Theo Strickland ($4.10M). Sato covers better, but he costs $1.16M of
  our last $3.14M, and his contract runs two years longer.

  Review proposed moves  (1 waiting: offer from MES)
> Veto
Offer vetoed. Mesa Verde has been told no.
```

Rival GMs make offers to us and trade with each other, so the league keeps
changing even when the owner does nothing.

## Week 9: the trade deadline [2.3]

```
=== Week 9: Herons 5-3, 2nd of 6 ===  Cap space: $3.14M   TRADE DEADLINE THIS WEEK

Your GM's briefing
  Last chance to trade this season.

  The Trade Desk closes after this week's games. Since the Odom trade, our
  safeties' coverage is up from 48.5 to 66.0. That's still 6th of 6, but now
  4 points behind Mesa Verde instead of 21.5.
```

Under G3's number check, the GM can say "4 points behind" only if the week's
facts include that gap, so the facts must grow with each task that adds to the
briefing (here 2.3).

## Week 10: too late [1.2]

```
Your order: Get Xavier Pruitt from Delta Bay for Darius Kessler.

GM: I can't. The League Office refused it:
      Trades closed after week 9, the trade deadline; it is week 10.
    We play the rest of the season with this roster.
```

A rejected move always shows the rule it broke. Here the GM passes on the
League Office's message as is.

## Week 12: an injury [3.2]

```
=== Week 12: Herons 7-4, 2nd of 6 ===  Cap space: $3.14M

Your GM's briefing
  Medical: Bryce Gaines (CB) hurt his hamstring and will miss 2 games.
  Coaching: Jonah Reyes and Hunter Vance start at corner until he's back.
```

## Week 17 and the playoffs [G6]

```
=== End of the regular season: Herons 11-6, 2nd of 6 ===

Playoffs (top 4)
  Semifinal:  Harbor City 27  Delta Bay 20
  Final:      Summit 24  Harbor City 21

SEASON SUMMARY
  Record        11-6, 2nd of 6
  Playoffs      lost in the final to Summit
  Moves         1 trade (Odom from SUM), 1 offer vetoed (MES)
  Final cap     payroll $251.86M, cap space $3.14M, never over the hard cap
  Result        Playoffs made. Championship missed.
```

The owner wins by making the playoffs and then the championship without ever
going over the hard cap.

## Any week: the org chart [4.3]

```
Org chart

Owner (you)
 └─ GM .......................... briefed you, proposed 1 trade, vetoed 0
     ├─ Analytics ............... ranked safety coverage 6th of 6
     ├─ Cap & Contracts ......... checked 3 moves, dropped 1 (hard cap)
     ├─ Scouting team ........... found 4 safety targets
     ├─ Coaching ................ set the depth chart
     └─ Medical ................. no injuries this week
```

---

## What this example assumes

These choices are built into the example. Change any of them and the roadmap
changes with it.

1. **The owner gives orders and approves moves but doesn't write trades.** In
   week 10 the owner named a trade, and the GM handled it as an order. (The
   test bench's Trades tab can already write and check a trade by hand, but
   the game has no such screen.)
2. **Trades are player for player.** Draft picks can't be traded, and there are
   no releases or free agents. (The week 6 mock-up in `ROADMAP.md` mentions
   trading "a mid-round pick", which the league doesn't have.)
3. **There is no rookie draft before week 1.** G7 adds one, and this example
   skips it, so its cap figures are the seed's. With the draft, the Herons'
   rookies would use some of the $5.52M of cap space every later step depends
   on. The standalone draft's rookie scale (`draft/roster_rules.rookie_salary`)
   pays a safety $11.0M at pick 1 and $7.1M at pick 30, so under it the Herons
   could afford only a kicker, punter or long snapper. G7 needs its own scale.
4. **The game is one season.** Ages and contract years show in the screens but
   don't affect anything after the playoffs.
5. **The top 4 of 6 teams make the playoffs,** in a semifinal and a final. The
   roadmap only says "the top teams".
6. **Approval happens twice:** once for the GM's proposal and again for any
   counteroffer.
7. **Injuries come from the simulator** and are reported by Medical, with
   Coaching resetting the depth chart.
8. **With no API key,** starting a game, the three ways to play, standings
   and the rule checks work, the briefing falls back to plain notes, and Ask
   the front office says it needs a key (all built in G2 and G3). What orders
   and proposed moves (G4) and rival GMs (G5) do without a key is still
   undecided.
