# The simulator's units

Each unit is a weighted average of the starters' ratings at the positions
named, on the 25-99 scale (`build_lineup` in `agents/simulator.py`). "WR route
running" means the average route running of the three starting receivers.

## Offense

| Unit | Made of |
| --- | --- |
| inside run | 40% RB rushing, 10% RB speed, 35% OL run blocking, 10% OL strength, 5% TE blocking |
| outside run | 30% RB rushing, 25% RB speed, 30% OL run blocking, 15% TE blocking |
| short pass | 35% QB accuracy, 15% QB decision making, 35% receivers (60% WR route running + 40% WR hands), 15% TE receiving |
| deep pass | 30% QB arm strength, 20% QB accuracy, 35% WR speed, 15% WR route running |
| screen | 40% RB receiving, 30% RB speed, 30% OL pass blocking |
| pass block | 75% OL pass blocking, 15% OL strength, 10% RB pass protection |

## Defense

| Unit | Made of |
| --- | --- |
| run defense | 40% DL run defense, 15% DL strength, 25% LB run defense, 20% LB tackling |
| pass rush | 70% DL pass rush, 30% LB pass rush |
| short coverage | 45% CB coverage, 30% LB coverage, 25% S coverage |
| deep coverage | 40% CB coverage, 10% CB speed, 40% S coverage, 10% S speed |
| screen defense | 50% LB tackling, 25% LB coverage, 25% S tackling |
| tackling | LB, CB and S tackling, equally (computed, but no play uses it yet) |

## Single players

| Unit | Made of | Used for |
| --- | --- | --- |
| decision | QB decision making | how often he throws interceptions |
| mobility | QB mobility | avoiding sacks, scrambling |
| kick power | K kick power | field goal range |
| kick accuracy | K kick accuracy | field goals and extra points |
| punt power | P kick power | punt distance |

## One starter's share

A position's weight is shared by its starters. One safety is half of the
safeties' 40% of deep coverage, so each point of his coverage moves deep
coverage by 0.2. One of three receivers moves deep pass by a third of WR
speed's 35%: about 0.12 a point. A quarterback, alone at his position, moves
deep pass by 0.3 a point of arm strength.
