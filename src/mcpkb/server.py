from contextlib import asynccontextmanager
from typing import Annotated

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .audit import Audit
from .config import Settings
from .database import QueryError, ReadOnlyDB
from .docs import DocIndex
from .jobs import InferqClient, JobError

INSTRUCTIONS = """\
Tools for the internal knowledge of Lindenhof Electronics, a fictional online electronics shop.
Use search_docs for policies and processes and quote the document and section you used.
Use list_tables, describe_table and run_sql for numbers about customers, products and orders.
search_docs matches words, not meaning, so retry with other wording before giving up.
If it still returns no hits, say that the documents do not cover the question instead of guessing.
"""
NO_HITS = (
    "No section matched well enough. Try again with words the documents would use or check list_docs. "
    "If that finds nothing either, say the documents do not cover it."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)


class DocHit(BaseModel):
    doc: str
    title: str
    section: str
    score: float
    text: str


class SearchResult(BaseModel):
    query: str
    hits: list[DocHit]
    note: str | None = None


class DocInfo(BaseModel):
    name: str
    title: str
    sections: list[str]


class Column(BaseModel):
    name: str
    type: str


class ForeignKey(BaseModel):
    column: str
    references: str


class TableInfo(BaseModel):
    table: str
    columns: list[Column]
    foreign_keys: list[ForeignKey]
    row_count: int
    sample_rows: list[list]


class SqlResult(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    elapsed_ms: float


class JobView(BaseModel):
    id: str
    status: str
    result: dict | None = None
    error: str | None = None
    attempts: int = 0


def build_server(settings: Settings | None = None, inferq: InferqClient | None = None) -> MCPServer:
    settings = settings or Settings.from_env()
    index = DocIndex(settings.docs_dir)
    db = ReadOnlyDB(settings.db_path, settings.sql_timeout, settings.max_cell_chars)
    if inferq is None and settings.inferq_url:
        inferq = InferqClient(settings.inferq_url, settings.http_timeout)
    audit = Audit()

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield {}
        finally:
            db.close()
            if inferq:
                await inferq.close()

    mcp = MCPServer("mcp-knowledge-server", version=__version__, instructions=INSTRUCTIONS, lifespan=lifespan)

    @mcp.tool(annotations=READ_ONLY)
    def search_docs(
        query: Annotated[str, Field(min_length=2, max_length=300, description="What to look for, in plain words")],
        k: Annotated[int, Field(ge=1, le=10, description="Number of sections to return")] = 4,
    ) -> SearchResult:
        """Search the internal documents and return the best matching sections with their text."""
        with audit.track("search_docs", query=query):
            hits = index.search(query, k=k, min_score=settings.min_score)
            note = None if hits else NO_HITS
            return SearchResult(query=query, hits=[DocHit(**vars(h)) for h in hits], note=note)

    @mcp.tool(annotations=READ_ONLY)
    def list_docs() -> list[DocInfo]:
        """List all documents with their section headings."""
        with audit.track("list_docs"):
            return [DocInfo(**d) for d in index.list_docs()]

    @mcp.tool(annotations=READ_ONLY)
    def read_doc(name: Annotated[str, Field(max_length=64, description="Document name from list_docs")]) -> str:
        """Return the full markdown of one document."""
        with audit.track("read_doc", name=name):
            try:
                return index.read(name)
            except KeyError:
                raise ToolError(f"unknown document '{name}', call list_docs for valid names") from None

    @mcp.tool(annotations=READ_ONLY)
    def list_tables() -> list[str]:
        """List the tables of the read-only shop database."""
        with audit.track("list_tables"):
            return db.tables()

    @mcp.tool(annotations=READ_ONLY)
    def describe_table(table: Annotated[str, Field(max_length=64)]) -> TableInfo:
        """Show columns, foreign keys, row count and three sample rows of a table."""
        with audit.track("describe_table", table=table):
            try:
                return TableInfo(**db.describe(table))
            except QueryError as error:
                raise ToolError(str(error)) from None

    @mcp.tool(annotations=READ_ONLY)
    async def run_sql(
        query: Annotated[str, Field(min_length=1, max_length=4000, description="One SQLite SELECT statement")],
        max_rows: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> SqlResult:
        """Run one read-only SQL query on the shop database. Writes, PRAGMA and ATTACH are rejected."""
        with audit.track("run_sql", query=query):
            try:
                res = await anyio.to_thread.run_sync(db.query, query, min(max_rows, settings.max_rows))
            except QueryError as error:
                raise ToolError(f"query failed: {error}") from None
            return SqlResult(
                columns=res.columns,
                rows=res.rows,
                row_count=len(res.rows),
                truncated=res.truncated,
                elapsed_ms=res.elapsed_ms,
            )

    if inferq is not None:

        @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, openWorldHint=False))
        async def submit_job(
            text: Annotated[str, Field(min_length=1, max_length=20000)],
            wait_seconds: Annotated[float, Field(ge=0, le=10, description="How long to wait for the result")] = 2,
            idempotency_key: Annotated[str | None, Field(max_length=128)] = None,
        ) -> JobView:
            """Send a text to the inference service. Returns the result if it is ready in time, else the job id."""
            with audit.track("submit_job", chars=len(text)):
                try:
                    job = await inferq.submit(text, idempotency_key)
                    if wait_seconds > 0:
                        job = await inferq.wait(job["id"], wait_seconds)
                except JobError as error:
                    raise ToolError(str(error)) from None
                return JobView(**job)

        @mcp.tool(annotations=READ_ONLY)
        async def get_job(job_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]) -> JobView:
            """Look up the status and result of an inference job."""
            with audit.track("get_job", job_id=job_id):
                try:
                    return JobView(**await inferq.get(job_id))
                except JobError as error:
                    raise ToolError(str(error)) from None

    @mcp.resource("docs://{name}", mime_type="text/markdown")
    def doc_resource(name: str) -> str:
        """A document as markdown."""
        try:
            return index.read(name)
        except KeyError:
            raise ResourceNotFoundError(f"unknown document '{name}'") from None

    @mcp.resource("stats://tools", mime_type="application/json")
    def tool_stats() -> dict:
        """Call counts, errors and average latency per tool since start."""
        return audit.snapshot()

    @mcp.prompt()
    def answer_from_docs(question: str) -> str:
        """Answer a policy question using only the documents."""
        return (
            f"Answer the question below using search_docs. Cite the document and section for every claim. "
            f"If nothing relevant is found, say so.\n\nQuestion: {question}"
        )

    @mcp.prompt()
    def analyze_sales(question: str) -> str:
        """Answer a data question with the read-only database."""
        return (
            "Look at the tables with list_tables and describe_table before writing SQL. "
            "Use run_sql, check the result and show the final query with the answer. "
            "Revenue only counts delivered orders, see the order-status-glossary document.\n\n"
            f"Question: {question}"
        )

    mcp.audit = audit
    return mcp
