"""Assemble catalog query rows into the platform-neutral models. Pure, so unit-testable."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from quorlo.connectors.postgres.types import parse_type
from quorlo.models import (
    Column,
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
TableKey = str  # table name within the schema being assembled


def postgres_location(host: str, port: int, dbname: str) -> str:
    """'postgres://host:port/db'. A unix socket directory stands in for the host as-is."""
    return f"postgres://{host}:{port}/{dbname}"


@dataclass
class _Constraints:
    """One table's keys, gathered from pg_constraint rows."""

    primary_key: tuple[str, ...] = ()
    unique: list[tuple[str, ...]] = field(default_factory=list)
    foreign: list[ForeignKey] = field(default_factory=list)


class SchemaAssembler:
    """Builds one `Schema` from the rows of the per-schema catalog queries."""

    def __init__(self, database: str) -> None:
        self._database = database

    def build(
        self,
        schema: Row,
        tables: Iterable[Row],
        columns: Iterable[Row],
        constraints: Iterable[Row],
    ) -> Schema:
        columns_by_table = self._columns(columns)
        constraints_by_table = self._constraints(constraints)
        return Schema(
            name=schema["name"],
            description=schema["description"],
            tables=tuple(
                self._table(
                    row,
                    columns_by_table[row["name"]],
                    constraints_by_table.get(row["name"], _Constraints()),
                )
                for row in tables
            ),
        )

    def _columns(self, rows: Iterable[Row]) -> dict[TableKey, list[Column]]:
        by_table: dict[TableKey, list[Column]] = defaultdict(list)
        for r in rows:
            by_table[r["table"]].append(
                Column(
                    name=r["name"],
                    data_type=parse_type(r["type"], r["typtype"]),
                    ordinal=r["ordinal"],
                    nullable=r["nullable"],
                    description=r["description"],
                    default=r["default"],
                )
            )
        return by_table

    def _constraints(self, rows: Iterable[Row]) -> dict[TableKey, _Constraints]:
        by_table: dict[TableKey, _Constraints] = defaultdict(_Constraints)
        for r in rows:
            found = by_table[r["table"]]
            columns = tuple(r["columns"])
            if r["type"] == "p":
                found.primary_key = columns
            elif r["type"] == "u":
                found.unique.append(columns)
            elif r["type"] == "f":
                found.foreign.append(self._foreign_key(r, columns))
        return by_table

    def _foreign_key(self, row: Row, columns: tuple[str, ...]) -> ForeignKey:
        return ForeignKey(
            name=row["name"],
            columns=columns,
            references=TableRef(
                database=self._database, schema=row["ref_schema"], table=row["ref_table"]
            ),
            referenced_columns=tuple(row["ref_columns"]),
        )

    def _table(self, row: Row, columns: list[Column], constraints: _Constraints) -> Table:
        return Table(
            name=row["name"],
            kind=_RELKINDS.get(row["relkind"], TableKind.OTHER),
            description=row["description"],
            columns=tuple(sorted(columns, key=lambda c: c.ordinal)),
            primary_key=constraints.primary_key,
            unique_constraints=tuple(constraints.unique),
            foreign_keys=tuple(constraints.foreign),
            row_count_estimate=self._row_estimate(row["reltuples"]),
            ref=TableRef(database=self._database, schema=row["schema"], table=row["name"]),
        )

    @staticmethod
    def _row_estimate(reltuples: int | None) -> int | None:
        # reltuples is -1 on Postgres 14+ until the table is first vacuumed or analyzed.
        return reltuples if reltuples is not None and reltuples >= 0 else None
