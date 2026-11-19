---
name: front-office-memo
description: The front office's house style for writing to the owner - the weekly briefing and answers to the owner's questions - with a script that checks a memo's numbers against the facts it was written from and its length and tone. Use whenever writing something the owner will read.
---

# Front-office memo

The owner is busy and reads every word. Write so a memo can be read in under a
minute and acted on.

## House style

- **Bottom line first.** The first sentence says what happened or what to do.
- **Short.** One idea per paragraph, one to three sentences each.
- **Specific.** Name players with their position, teams by city, and give the
  number that matters, with its unit: "$5.5M of cap space", "6th of 6",
  "coverage 52". Records as 2-1, scores as ours first: "we lost 17-24".
- **Numbers from the data only.** Copy them as the data gives them. Don't work
  out new ones (differences, totals, averages, percentages) unless a tool or
  script did it for you, and don't round them differently.
- **"We" means the Herons.** Name every other team.
- **Plain words, no hype.** No "elite", "dominant", "massive", "huge",
  "incredible", "must-win" or "statement game". Say what the numbers say.
- **No hedging filler.** Skip "it's worth noting", "at the end of the day",
  "going forward". If something is uncertain, say what would settle it.

## The weekly briefing

Written at the start of each week from the week's facts.

- **Headline**: the week in one line, at most 12 words. Lead with the record or
  the result: "Herons 2-1 after Summit win; safety coverage still last".
- **Two to four paragraphs**, in this order, skipping what the facts don't have:
  1. Our record and standing, and last week's result with one or two standout
     players from our game.
  2. The other results around the league, in one sentence.
  3. Our biggest weakness: the unit, its rank, its rating against the league
     average, and who plays there.
  4. The cap space and the trade deadline, then this week's opponent and their
     record.
- **Watching**: one sentence on what the GM will watch this week, tied to the
  weakness or the opponent.
- In week 1 there's no last week and no standings: say the season starts.
- **Near the trade deadline** the facts carry a `warning`. In the deadline
  week, lead with it: it's the last chance to trade this season. If the facts
  have `since_our_trades`, say in one or two sentences what our trades did to
  that unit: "up from" its rating before "to" its rating now, its rank now,
  and how far we are from the team named now "instead of" before, with the
  numbers exactly as the facts give them.

## Answering the owner

- **Answer** in two to four sentences: the direct answer first, then the reason
  with its numbers.
- **Recommendation**: what to do next, in one or two sentences, or "None" when
  the question didn't call for one. One recommendation, not a menu.
- **Evidence**: the specific numbers behind the answer, one per line, each with
  where it came from (the specialist or the league).
- If something couldn't be found out, say so plainly in the answer.

## Checking a memo

Before it goes out, check it against the facts it was written from:

```
get_skill_script("front-office-memo", "check_memo.py", execute=True,
                 args=["--facts", "<the facts, as JSON>", "--text", "<the memo>"])
```

It lists every number in the memo that isn't in the facts, and any style
problem: a long headline, too many paragraphs or sentences, or a hype word. Fix
each one and check again. See `references/examples.md` for a good briefing and
a bad one.
