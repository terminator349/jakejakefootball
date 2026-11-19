"""The League Office MCP server: league data, cap checks and the league rules.

It serves the four functions the Analytics agent called directly in task 0.2,
plus check_trade (task 1.2), which says whether a trade is legal and which
rules it breaks, and validate_cap_compliance/check_cap_fit (task 1.3), which
the Cap & Contracts agent and the Draft GM use to judge a move against the
hard cap. Every tool is read-only: making a trade belongs to the Trade Desk
(task 2.1, servers/trade_desk.py), which calls agents.rules.make_trade_in. The
functions stay in agents/tools.py, and their docstrings become the tool
descriptions the model sees.

    python -m servers.league_office                         # the default league, data/league.db
    python -m servers.league_office --db saves/herons.db    # a saved game (task G1)

Run it from the project root so `agents` can be imported.
"""

import argparse
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from agents import league_db
from agents.tools import (check_cap_fit, check_trade, compare_to_league, get_depth_chart,
                          get_injury_report, get_league_rules, get_roster, get_team_tendencies,
                          list_teams, set_depth_chart, validate_cap_compliance)

LEAGUE_TOOLS = [list_teams, get_roster, compare_to_league, get_league_rules, check_trade,
                validate_cap_compliance, check_cap_fit, get_depth_chart, set_depth_chart,
                get_injury_report, get_team_tendencies]

# Every tool but set_depth_chart only reads the league, so clients can call those freely.
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=False)

league_office = MCPServer(
    name="League Office",
    instructions="League data for a fictional American football league: teams, rosters, "
                 "ratings, contracts, rules, hard-cap checks, a check of whether a trade is "
                 "legal, the depth chart and injury report, and team tendencies. Every tool "
                 "but set_depth_chart is read-only; every tool returns JSON text.",
)

for tool in LEAGUE_TOOLS:
    # structured_output=False sends the JSON string as plain text content, as the
    # agent saw it in task 0.2, instead of wrapping it in {"result": ...}.
    annotations = WRITE if tool is set_depth_chart else READ_ONLY
    league_office.add_tool(tool, annotations=annotations, structured_output=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The League Office MCP server (stdio).")
    parser.add_argument("--db", type=Path, help="league database to serve, e.g. a save file")
    args = parser.parse_args()
    if args.db:
        if not args.db.exists():
            sys.exit(f"No league database at {args.db}")
        league_db.connect(args.db).close()  # fail now, not on the first tool call, if it's outdated
        league_db.DB_FILE = args.db
    league_office.run()
