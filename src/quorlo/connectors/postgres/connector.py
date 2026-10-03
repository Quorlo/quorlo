"""Read-only Postgres metadata connector.

Reads only the system catalogs: tables, columns, comments, constraints and planner
statistics. It never selects from a user table, so no row of data is ever read.
Read-only is enforced by the driver (`conn.read_only = True` makes every transaction
READ ONLY), not just by the queries this module happens to run.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import ClassVar, Self

from quorlo.connectors.base import (
    ConnectionConfig,
    ConnectorCapabilities,
    ConnectorError,
    DatabaseInfo,
    FetchStats,
)
from quorlo.connectors.postgres.catalog import PLATFORM, Row, SchemaAssembler, postgres_location
from quorlo.connectors.postgres.queries import (
    COLUMNS_SQL,
    CONSTRAINTS_SQL,
    SCHEMAS_SQL,
    SYSTEM_SCHEMAS,
    TABLES_SQL,
)
from quorlo.connectors.postgres.runner import QueryRunner
from quorlo.models import Schema

# Queries per schema, whatever the number of tables in it. A test holds this constant.
QUERIES_PER_SCHEMA = 3


class PostgresConnector:
    """Streams one schema at a time with QUERIES_PER_SCHEMA catalog queries each, plus
    one query for the schema list, all inside a single read-only snapshot."""

    name: ClassVar[str] = PLATFORM
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig) -> None:
        if not config.read_only:
            raise ConnectorError("The postgres connector only supports read-only connections.")
        self._runner = QueryRunner(config)

    @property
    def stats(self) -> FetchStats:
        return self._runner.stats

    def test_connection(self) -> None:
        with self._runner.snapshot():
            self._runner.fetch("SELECT 1 AS ok")

    def describe(self) -> DatabaseInfo:
        """From the live connection, so no credential can end up in the location."""
        info = self._runner.info
        return DatabaseInfo(
            name=info.dbname,
            platform=PLATFORM,
            location=postgres_location(info.host, info.port, info.dbname),
        )

    def list_schemas(self) -> list[str]:
        with self._runner.snapshot():
            return [row["name"] for row in self._schema_rows()]

    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
        assembler = SchemaAssembler(self._runner.info.dbname)
        with self._runner.snapshot():
            for row in self._selected(self._schema_rows(), schemas):
                params = {"schema": row["name"]}
                yield assembler.build(
                    row,
                    tables=self._runner.fetch(TABLES_SQL, params),
                    columns=self._runner.fetch(COLUMNS_SQL, params),
                    constraints=self._runner.fetch(CONSTRAINTS_SQL, params),
                )

    def _schema_rows(self) -> list[Row]:
        return self._runner.fetch(SCHEMAS_SQL, {"system": list(SYSTEM_SCHEMAS)})

    @staticmethod
    def _selected(rows: list[Row], wanted: Sequence[str] | None) -> list[Row]:
        if not wanted:
            return rows
        unknown = set(wanted) - {r["name"] for r in rows}
        if unknown:
            raise ConnectorError(f"Schemas not found: {', '.join(sorted(unknown))}.")
        return [r for r in rows if r["name"] in set(wanted)]

    def close(self) -> None:
        self._runner.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
