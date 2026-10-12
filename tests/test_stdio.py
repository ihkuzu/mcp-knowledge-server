import os
import sys

from mcp import Client, StdioServerParameters


async def test_server_over_stdio(db_path):
    # runs the real subprocess, so anything printed to stdout would break the protocol
    env = {**os.environ, "MCPKB_DB_PATH": str(db_path)}
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcpkb", "serve"], env=env)
    async with Client(params) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        res = await client.call_tool("run_sql", {"query": "SELECT COUNT(*) AS n FROM customers"})
    assert "run_sql" in tools
    assert res.structured_content["rows"] == [[60]]
