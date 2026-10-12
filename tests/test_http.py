import httpx
import pytest
from mcp import Client

from mcpkb.http import build_app
from mcpkb.server import build_server

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
}


@pytest.fixture
def app(settings):
    return build_app(build_server(settings), token="s3cret")


async def post(app, headers):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        return await client.post("/mcp", json=INIT, headers={**HEADERS, **headers})


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer wrong"}, {"authorization": "s3cret"}])
async def test_requests_without_valid_token_are_rejected(app, headers):
    resp = await post(app, headers)
    assert resp.status_code == 401 and resp.headers["www-authenticate"] == "Bearer"


async def test_valid_token_passes_through(settings):
    server = build_server(settings)
    app = build_app(server, "s3cret")
    async with server.session_manager.run():
        resp = await post(app, {"authorization": "Bearer s3cret"})
    assert resp.status_code == 200
    assert "mcp-knowledge-server" in resp.text


def test_no_token_means_no_wrapper(settings):
    server = build_server(settings)
    assert build_app(server, None).__class__.__name__ != "BearerAuth"


async def test_in_process_client_still_works(settings):
    async with Client(build_server(settings)) as client:
        assert (await client.call_tool("list_tables", {})).structured_content["result"]
