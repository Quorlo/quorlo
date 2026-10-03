from __future__ import annotations

from quorlo.models import Column, DataType, Table, TableKind, TableRef, TypeKind


def make_column(
    name: str, description: str | None = None, kind: TypeKind = TypeKind.STRING, ordinal: int = 1
) -> Column:
    return Column(
        name=name,
        data_type=DataType(raw=kind.value, kind=kind),
        ordinal=ordinal,
        description=description,
    )


def make_table(
    name: str = "orders",
    columns: list[Column] | None = None,
    description: str | None = None,
    primary_key: tuple[str, ...] = (),
    kind: TableKind = TableKind.TABLE,
    schema: str = "public",
) -> Table:
    columns = columns or []
    columns = [c.model_copy(update={"ordinal": i}) for i, c in enumerate(columns, start=1)]
    return Table(
        name=name,
        kind=kind,
        description=description,
        columns=tuple(columns),
        primary_key=primary_key,
        ref=TableRef(database="db", schema=schema, table=name),
    )
