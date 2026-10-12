import sqlite3

import pytest

from mcpkb.database import QueryError, ReadOnlyDB


@pytest.fixture
def db(db_path):
    conn = ReadOnlyDB(db_path, timeout=0.5, max_cell_chars=20)
    yield conn
    conn.close()


def test_select(db):
    res = db.query("SELECT COUNT(*) AS n FROM orders", 10)
    assert res.columns == ["n"] and res.rows == [[400]] and not res.truncated


def test_join_and_cte(db):
    res = db.query(
        "WITH d AS (SELECT * FROM orders WHERE status = 'delivered') "
        "SELECT p.category, SUM(i.quantity * p.price) FROM d JOIN order_items i ON i.order_id = d.id "
        "JOIN products p ON p.id = i.product_id GROUP BY 1 ORDER BY 2 DESC",
        10,
    )
    assert len(res.rows) == 4


def test_recursive_cte_allowed(db):
    res = db.query("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 5) SELECT x FROM n", 10)
    assert [r[0] for r in res.rows] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "UPDATE products SET price = 0",
        "INSERT INTO products VALUES (99, 'x', 'y', 1)",
        "DROP TABLE orders",
        "CREATE TABLE t (x)",
        "PRAGMA writable_schema = ON",
        "ATTACH DATABASE ':memory:' AS other",
        "CREATE TEMP TABLE t AS SELECT 1",
    ],
)
def test_writes_and_admin_statements_are_denied(db, sql):
    with pytest.raises(QueryError, match="only reading"):
        db.query(sql, 10)


def test_only_one_statement(db):
    with pytest.raises(QueryError):
        db.query("SELECT 1; DELETE FROM orders", 10)
    assert db.query("SELECT COUNT(*) FROM orders", 1).rows == [[400]]


def test_connection_itself_is_read_only(db_path):
    # even without the authorizer the file is opened in read-only mode
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM orders")
    conn.close()


def test_row_cap(db):
    res = db.query("SELECT id FROM orders", 25)
    assert len(res.rows) == 25 and res.truncated


def test_timeout_stops_runaway_query(db):
    with pytest.raises(QueryError, match="stopped after"):
        db.query("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT COUNT(*) FROM n", 1)


def test_long_cells_are_cut(db):
    res = db.query("SELECT printf('%.100c', 'a')", 1)
    assert res.rows[0][0] == "a" * 20 + "..."


def test_blob_is_summarized(db):
    assert db.query("SELECT zeroblob(8)", 1).rows == [["<8 bytes>"]]


@pytest.mark.skipif(not hasattr(sqlite3.Connection, "setlimit"), reason="needs Python 3.11")
def test_huge_strings_hit_the_length_limit(db):
    with pytest.raises(QueryError):
        db.query("SELECT length(zeroblob(50000000))", 1)


def test_syntax_error_message(db):
    with pytest.raises(QueryError, match="no such column"):
        db.query("SELECT nope FROM orders", 1)


def test_describe(db):
    info = db.describe("order_items")
    assert [c["name"] for c in info["columns"]] == ["order_id", "product_id", "quantity"]
    assert {"column": "order_id", "references": "orders.id"} in info["foreign_keys"]
    assert len(info["sample_rows"]) == 3


def test_describe_unknown_table(db):
    with pytest.raises(QueryError, match="available: customers"):
        db.describe("users")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReadOnlyDB(tmp_path / "nope.db")


def test_metadata_still_works_after_a_denied_query(db):
    with pytest.raises(QueryError):
        db.query("DROP TABLE orders", 1)
    assert db.describe("orders")["row_count"] == 400
    assert db.tables() == ["customers", "order_items", "orders", "products"]
