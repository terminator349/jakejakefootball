"""The League Office MCP server: read-only access to league data.

It serves the same four functions the Analytics agent called directly in
Step 1, so any MCP client (an Agno agent, Claude Desktop, the MCP Inspector)
can read the league. The functions stay in agents/tools.py, and their
docstrings become the tool descriptions the model sees.

    python -m servers.league_office    # speaks MCP over stdin/stdout

Run it from the project root so `agents` can be imported.
"""

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from agents.tools import compare_to_league, get_league_rules, get_roster, list_teams

LEAGUE_TOOLS = [list_teams, get_roster, compare_to_league, get_league_rules]

# Nothing here changes the league, so clients can call these tools freely.
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

league_office = MCPServer(
    name="League Office",
    instructions="Read-only league data for a fictional American football league: teams, "
                 "rosters, ratings, contracts and rules. Every tool returns JSON text.",
)

for tool in LEAGUE_TOOLS:
    # structured_output=False sends the JSON string as plain text content, as the
    # agent saw it in Step 1, instead of wrapping it in {"result": ...}.
    league_office.add_tool(tool, annotations=READ_ONLY, structured_output=False)


if __name__ == "__main__":
    league_office.run()
