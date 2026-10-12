import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# the only actions a user query may perform, everything else is denied by SQLite itself
ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}
DENIED_HINT = "only reading the shop tables is allowed, writes, PRAGMA and ATTACH are blocked"


class QueryError(RuntimeError):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool
    elapsed_ms: float


class ReadOnlyDB:
    def __init__(self, path: Path, timeout: float = 3.0, max_cell_chars: int = 500):
        if not path.exists():
            raise FileNotFoundError(f"database not found: {path} (run 'mcpkb init-db')")
        self.timeout = timeout
        self.max_cell_chars = max_cell_chars
        self._deadline = float("inf")
        self._lock = threading.Lock()
        self._meta_lock = threading.Lock()
        uri = f"{path.resolve().as_uri()}?mode=ro"
        # user queries get their own connection with a permanent authorizer, metadata lookups use the other
        self._meta = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._conn.set_authorizer(self._authorize)
        self._conn.set_progress_handler(self._expired, 1000)
        if hasattr(self._conn, "setlimit"):
            # caps the size of any single string or blob a query can build
            self._conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)

    def _expired(self) -> int:
        return 1 if time.monotonic() > self._deadline else 0

    @staticmethod
    def _authorize(action, arg1, arg2, db_name, source) -> int:
        return sqlite3.SQLITE_OK if action in ALLOWED else sqlite3.SQLITE_DENY

    def close(self) -> None:
        self._conn.close()
        self._meta.close()

    def tables(self) -> list[str]:
        with self._meta_lock:
            return self._tables()

    def _tables(self) -> list[str]:
        rows = self._meta.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]

    def describe(self, table: str) -> dict:
        with self._meta_lock:
            tables = self._tables()
            if table not in tables:
                raise QueryError(f"unknown table '{table}', available: {', '.join(tables)}")
            m = self._meta
            cols = [{"name": r[1], "type": r[2] or ""} for r in m.execute(f'PRAGMA table_info("{table}")')]
            fks = [
                {"column": r[3], "references": f"{r[2]}.{r[4]}"}
                for r in m.execute(f'PRAGMA foreign_key_list("{table}")')
            ]
            count = m.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            sample = m.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
        return {
            "table": table,
            "columns": cols,
            "foreign_keys": fks,
            "row_count": count,
            "sample_rows": [list(r) for r in sample],
        }

    def _cell(self, value):
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        if isinstance(value, str) and len(value) > self.max_cell_chars:
            return value[: self.max_cell_chars] + "..."
        return value

    def query(self, sql: str, max_rows: int) -> QueryResult:
        with self._lock:
            return self._query(sql, max_rows)

    def _query(self, sql: str, max_rows: int) -> QueryResult:
        start = time.monotonic()
        self._deadline = start + self.timeout
        try:
            cur = self._conn.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
            columns = [d[0] for d in cur.description or []]
        except (sqlite3.Error, sqlite3.Warning) as error:
            message = str(error)
            if "interrupted" in message:
                message = f"query stopped after {self.timeout:g}s, add filters or a LIMIT"
            elif "not authorized" in message:
                message = DENIED_HINT
            raise QueryError(message) from error
        finally:
            self._deadline = float("inf")
        return QueryResult(
            columns,
            [[self._cell(v) for v in r] for r in rows[:max_rows]],
            len(rows) > max_rows,
            round((time.monotonic() - start) * 1000, 2),
        )
