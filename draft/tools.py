"""Cap tools for the Draft GM agent.

Same cap_math as agents/tools.check_cap_fit and validate_cap_compliance (the
Cap & Contracts agent's tools), applied to the draft's in-memory teams instead
of the SQLite league, so a prospective pick is judged by the same rule and
reported in the same shape. build_cap_tools binds the two functions to one
draft's teams_by_id, for build_draft_agent.
"""

import json
from typing import TYPE_CHECKING

from agents.tools import cap_math

if TYPE_CHECKING:
    from draft.team import Team


def build_cap_tools(teams_by_id: dict[str, "Team"], cap: float) -> list:
    def check_cap_fit(team_id: str, new_salary: float) -> str:
        """Check whether drafting a player at a given rookie salary ($M per season) fits
        under one team's hard salary cap, and if not, how much salary is still missing.

        Args:
            team_id: three-letter team id, e.g. "HAR".
            new_salary: the prospective rookie salary in $M per season.
        """
        team = teams_by_id.get(team_id.upper())
        if team is None:
            return json.dumps({"error": f"Unknown team_id {team_id!r}. Valid ids: {list(teams_by_id)}"})
        return json.dumps({"team_id": team.id, **cap_math(team.payroll(), new_salary, cap)})

    def validate_cap_compliance() -> str:
        """Check every team's current payroll against the hard salary cap and report
        which teams, if any, are over it."""
        teams = []
        for team in teams_by_id.values():
            payroll = team.payroll()
            teams.append({"team_id": team.id, "payroll": round(payroll, 2),
                          "cap_space": round(cap - payroll, 2), "over_cap": payroll > cap})
        over = [t for t in teams if t["over_cap"]]
        return json.dumps({"salary_cap": cap, "all_teams_compliant": not over,
                           "teams_over_cap": over, "teams": teams})

    return [check_cap_fit, validate_cap_compliance]
