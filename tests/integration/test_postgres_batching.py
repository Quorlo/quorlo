"""The Postgres connector fetches in fixed-size batches per schema, from one snapshot."""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from quorlo.connector import ConnectionConfig
from quorlo.connectors.postgres import QUERIES_PER_SCHEMA, PostgresConnector

DSN = os.environ.get("QUORLO_TEST_DSN")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="QUORLO_TEST_DSN is not set"),
]

SCHEMA_LIST_QUERIES = 1


def admin(statement: sql.Composable | str) -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(statement)


@pytest.fixture
def schemas_of_size():
    """Create throwaway schemas with a given number of tables; drop them afterwards."""
    created: list[str] = []

    def create(name: str, tables: int) -> str:
        created.append(name)
        admin(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        for i in range(tables):
            admin(
                sql.SQL(
                    "CREATE TABLE {}.{} (id integer PRIMARY KEY, note text, at timestamptz)"
                ).format(sql.Identifier(name), sql.Identifier(f"t{i}"))
            )
        return name

    yield create
    for name in created:
        admin(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))


def queries_to_scan(schema: str) -> tuple[int, int]:
    with PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN))) as connector:
        (scanned,) = connector.iter_schemas([schema])
        return connector.stats.queries, len(scanned.tables)


def test_query_count_per_schema_does_not_grow_with_tables(schemas_of_size):
    small = schemas_of_size("qtest_small", tables=1)
    large = schemas_of_size("qtest_large", tables=60)

    small_queries, small_tables = queries_to_scan(small)
    large_queries, large_tables = queries_to_scan(large)

    assert (small_tables, large_tables) == (1, 60)
    assert small_queries == large_queries == SCHEMA_LIST_QUERIES + QUERIES_PER_SCHEMA


def test_query_count_grows_only_with_schemas(schemas_of_size):
    names = [schemas_of_size(f"qtest_many_{i}", tables=2) for i in range(4)]
    with PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN))) as connector:
        scanned = list(connector.iter_schemas(names))
        assert len(scanned) == 4
        assert connector.stats.queries == SCHEMA_LIST_QUERIES + 4 * QUERIES_PER_SCHEMA
        assert connector.stats.rows > 0


def test_schemas_stream_from_one_snapshot(schemas_of_size):
    first = schemas_of_size("qtest_snap_a", tables=1)
    second = schemas_of_size("qtest_snap_b", tables=1)
    with PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN))) as connector:
        stream = connector.iter_schemas([first, second])
        assert next(stream).name == first
        # Another session changes the second schema while the scan is mid-stream.
        admin(sql.SQL("CREATE TABLE {}.late (id integer)").format(sql.Identifier(second)))
        later = next(stream)
        assert later.name == second
        assert [t.name for t in later.tables] == ["t0"]  # the scan's snapshot predates it


def test_describe_issues_no_query():
    with PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN))) as connector:
        info = connector.describe()
        assert info.name == "quorlo_demo"
        assert connector.stats.queries == 0


def test_abandoning_a_stream_after_close_is_clean(schemas_of_size):
    name = schemas_of_size("qtest_abandon", tables=1)
    connector = PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN)))
    stream = connector.iter_schemas([name, "retail_raw"])
    next(stream)
    connector.close()
    stream.close()  # must not raise on the closed connection
