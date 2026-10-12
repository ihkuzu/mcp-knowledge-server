"""Talks raw JSON-RPC to the server over streamable HTTP: python scripts/smoke.py URL [TOKEN]"""

import sys
import time

import httpx

URL = sys.argv[1]
TOKEN = sys.argv[2] if len(sys.argv) > 2 else None
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
if TOKEN:
    HEADERS["authorization"] = f"Bearer {TOKEN}"


def wait_until_up(client: httpx.Client) -> None:
    for _ in range(30):
        try:
            client.get(URL)
            return
        except httpx.TransportError:
            time.sleep(1)
    raise SystemExit("server did not start")


def main() -> None:
    with httpx.Client(timeout=10) as client:
        wait_until_up(client)
        if TOKEN:
            assert client.post(URL, json={}).status_code == 401, "request without token was not rejected"

        def rpc(msg_id, method, params, session=None):
            headers = {**HEADERS, **({"mcp-session-id": session} if session else {})}
            body = {"jsonrpc": "2.0", "method": method, "params": params}
            if msg_id is not None:
                body["id"] = msg_id
            resp = client.post(URL, json=body, headers=headers)
            resp.raise_for_status()
            return resp

        init = rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            },
        )
        session = init.headers.get("mcp-session-id")
        rpc(None, "notifications/initialized", {}, session)
        tools = rpc(2, "tools/list", {}, session).text
        assert "run_sql" in tools, tools
        call = rpc(3, "tools/call", {"name": "run_sql", "arguments": {"query": "SELECT 1 AS ok"}}, session).text
        assert '"ok"' in call, call
        print("smoke test passed")


if __name__ == "__main__":
    main()
