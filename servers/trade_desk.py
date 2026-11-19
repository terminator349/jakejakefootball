"""The Trade Desk MCP server: proposing, evaluating and making trades (task 2.1).

The League Office is read-only; this is the one server that changes rosters.
Teams evaluate a trade, propose it, and the team it's offered to accepts,
rejects or counters it. Every proposal is checked against the 1.2 rules when
it's made and again when it's accepted, and only an accepted proposal moves
players. The logic lives in agents/trade_desk.py; the functions' docstrings
become the tool descriptions the model sees.

    python -m servers.trade_desk                         # the default league, data/league.db
    python -m servers.trade_desk --db saves/herons.db    # a saved game (task G1)

Run it from the project root so `agents` can be imported.
"""

import argparse
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from agents import league_db
from agents.trade_desk import READ_TOOLS, TRADE_TOOLS, WRITE_TOOLS

# Reading and evaluating changes nothing. Proposing, countering and withdrawing only
# change the proposals. Accepting moves players and can't be undone.
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                         open_world_hint=False)
MOVES_PLAYERS = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False,
                                open_world_hint=False)

trade_desk = MCPServer(
    name="Trade Desk",
    instructions="Trades for a fictional American football league. Evaluate a trade, propose it to "
                 "another team, and answer the proposals made to your team: accept, reject or counter. "
                 "Every proposal is checked against the league rules (roster size, hard cap, trade "
                 "deadline), and players move only when the receiving team accepts. Every tool returns "
                 "JSON text.",
)

for tools, annotations in ((READ_TOOLS, READ_ONLY), (WRITE_TOOLS, WRITES), (TRADE_TOOLS, MOVES_PLAYERS)):
    for tool in tools:
        # Plain JSON text content, as the League Office sends it.
        trade_desk.add_tool(tool, annotations=annotations, structured_output=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The Trade Desk MCP server (stdio).")
    parser.add_argument("--db", type=Path, help="league database to serve, e.g. a save file")
    args = parser.parse_args()
    if args.db:
        if not args.db.exists():
            sys.exit(f"No league database at {args.db}")
        league_db.connect(args.db).close()  # fail now, and upgrade an older save, before the first call
        league_db.DB_FILE = args.db
    trade_desk.run()
