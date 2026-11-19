---
name: scouting
description: How the pro scouts grade a trade target A, B or C and write the note the GM reads. Use when scouting players on other teams for a trade.
---

# Scouting

The scouting team (task 4.1) finds trade targets for the GM. Plain Python does
the looking: `scout_targets` lists the players at a position on the other five
teams who would start for us, with what each adds to our units, his season,
any injury, and the best one-for-one offer his team should accept by the
league's own measure (the negotiation skill's score). The scout grades them
and writes a note on each. The GM reads the grades and notes and builds the
trades.

## Grades

- **A**: he would start for us, his team should take a one-for-one offer, the
  offer is worth at least +1.00 to us, and he's healthy. Go get him.
- **B**: he would start for us and a one-for-one deal works, but it's worth
  less than +1.00 to us; or he'd be an A but with a concern you name (age 32
  or older, the last year of his contract, a thin season so far).
- **C**: no single player of ours gets it done (`offer` is null), or he's hurt
  (`games_out` above 0). Worth knowing about, not worth chasing now.

You may grade a player lower than the numbers allow, for a reason you name.
You may never grade him higher: an A or B needs an offer and a healthy player,
and the game holds every grade to that.

`scripts/grade.py` gives the highest grade the numbers allow:

```
python scripts/grade.py --our-score 1.35 --games-out 0
python scripts/grade.py --no-offer
```

## Notes

- One or two sentences. Lead with why he fits: the rating that matters at his
  position, against the starter he'd replace (e.g. "Coverage 80, against our
  weakest safety's 48").
- Then the deal: who we'd send, and both sides' scores from the offer.
- Quote only numbers your tools gave you. Name every other team by its city,
  never its id.
- No hype: "would start for us" and the numbers, not "elite" or "game-changer".
