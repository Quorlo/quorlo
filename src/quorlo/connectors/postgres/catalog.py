"""Assemble catalog query rows into the platform-neutral models. Pure, so unit-testable."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from quorlo.connectors.postgres.types import parse_type
from quorlo.models import (
    Column,
    Database,
    ForeignKey,
    Schema,
    Table,
    TableKind,
    TableRef,
)

PLATFORM = "postgres"

_RELKINDS = {
    "r": TableKind.TABLE,
    "p": TableKind.TABLE,
    "v": TableKind.VIEW,
    "m": TableKind.MATERIALIZED_VIEW,
    "f": TableKind.FOREIGN,
}


Row = Mapping[str, Any]


def postgres_location(host: str, port: int, dbname: str) -> str:
    """'postgres://host:port/db'. A unix socket directory stands in for the host as-is."""
    return f"postgres://{host}:{port}/{dbname}"


def build_database(
    name: str,
    schemas: Iterable[Row],
    tables: Iterable[Row],
    columns: Iterable[Row],
    constraints: Iterable[Row],
    location: str | None = None,
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
        platform=PLATFORM,
        location=location,
        schemas=tuple(
            Schema(
                name=s["name"],
                description=s["description"],
                tables=tuple(tables_by_schema[s["name"]]),
            )
            for s in schemas
        ),
    )
