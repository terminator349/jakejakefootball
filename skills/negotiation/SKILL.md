---
name: negotiation
description: How the league's general managers score a trade from their own side, so you can build an offer the other team will accept and judge a counteroffer. Use before proposing a trade, or when another team answers or makes an offer.
---

# Negotiation

Every GM in this league judges a trade the same way: by what it does for its
own team. The Trade Desk's `evaluate_trade` already gives each side's
**appraisal**, so read it there; the script below scores a what-if from the
numbers.

## How a team scores a trade

```
score = market value gained - 0.5 x salary taken on + 0.3 x unit points
```

- **Market value gained**: the market value of the players a team gets minus
  those it gives, in $M per season (the player-valuation skill's formula).
  `market_value_change` in the evaluation.
- **Salary taken on** counts half: money matters, but less than talent.
  `salary_change` in the evaluation; negative when a team sheds salary.
- **Unit points**: how far the trade moves the team's simulator units (deep
  coverage, run defense, ...), added up. Tackling doesn't count: no play uses
  it. A player who would start at a weak position is worth far more than his
  market value alone.

A team **accepts** a trade that scores at least its **margin** (0.25 at
normal difficulty), **counters** one that falls short by less than 6, asking
for one more player, and **rejects** the rest. A rival making an offer of its
own wants 0.5 more than its margin.

## Building an offer they'll take

1. Find their side in `evaluate_trade`: `teams.<their id>.appraisal`.
2. If its verdict is `accept`, the offer works as it stands. Don't give more
   than you need to.
3. If it's short, add value they score: a player who would **start for them
   at one of their weak positions** scores best, because it adds unit points
   as well as market value. A backup at a position they're deep at adds
   little. Taking salary back from them also helps them (half its amount).
4. Re-evaluate until their appraisal reaches `accept` and ours is still worth
   it. A trade both sides score above their margin is the one that happens.

The best trades swap strength for need: we give up a good player at a
position where we're deep, they give up one where they are, and both teams'
units improve.

## Judging a counter or an offer

- Read **our** appraisal. Positive means the trade is good for us by the same
  measure every team uses; recommend it only if it is, and if the players it
  sends away aren't protected by one of the owner's orders.
- A counter asks for one more of our players. Check which unit he plays in:
  losing a starter shows as negative unit points on our side.
- Never accept or recommend a trade the league rules refuse.

## The script

```
python scripts/appraise.py --market-value-change 4.08 --salary-change 3.46 --unit-points 9.63
```

Prints the score, the margin and the verdict, so you can test a what-if (one
more player, a different player) from the evaluation's numbers without doing
the sums yourself.
