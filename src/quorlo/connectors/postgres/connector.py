"""Read-only Postgres metadata connector.

Reads only the system catalogs: tables, columns, comments, constraints and planner
statistics. It never selects from a user table, so no row of data is ever read.
Read-only is enforced by the driver (`conn.read_only = True` makes every transaction
READ ONLY), not just by the queries this module happens to run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Self

import psycopg
from psycopg.rows import dict_row

from quorlo.connector import ConnectionConfig, ConnectorCapabilities, ConnectorError
from quorlo.connectors.postgres.catalog import PLATFORM, Row, build_database, postgres_location
from quorlo.connectors.postgres.queries import (
    COLUMNS_SQL,
    CONSTRAINTS_SQL,
    SCHEMAS_SQL,
    SYSTEM_SCHEMAS,
    TABLES_SQL,
)
from quorlo.models import Database


class PostgresConnector:
    name: ClassVar[str] = PLATFORM
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig) -> None:
        if not config.read_only:
            raise ConnectorError("The postgres connector only supports read-only connections.")
        self._config = config
        self._conn: psycopg.Connection | None = None

    def _connection(self) -> psycopg.Connection:
        if self._conn is None:
            try:
                conn = psycopg.connect(
                    self._config.dsn.get_secret_value(),
                    row_factory=dict_row,
                    connect_timeout=self._config.options.get("connect_timeout", 10),
                    application_name="quorlo",
                )
            except psycopg.Error as exc:
                raise ConnectorError(f"Could not connect to Postgres: {exc}") from None
            # Every transaction on this connection is READ ONLY; writes fail in the server.
            conn.read_only = True
            self._conn = conn
        return self._conn

    def _run(self, queries: Sequence[tuple[str, Mapping[str, Any] | None]]) -> list[list[Row]]:
        """Run catalog queries in one read-only transaction, so they see one snapshot."""
        conn = self._connection()
        try:
            with conn.cursor() as cur:
                results = []
                for sql, params in queries:
                    cur.execute(sql, params)
                    results.append(cur.fetchall())
            return results
        except psycopg.Error as exc:
            raise ConnectorError(f"Postgres metadata query failed: {exc}") from None
        finally:
            conn.rollback()  # nothing to commit, and no transaction left open

    def test_connection(self) -> None:
        self._run([("SELECT 1 AS ok", None)])

    def list_schemas(self) -> list[str]:
        (rows,) = self._run([(SCHEMAS_SQL, {"system": list(SYSTEM_SCHEMAS)})])
        return [r["name"] for r in rows]

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        wanted = list(schemas) if schemas else None
        params = {"system": list(SYSTEM_SCHEMAS)}
        (db_rows, schema_rows) = self._run(
            [("SELECT current_database() AS name", None), (SCHEMAS_SQL, params)]
        )
        if wanted is not None:
            unknown = set(wanted) - {r["name"] for r in schema_rows}
            if unknown:
                raise ConnectorError(f"Schemas not found: {', '.join(sorted(unknown))}.")
            schema_rows = [r for r in schema_rows if r["name"] in wanted]

        params = {"schemas": [r["name"] for r in schema_rows]}
        tables, columns, constraints = self._run(
            [(TABLES_SQL, params), (COLUMNS_SQL, params), (CONSTRAINTS_SQL, params)]
        )
        return build_database(
            db_rows[0]["name"], schema_rows, tables, columns, constraints, self._location()
        )

    def _location(self) -> str:
        """Server and database from the live connection, so no credential can end up in it."""
        info = self._connection().info
        return postgres_location(info.host, info.port, info.dbname)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
