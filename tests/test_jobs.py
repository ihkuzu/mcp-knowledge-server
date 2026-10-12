import httpx
import pytest
from mcp import Client

from mcpkb.jobs import InferqClient, JobError
from mcpkb.server import build_server

JOB_ID = "a" * 32


def fake_service(polls_until_done=2):
    state = {"gets": 0, "headers": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v1/jobs":
            state["headers"] = request.headers
            return httpx.Response(202, json={"id": JOB_ID, "status": "queued", "attempts": 0})
        if request.url.path == f"/v1/jobs/{JOB_ID}":
            state["gets"] += 1
            if state["gets"] < polls_until_done:
                return httpx.Response(200, json={"id": JOB_ID, "status": "running", "attempts": 1})
            return httpx.Response(
                200, json={"id": JOB_ID, "status": "done", "attempts": 1, "result": {"label": "positive", "score": 0.9}}
            )
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler), state


async def test_submit_and_wait():
    transport, state = fake_service()
    client = InferqClient("http://svc", transport=transport)
    job = await client.submit("hello", idempotency_key="k1")
    done = await client.wait(job["id"], seconds=2, interval=0.01)
    assert done["status"] == "done" and state["headers"]["idempotency-key"] == "k1"


async def test_wait_returns_unfinished_job_after_timeout():
    transport, _ = fake_service(polls_until_done=10_000)
    client = InferqClient("http://svc", transport=transport)
    job = await client.wait(JOB_ID, seconds=0.05, interval=0.01)
    assert job["status"] == "running"


async def test_errors_become_job_errors():
    transport, _ = fake_service()
    client = InferqClient("http://svc", transport=transport)
    with pytest.raises(JobError, match="not found"):
        await client.get("b" * 32)

    def down(request):
        raise httpx.ConnectError("refused")

    client = InferqClient("http://svc", transport=httpx.MockTransport(down))
    with pytest.raises(JobError, match="unreachable"):
        await client.get(JOB_ID)


async def test_job_tools_through_mcp(settings):
    transport, _ = fake_service()
    server = build_server(settings, inferq=InferqClient("http://svc", transport=transport))
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        res = await client.call_tool("submit_job", {"text": "great product", "wait_seconds": 2})
        bad = await client.call_tool("get_job", {"job_id": "../../admin"})
        missing = await client.call_tool("get_job", {"job_id": "b" * 32})
    assert {"submit_job", "get_job"} <= names
    assert res.structured_content["status"] == "done"
    assert res.structured_content["result"]["label"] == "positive"
    assert bad.is_error and "pattern" in bad.content[0].text
    assert missing.is_error and "not found" in missing.content[0].text
