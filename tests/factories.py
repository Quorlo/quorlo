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


def run_estate_check(check, tables) -> list:
    """Drive an EstateCheck the way the engine does: observe every table, then report."""
    run = check.start()
    for table in tables:
        if check.applies_to(table):
            run.observe(table)
    return list(run.findings())


def estate_findings_for(check, tables, table) -> list:
    """The findings an EstateCheck raises about one table of a set."""
    return [f for f in run_estate_check(check, tables) if f.table == table.qualified_name]


def evaluate_tables(tables, checks):
    """Assess loose tables, grouped into their schemas, as one database."""
    from quorlo.models import Database, Schema
    from quorlo.readiness import evaluate

    by_schema: dict[str, list] = {}
    for table in tables:
        by_schema.setdefault(table.ref.schema_name, []).append(table)
    database = Database(
        name="db",
        platform="test",
        schemas=tuple(Schema(name=n, tables=tuple(ts)) for n, ts in by_schema.items()),
    )
    return evaluate(database, checks)
