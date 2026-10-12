# mcp-knowledge-server

An [MCP](https://modelcontextprotocol.io) server that gives an LLM client access to a company's internal knowledge: search over policy documents, read-only SQL on a sales database, and (optionally) an inference job API. Any MCP client, such as a desktop chat app or an IDE assistant, can connect to it over stdio or HTTP and use the tools without custom glue code.

The company is fictional (Lindenhof Electronics, an online electronics shop): 10 markdown documents and a SQLite database with 60 customers, 18 products and 400 orders. The point of the project is the server side: tool design, input and output contracts, guardrails, errors the model can recover from, and tests.

```
MCP client (chat app, IDE, agent)
        │  JSON-RPC over stdio or streamable HTTP (+ bearer token)
        ▼
mcp-knowledge-server
  ├─ search_docs / list_docs / read_doc ──▶ BM25 index over markdown sections
  ├─ list_tables / describe_table / run_sql ──▶ SQLite, read-only (3 layers, see below)
  ├─ submit_job / get_job ──▶ async-inference-service HTTP API (only if configured)
  ├─ resources: docs://{name}, stats://tools
  └─ prompts: answer_from_docs, analyze_sales
```

## Tools

| Tool | What it does | Limits |
|---|---|---|
| `search_docs(query, k)` | Best matching document sections with their text and score | `k` ≤ 10, query ≤ 300 chars, weak matches are dropped |
| `list_docs()` | Document names, titles and section headings | |
| `read_doc(name)` | Full markdown of one document | Only known names, no paths |
| `list_tables()` | Tables of the shop database | |
| `describe_table(table)` | Columns, foreign keys, row count, 3 sample rows | |
| `run_sql(query, max_rows)` | One read-only SELECT | 3 s timeout, ≤ 100 rows, long cells cut at 500 chars |
| `submit_job(text, wait_seconds)` | Sends text to the [inference service](https://github.com/ihkuzu/async-inference-service) and waits up to 10 s for the result | Only registered when `MCPKB_INFERQ_URL` is set |
| `get_job(job_id)` | Status and result of a job | Id must be 32 hex chars |

Every tool has a typed input schema (pydantic, so the client sees min/max values and descriptions) and a typed output schema, so clients get structured results and not only text. Read-only tools carry `readOnlyHint`, which lets clients skip the confirmation step for them.

## Run it

```bash
pip install -e ".[dev]"
mcpkb init-db              # creates data/shop.db
mcpkb demo                 # starts the server over stdio and calls a few tools
```

### Connect a client (stdio)

Most MCP clients take a JSON config like this:

```json
{
  "mcpServers": {
    "knowledge": {
      "command": "mcpkb",
      "args": ["serve"],
      "env": { "MCPKB_DB_PATH": "/path/to/data/shop.db" }
    }
  }
}
```

### HTTP and Docker

```bash
MCPKB_TOKEN=change-me mcpkb serve --http --port 8000    # endpoint: http://localhost:8000/mcp
docker compose up --build mcp                            # same, in a container
python scripts/smoke.py http://localhost:8000/mcp change-me
```

With `MCPKB_TOKEN` set, every HTTP request needs `Authorization: Bearer <token>` (compared in constant time). Without a token the server warns when it is bound to a public interface. On localhost the SDK also checks the `Host` header against DNS rebinding.

To try the job tools with the real inference service:

```bash
MCPKB_INFERQ_URL=http://inferq-api:8000 docker compose --profile jobs up --build
```

### Settings

| Variable | Default | Meaning |
|---|---|---|
| `MCPKB_DOCS_DIR` | `data/docs` | folder with markdown files |
| `MCPKB_DB_PATH` | `data/shop.db` | SQLite file, opened read-only |
| `MCPKB_MIN_SCORE` | `5.0` | BM25 score below which a section is not returned |
| `MCPKB_SQL_TIMEOUT` | `3` | seconds before a query is interrupted |
| `MCPKB_MAX_ROWS` | `100` | hard cap on rows per query |
| `MCPKB_INFERQ_URL` | unset | base URL of the inference service, enables the job tools |
| `MCPKB_TOKEN` | unset | bearer token for HTTP mode |

## Read-only SQL in three layers

The earlier [sql-agent](https://github.com/ihkuzu/sql-agent) project checked queries with regular expressions. Here the database engine enforces it:

1. **The file is opened with `mode=ro`.** SQLite itself refuses writes, whatever the query says.
2. **An authorizer callback** allows only `SELECT`, `READ`, `FUNCTION` and `RECURSIVE` actions while a user query runs. `PRAGMA`, `ATTACH`, temp tables and every write are denied before execution, and the model gets a short explanation instead of the raw "not authorized".
3. **Resource limits.** A progress handler stops queries after the timeout, `fetchmany` caps rows, the string/blob length limit is 1 MB, and long cells are cut, so one query cannot fill the model's context.

`sqlite3` already refuses more than one statement per call. Tests cover each denied statement type, a runaway recursive query and the size limits.

## Search evaluation

`data/eval/questions.json` has 48 questions: 24 that reuse the documents' words, 16 paraphrases written the way a customer or new colleague would ask, and 8 that the documents do not answer.

```bash
mcpkb eval --sweep
```

| min_score | keyword hit@1 | paraphrase hit@1 | paraphrase hit@3 | unanswerable returns nothing |
|---|---|---|---|---|
| 0 | 0.96 | 0.31 | 0.44 | 0.00 |
| 3 | 0.96 | 0.31 | 0.44 | 0.25 |
| 4 | 0.96 | 0.31 | 0.31 | 0.50 |
| **5 (default)** | **0.96** | **0.31** | **0.31** | **0.88** |
| 6 | 0.88 | 0.31 | 0.31 | 1.00 |

What this shows:

- **BM25 is good when the question uses the documents' words and weak when it does not.** "Do you deliver to Austria?" shares no useful word with "We currently ship only to addresses in Germany". Dense embeddings fix much of this; in [rag-doc-qa](https://github.com/ihkuzu/rag-doc-qa) they raised paraphrase hit@1 from 0.60 to 0.93. I kept this server dependency-free and the index behind one `search()` method, so swapping in embeddings or a hybrid is a local change.
- **The threshold mostly removes wrong answers.** At 5, seven of eight unanswerable questions return nothing. Half of the paraphrases also return nothing, but none of them had the right section on top before (two had it at rank 2 or 3). When nothing matches, the tool says so and tells the model to retry with other words; I have not measured how often a model then finds the section.
- **The threshold was picked on these same 48 questions**, so 0.88 is optimistic. A held-out set would be the honest next step.
- **The eval found a bug.** My first hand-written stemmer turned "invoices" into "invoic" but left "invoice" alone, so the two never matched. It now uses the Snowball stemmer.

## Design notes

- **Errors are tool results, not crashes.** Anticipated failures (bad SQL, unknown table, service down) raise `ToolError`, which the client receives as `isError: true` with a message the model can act on: "unknown table 'users', available: customers, order_items, orders, products". Unexpected exceptions are logged with a traceback and the model only sees a generic message.
- **The server tells the model how to use it.** Server instructions and tool descriptions say when to use which tool, that search matches words and not meaning, and that "not covered" is a valid answer.
- **Stdout belongs to the protocol.** In stdio mode anything printed to stdout corrupts JSON-RPC, so the audit log (one JSON line per tool call with duration and outcome) goes to stderr. A test starts the real subprocess to catch this.
- **Long jobs do not block.** `submit_job` waits at most 10 s and otherwise returns the job id, so the model can call `get_job` later instead of holding the connection.
- **Blocking work runs in a thread.** SQL runs through `anyio.to_thread` with a lock around the connection, so a slow query does not stall other requests.
- Built on version 2 of the official Python SDK (`MCPServer`, which was called `FastMCP` in 1.x).

## Limitations

- Keyword search only; see the evaluation above.
- One static bearer token, no per-user permissions. A real deployment would use the SDK's OAuth support and filter rows by user.
- No rate limiting per client.
- No test with a real LLM driving the tools in this repo; the tests check the contracts the model relies on.
- Small fictional data.

## Tests

```bash
pytest -q        # 60 tests, about 5 s, no network needed
```

They cover the index and stemming, every denied SQL statement type, timeouts and size caps, all tools and resources through an in-process MCP client, input validation errors, the job tools against a mocked HTTP service, the bearer token check, and the server over a real stdio subprocess. CI runs them on Python 3.10 and 3.12 and does an HTTP smoke test against the Docker image.

## License

MIT
