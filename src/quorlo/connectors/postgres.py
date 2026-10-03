"""Read-only Postgres metadata connector.

Reads only the system catalogs: tables, columns, comments, constraints and planner
statistics. It never selects from a user table, so no row of data is ever read.
Read-only is enforced by the driver (`conn.read_only = True` makes every transaction
READ ONLY), not just by the queries this module happens to run.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, ClassVar, Self

import psycopg
from psycopg.rows import dict_row

from quorlo.connector import ConnectionConfig, ConnectorCapabilities, ConnectorError
from quorlo.models import (
    Column,
    Database,
    DataType,
    ForeignKey,
    Schema,
    Table,
    TableKind,
    TableRef,
    TypeKind,
)

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

_SCHEMAS_SQL = """
SELECT n.nspname AS name, obj_description(n.oid, 'pg_namespace') AS description
FROM pg_namespace n
WHERE n.nspname <> ALL(%(system)s::text[])
  AND n.nspname NOT LIKE 'pg\\_temp\\_%%'
  AND n.nspname NOT LIKE 'pg\\_toast\\_temp\\_%%'
ORDER BY n.nspname
"""

# Partitions are skipped; their partitioned parent (relkind 'p') represents them.
_TABLES_SQL = """
SELECT n.nspname AS schema, c.relname AS name, c.relkind AS relkind,
       obj_description(c.oid, 'pg_class') AS description,
       c.reltuples::bigint AS reltuples
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT c.relispartition
  AND n.nspname = ANY(%(schemas)s::text[])
ORDER BY n.nspname, c.relname
"""

_COLUMNS_SQL = """
SELECT n.nspname AS schema, c.relname AS table, a.attnum AS ordinal, a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS type, t.typtype AS typtype,
       NOT a.attnotnull AS nullable,
       col_description(c.oid, a.attnum) AS description,
       pg_get_expr(d.adbin, d.adrelid) AS default
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT c.relispartition
  AND n.nspname = ANY(%(schemas)s::text[])
