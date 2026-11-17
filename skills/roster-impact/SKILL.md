---
name: roster-impact
description: How players' ratings feed the game simulator's units (pass coverage, run defense, pass rush and the rest), which plays each unit decides, and how much replacing one starter would move a unit - with a script that measures it using the simulator itself. Use to explain why a weakness matters on the field, or to compare candidates for fixing one.
---

# Roster impact

Games are played snap by snap by the simulator (`agents/simulator.py`). It
doesn't use a player's overall: each play pits one of our **units** against one
of theirs, and each unit is a weighted average of specific ratings of the
**starters** only. Backups don't count until a starter is replaced.

## Starters

1 QB, 1 RB, 3 WR, 1 TE, 5 OL, 4 DL, 3 LB, 2 CB, 2 S, 1 K, 1 P: the best by
overall at each position. A new player only helps if he'd start.

## Which unit meets which

| Their play | Our unit that defends it | | Our play | Our unit that runs it |
| --- | --- | --- | --- | --- |
| run inside / outside | run defense | | run inside | inside run |
| short pass | short coverage | | run outside | outside run |
| deep pass, play action | deep coverage | | short pass | short pass |
| screen | screen defense | | deep pass, play action | deep pass |
| | | | screen | screen |

Every pass also sets pass rush against pass blocking for sacks. The units, and
the ratings in each, are in `references/units.md`.

## What a gap is worth

The bigger the gap between the two units, the better the play goes for the
stronger side, with diminishing returns: about the first 10 points of a gap
count almost in full, and no gap counts for more than 10. So lifting a unit
that's 20 points behind by 6 points matters less than lifting one that's 6
behind by 6. A weak unit also gets tested more: the AI play callers lean toward
the plays that work against a defense.

## Measuring a swap

To see what a candidate would do, compare him with the starter he'd replace:

```
get_skill_script("roster-impact", "unit_impact.py", execute=True,
                 args=["--position", "S",
                       "--current", "coverage=52,tackling=78,speed=81",
                       "--candidate", "coverage=83,tackling=71,speed=80"])
```

Give every rating the position has (`get_roster` lists them). The script builds
the same lineup twice with the simulator's own code, once with each player, and
reports how many points each unit moves and which plays that unit decides. That
example: deep coverage +6.15, short coverage +3.88, screen defense -0.88.

## Saying it

Name the unit and the plays: "he lifts our deep coverage by about 6 points,
which defends deep passes and play action". Mention a unit that gets worse if
it moves by more than a point. Don't promise wins: a unit is one input to each
play, with the opponent's unit, both play calls and chance.
