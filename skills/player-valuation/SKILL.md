---
name: player-valuation
description: How to judge what a player is worth in this league - his market value at his position and rating, whether his contract is a bargain or an overpay, and what his age means - with a script that prices any player from the league's own salaries. Use when comparing players, judging a contract or picking a target.
---

# Player valuation

A player's value here is what the league pays for his position and rating, set
against what he actually earns. Ratings run from 25 to 99; a player's overall is
the average of his position's skill ratings.

## Market value

League salaries follow one curve per position: about $1.0M at an overall of 55
or below, rising with the square of the rating above 55, so the best players
cost far more than the good ones. Quarterbacks, defensive linemen and receivers
cost the most at the same rating; kickers and punters the least.

`value_player.py` fits that curve to every veteran contract in the league
(players 24 and older; 23 and under are on rookie deals) and prices a player:

```
get_skill_script("player-valuation", "value_player.py", execute=True,
                 args=["--position", "S", "--overall", "74", "--salary", "4.5",
                       "--age", "27", "--years", "3"])
```

It returns the market value, the surplus (market value minus salary, per season
and over the contract) and a verdict:

- **bargain**: earns at least 20% less than the market (or $1M+ less),
- **fair**: within that band,
- **overpaid**: earns at least 20% more (or $1M+ more).

Run it for each player you compare rather than estimating. Cite the market value
and the surplus with the player's actual salary.

## Where the value is

Veterans here are paid almost exactly on the curve: every veteran contract in
the league comes out "fair". So a bargain comes from one of two places:

1. **A rookie deal** (23 and under): paid about the minimum whatever his rating.
2. **The rating the job needs.** Salaries are priced on overall, but a unit only
   uses some ratings (see `roster-impact`). A safety with 85 coverage and 60
   tackling costs the same as one with 60 coverage and 85 tackling, but only the
   first fixes a pass-coverage hole. Pass that rating as `--key`, its name and
   value: `--key coverage=88` (the value alone, `--key 88`, works too). The script
   prices the player as if his overall were that rating (`value_for_the_job`).
   A job surplus well above zero is a player who's better at the job than he's
   paid for; well below zero, he's paid for ratings the job doesn't use.

Our own Theo Strickland is the example: overall 70 on $4.1M is fair, but his
coverage is 52, worth about $1.0M as a coverage safety.

## Age

- **23 and under**: on a rookie deal, so cheap whatever his rating. That's real
  surplus, but it won't last past his contract.
- **24 to 29**: his prime. Ratings hold.
- **30 and over**: the league's history shows older players miss more games:
  last season, about 0.4 more games for every year past 29. Injuries in the
  simulator arrive with task 3.2; until then, say it's a risk, not a certainty.

## Contract years

Years left include this season. More years on a bargain is better; more years
on an overpay is worse. A one-year deal is the easiest to move.

## Judging a fit

Value alone doesn't fix a weakness: a player must be better at the ratings that
weakness is made of. The `roster-impact` skill says which ratings make up each
unit and how much a player would move it. Use both: the target is the player
who moves the weak unit most for the salary we can fit (see `salary-cap-rules`).

## Saying it

Give market value and salary in $M with one decimal, the surplus with its sign,
and the verdict in plain words: "earns $4.1M against a market value of $6.3M, a
$2.2M bargain".