ORDER BY n.nspname, c.relname, a.attnum
"""

_CONSTRAINTS_SQL = """
SELECT con.conname AS name, con.contype AS type, n.nspname AS schema, c.relname AS table,
       ARRAY(SELECT a.attname::text FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS columns,
       fn.nspname AS ref_schema, fc.relname AS ref_table,
       ARRAY(SELECT a.attname::text FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum
             ORDER BY k.ord) AS ref_columns
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE con.contype IN ('p', 'u', 'f')
  AND n.nspname = ANY(%(schemas)s::text[])
ORDER BY n.nspname, c.relname, con.conname
"""

_RELKINDS = {
    "r": TableKind.TABLE,
    "p": TableKind.TABLE,
    "v": TableKind.VIEW,
    "m": TableKind.MATERIALIZED_VIEW,
    "f": TableKind.FOREIGN,
}

_TYPE_KINDS = {
    TypeKind.STRING: {
        "text",
        "character varying",
        "character",
        "varchar",
        "char",
        "bpchar",
        "name",
        "citext",
    },
    TypeKind.INTEGER: {"smallint", "integer", "bigint", "int2", "int4", "int8"},
    TypeKind.DECIMAL: {"numeric", "decimal", "money"},
    TypeKind.FLOAT: {"real", "double precision", "float4", "float8"},
    TypeKind.BOOLEAN: {"boolean", "bool"},
    TypeKind.DATE: {"date"},
    TypeKind.TIME: {"time without time zone", "time with time zone"},
    TypeKind.TIMESTAMP: {"timestamp without time zone", "timestamp with time zone"},
    TypeKind.INTERVAL: {"interval"},
    TypeKind.BINARY: {"bytea"},
    TypeKind.JSON: {"json", "jsonb"},
    TypeKind.UUID: {"uuid"},
}
_KIND_BY_NAME = {name: kind for kind, names in _TYPE_KINDS.items() for name in names}
_MODIFIERS = re.compile(r"\(([^)]*)\)")


def parse_type(raw: str, typtype: str = "b") -> DataType:
    """Map a `format_type()` spelling such as 'numeric(10,2)' to a neutral DataType."""
    if raw.endswith("[]"):
        return DataType(raw=raw, kind=TypeKind.ARRAY)

    mods = [int(m) for m in _MODIFIERS.findall(raw)[0].split(",")] if "(" in raw else []
    base = " ".join(_MODIFIERS.sub("", raw).split())
    kind = _KIND_BY_NAME.get(base, TypeKind.STRING if typtype == "e" else TypeKind.OTHER)

    length = precision = scale = None
    if kind is TypeKind.STRING and mods:
        length = mods[0]
    elif kind is TypeKind.DECIMAL and mods:
        precision = mods[0]
        scale = mods[1] if len(mods) > 1 else 0
    elif kind in (TypeKind.TIME, TypeKind.TIMESTAMP, TypeKind.INTERVAL) and mods:
        precision = mods[0]
    return DataType(raw=raw, kind=kind, length=length, precision=precision, scale=scale)


Row = Mapping[str, Any]


def build_database(
    name: str,
    schemas: Iterable[Row],
    tables: Iterable[Row],
    columns: Iterable[Row],
    constraints: Iterable[Row],
) -> Database:
    """Assemble catalog query rows into the neutral model. Pure, so it is unit-testable."""
    cols_by_table: dict[tuple[str, str], list[Column]] = defaultdict(list)
    for r in columns:
        cols_by_table[r["schema"], r["table"]].append(
            Column(
                name=r["name"],
                data_type=parse_type(r["type"], r["typtype"]),
                ordinal=r["ordinal"],
                nullable=r["nullable"],
                description=r["description"],
                default=r["default"],
            )
        )

    pks: dict[tuple[str, str], tuple[str, ...]] = {}
    uniques: dict[tuple[str, str], list[tuple[str, ...]]] = defaultdict(list)
    fks: dict[tuple[str, str], list[ForeignKey]] = defaultdict(list)
    for r in constraints:
        key = (r["schema"], r["table"])
        cols = tuple(r["columns"])
        if r["type"] == "p":
            pks[key] = cols
        elif r["type"] == "u":
            uniques[key].append(cols)
        elif r["type"] == "f":
            fks[key].append(
                ForeignKey(
                    name=r["name"],
                    columns=cols,
                    references=TableRef(
                        database=name, schema=r["ref_schema"], table=r["ref_table"]
                    ),
                    referenced_columns=tuple(r["ref_columns"]),
                )
            )

    tables_by_schema: dict[str, list[Table]] = defaultdict(list)
    for r in tables:
        key = (r["schema"], r["name"])
        # reltuples is -1 on Postgres 14+ until the table is first vacuumed or analyzed.
        estimate = r["reltuples"] if r["reltuples"] is not None and r["reltuples"] >= 0 else None
        tables_by_schema[r["schema"]].append(
            Table(
                name=r["name"],
                kind=_RELKINDS.get(r["relkind"], TableKind.OTHER),
                description=r["description"],
                columns=tuple(sorted(cols_by_table[key], key=lambda c: c.ordinal)),
                primary_key=pks.get(key, ()),
                unique_constraints=tuple(uniques[key]),
                foreign_keys=tuple(fks[key]),
                row_count_estimate=estimate,
                ref=TableRef(database=name, schema=r["schema"], table=r["name"]),
            )
        )

    return Database(
        name=name,
        platform=PostgresConnector.name,
        schemas=tuple(
            Schema(
                name=s["name"],
                description=s["description"],
                tables=tuple(tables_by_schema[s["name"]]),
            )
            for s in schemas
        ),
    )


class PostgresConnector:
    name: ClassVar[str] = "postgres"
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
        (rows,) = self._run([(_SCHEMAS_SQL, {"system": list(SYSTEM_SCHEMAS)})])
        return [r["name"] for r in rows]

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        wanted = list(schemas) if schemas else None
        params = {"system": list(SYSTEM_SCHEMAS)}
        (db_rows, schema_rows) = self._run(
            [("SELECT current_database() AS name", None), (_SCHEMAS_SQL, params)]
        )
        if wanted is not None:
            unknown = set(wanted) - {r["name"] for r in schema_rows}
            if unknown:
                raise ConnectorError(f"Schemas not found: {', '.join(sorted(unknown))}.")
            schema_rows = [r for r in schema_rows if r["name"] in wanted]

        params = {"schemas": [r["name"] for r in schema_rows]}
        tables, columns, constraints = self._run(
            [(_TABLES_SQL, params), (_COLUMNS_SQL, params), (_CONSTRAINTS_SQL, params)]
        )
        return build_database(db_rows[0]["name"], schema_rows, tables, columns, constraints)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
