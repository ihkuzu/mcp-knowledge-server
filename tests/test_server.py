import json

import pytest
from mcp import Client

from mcpkb.server import build_server


@pytest.fixture
def server(settings):
    return build_server(settings)


async def test_tool_list_and_annotations(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_docs", "list_docs", "read_doc", "list_tables", "describe_table", "run_sql"}
    assert all(t.annotations.read_only_hint for t in tools.values())
    schema = tools["search_docs"].input_schema["properties"]
    assert schema["k"]["maximum"] == 10 and schema["query"]["maxLength"] == 300
    assert "hits" in tools["search_docs"].output_schema["properties"]


async def test_instructions_are_sent(server):
    async with Client(server) as client:
        assert "search_docs" in client.instructions


async def test_search_docs(server):
    async with Client(server) as client:
        res = await client.call_tool("search_docs", {"query": "goodwill voucher approval", "k": 2})
    assert not res.is_error
    hit = res.structured_content["hits"][0]
    assert hit["doc"] == "customer-support-playbook" and "20 EUR" in hit["text"]
    assert res.structured_content["note"] is None


async def test_search_without_hits_explains_why(server):
    async with Client(server) as client:
        res = await client.call_tool("search_docs", {"query": "parental leave"})
    assert res.structured_content["hits"] == []
    assert "do not cover" in res.structured_content["note"]


async def test_invalid_arguments_are_tool_errors(server):
    async with Client(server) as client:
        res = await client.call_tool("search_docs", {"query": "x", "k": 50})
    assert res.is_error
    assert "at least 2 characters" in res.content[0].text


async def test_list_and_read_docs(server):
    async with Client(server) as client:
        docs = (await client.call_tool("list_docs", {})).structured_content["result"]
        text = (await client.call_tool("read_doc", {"name": "deployment-process"})).content[0].text
        bad = await client.call_tool("read_doc", {"name": "../README"})
    assert len(docs) == 10
    assert "code freeze" in text
    assert bad.is_error and "list_docs" in bad.content[0].text


async def test_sql_tools(server):
    async with Client(server) as client:
        tables = (await client.call_tool("list_tables", {})).structured_content["result"]
        info = (await client.call_tool("describe_table", {"table": "orders"})).structured_content
        res = await client.call_tool("run_sql", {"query": "SELECT status, COUNT(*) FROM orders GROUP BY 1"})
    assert tables == ["customers", "order_items", "orders", "products"]
    assert info["row_count"] == 400
    assert res.structured_content["row_count"] == 3


async def test_sql_errors_reach_the_model(server):
    async with Client(server) as client:
        denied = await client.call_tool("run_sql", {"query": "DROP TABLE orders"})
        typo = await client.call_tool("run_sql", {"query": "SELECT * FROM order"})
        unknown = await client.call_tool("describe_table", {"table": "users"})
    assert denied.is_error and "only reading" in denied.content[0].text
    assert typo.is_error and "syntax error" in typo.content[0].text
    assert unknown.is_error and "available" in unknown.content[0].text


async def test_max_rows_is_capped_by_settings(settings, db_path):
    from dataclasses import replace

    server = build_server(replace(settings, max_rows=5))
    async with Client(server) as client:
        res = await client.call_tool("run_sql", {"query": "SELECT id FROM orders", "max_rows": 500})
    assert res.structured_content["row_count"] == 5 and res.structured_content["truncated"]


async def test_resources(server):
    async with Client(server) as client:
        templates = (await client.list_resource_templates()).resource_templates
        doc = await client.read_resource("docs://onboarding")
        with pytest.raises(Exception, match="unknown document"):
            await client.read_resource("docs://nope")
    assert templates[0].uri_template == "docs://{name}"
    assert doc.contents[0].text.startswith("# Onboarding")


async def test_stats_count_calls_and_errors(server):
    async with Client(server) as client:
        await client.call_tool("run_sql", {"query": "SELECT 1"})
        await client.call_tool("run_sql", {"query": "DELETE FROM orders"})
        stats = json.loads((await client.read_resource("stats://tools")).contents[0].text)
    assert stats["run_sql"]["calls"] == 2 and stats["run_sql"]["errors"] == 1


async def test_prompts(server):
    async with Client(server) as client:
        names = {p.name for p in (await client.list_prompts()).prompts}
        prompt = await client.get_prompt("answer_from_docs", {"question": "How long is probation?"})
    assert names == {"answer_from_docs", "analyze_sales"}
    assert "How long is probation?" in prompt.messages[0].content.text
