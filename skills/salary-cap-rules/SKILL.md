---
name: salary-cap-rules
description: The league's hard salary cap, roster limits and trade deadline, and how to test a signing, a cut or a trade against them, with a script that does the arithmetic. Use for any question about whether a move is legal or affordable.
---

# Salary cap rules

These are the rules the League Office enforces (`agents/rules.py`). A move that
breaks any of them is refused, so never recommend one that does.

## The rules

| Rule | Value | What it means |
| --- | --- | --- |
| Hard cap | $255M per team | Payroll must stay at or under it after every move. Going over is illegal, not taxed. There are no exceptions. |
| Roster minimum | 46 players | A trade can't leave a team below 46. |
| Roster maximum | 53 players | A trade or signing can't take a team above 53. |
| Trade deadline | after week 9 | Trades are allowed up to and including week 9, then closed for the season. |

- **Salary** is per season, in $M, and counts in full against the cap.
- **Contract years** are the seasons left, including this one. The game plays one
  season, so years matter for value, not for this season's cap.
- **There is no dead money, no bonus proration and no restructuring.** A player
  who leaves takes his whole salary off the books, and a player who arrives adds
  his whole salary. Don't talk about guarantees, cap hits or restructures: this
  league doesn't have them.
- **Both teams in a trade must be legal afterwards**, not just ours.

## How to test a move

1. Get the team's payroll and cap space from `list_teams` (or `check_cap_fit`).
   Use them exactly as given: don't round before you calculate.
2. For a **signing**, cap space after = cap space - new salary. It fits if that's
   0 or more. If not, `salary_to_clear` = new salary - cap space.
3. For a **trade**, payroll after = payroll - salary going out + salary coming in,
   for each team, and roster size after = size - players out + players in.
4. For a real trade between two league teams, `check_trade` is the final word:
   it checks every rule for both teams at once.

The script does steps 2 and 3 exactly as the League Office does (it uses the same
`cap_math`), so use it rather than doing the sums in your head:

```
get_skill_script("salary-cap-rules", "cap_check.py", execute=True,
                 args=["sign", "--payroll", "249.48", "--salary", "6.0"])
get_skill_script("salary-cap-rules", "cap_check.py", execute=True,
                 args=["trade", "--payroll", "249.48", "--roster", "48",
                       "--out", "4.1", "--in", "9.87", "--week", "3"])
```

`--out` and `--in` take one salary per player. The trade check reports payroll,
cap space and roster size after the move, and every rule it would break.

## Saying it

- Give money in $M with two decimals when the margin is tight (under $1M), and
  one decimal otherwise.
- Always say how much room is left after the move, or how much must be cleared.
- When a move doesn't fit, say what would make it fit: which salary must go, or
  the most the new player can earn.

See `references/worked-examples.md` for the common cases.
