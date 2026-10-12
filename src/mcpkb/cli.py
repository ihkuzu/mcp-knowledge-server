import argparse
import asyncio
import json
import sys

from .config import Settings


def _serve(args) -> None:
    from .server import build_server

    settings = Settings.from_env()
    server = build_server(settings)
    if not args.http:
        server.run()
        return
    import uvicorn

    from .http import build_app

    if not settings.token and args.host not in ("127.0.0.1", "localhost"):
        print("warning: serving on a public interface without MCPKB_TOKEN", file=sys.stderr)
    uvicorn.run(build_app(server, settings.token, args.host), host=args.host, port=args.port, log_level="warning")


def _init_db(args) -> None:
    from .sampledata import build_sample_db

    path = build_sample_db(args.path or Settings.from_env().db_path)
    print(f"wrote {path}")


def _eval(args) -> None:
    from .docs import DocIndex
    from .evaluate import evaluate

    settings = Settings.from_env()
    index = DocIndex(settings.docs_dir)
    questions = settings.docs_dir.parent / "eval" / "questions.json"
    if args.sweep:
        print("| min_score | keyword hit@1 | paraphrase hit@1 | paraphrase hit@3 | unanswerable empty |")
        print("|---|---|---|---|---|")
        for ms in (0, 2, 3, 4, 5, 6):
            g = evaluate(index, questions, ms, args.k)["groups"]
            print(
                f"| {ms} | {g['keyword']['hit@1']:.2f} | {g['paraphrase']['hit@1']:.2f} | "
                f"{g['paraphrase'][f'hit@{args.k}']:.2f} | {g['unanswerable']['correctly_empty']:.2f} |"
            )
        return
    min_score = settings.min_score if args.min_score is None else args.min_score
    print(json.dumps(evaluate(index, questions, min_score, args.k), indent=2))


async def _demo() -> None:
    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=["-m", "mcpkb", "serve"])
    async with Client(params) as client:
        tools = await client.list_tools()
        print("tools:", ", ".join(t.name for t in tools.tools))
        calls = [
            ("search_docs", {"query": "return window days", "k": 1}),
            ("run_sql", {"query": "SELECT status, COUNT(*) AS n FROM orders GROUP BY status"}),
            ("run_sql", {"query": "DELETE FROM orders"}),
        ]
        for name, arguments in calls:
            result = await client.call_tool(name, arguments)
            body = result.structured_content or result.content[0].text
            print(f"\n{name} {json.dumps(arguments)}\nerror={result.is_error}\n{json.dumps(body, indent=1)[:600]}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mcpkb", description="MCP server for documents and a read-only database")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve", help="run the server (stdio by default)")
    p.add_argument("--http", action="store_true", help="use streamable HTTP instead of stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=_serve)
    p = sub.add_parser("init-db", help="create the sample shop database")
    p.add_argument("--path")
    p.set_defaults(func=_init_db)
    p = sub.add_parser("eval", help="evaluate document search")
    p.add_argument("--min-score", type=float)
    p.add_argument("-k", type=int, default=3)
    p.add_argument("--sweep", action="store_true", help="print a table for several thresholds")
    p.set_defaults(func=_eval)
    p = sub.add_parser("demo", help="start the server over stdio and call a few tools")
    p.set_defaults(func=lambda a: asyncio.run(_demo()))
    args = parser.parse_args(argv)
    args.func(args)
