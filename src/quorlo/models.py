"""Platform-neutral metadata models.

Every connector translates its platform's catalog into these models, and everything
downstream (readiness checks, reports, enrichment) works only on them.

These models describe structure and documentation, never content. There is
deliberately no field anywhere that can hold a sample value or a row of data, so the
model surface cannot carry data out of a platform even by accident. Keep it that way:
if sample values are ever needed, they get their own opt-in type outside this module.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TypeKind(StrEnum):
    """Neutral family of a column's data type. The platform spelling lives in `DataType.raw`."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    INTERVAL = "interval"
    BINARY = "binary"
    JSON = "json"
    UUID = "uuid"
    ARRAY = "array"
    STRUCT = "struct"
    OTHER = "other"


class DataType(_Frozen):
    raw: str = Field(description="Type name as the platform spells it, e.g. 'character varying'.")
    kind: TypeKind = TypeKind.OTHER
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


class TableKind(StrEnum):
    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    FOREIGN = "foreign"
    OTHER = "other"


class TableRef(_Frozen):
    database: str
    schema_name: str = Field(alias="schema")
    table: str

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema_name}.{self.table}"


class ForeignKey(_Frozen):
    name: str | None = None
    columns: tuple[str, ...]
    references: TableRef
    referenced_columns: tuple[str, ...]


class Column(_Frozen):
    name: str
    data_type: DataType
    ordinal: int = Field(ge=1, description="1-based position within the table.")
    nullable: bool = True
    description: str | None = None
    default: str | None = Field(
        default=None, description="Default expression as declared in the schema, not a value."
    )
    tags: tuple[str, ...] = Field(
        default=(),
        description="Platform tags or classifications, e.g. 'pii'. Labels, never values.",
    )


class Table(_Frozen):
    name: str
    kind: TableKind = TableKind.TABLE
    description: str | None = None
    columns: tuple[Column, ...] = ()
    primary_key: tuple[str, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    row_count_estimate: int | None = Field(
        default=None, description="From catalog statistics; never from counting rows."
    )
    tags: tuple[str, ...] = Field(
        default=(), description="Platform tags or classifications, e.g. 'certified'."
    )
    ref: TableRef

    @model_validator(mode="after")
    def _check_consistency(self) -> Table:
        if self.ref.table != self.name:
            raise ValueError(f"ref.table {self.ref.table!r} does not match name {self.name!r}")
        names = {c.name for c in self.columns}
        missing = [c for c in self.primary_key if c not in names] if self.columns else []
        if missing:
            raise ValueError(f"primary key columns not in table: {missing}")
        return self

    @property
    def qualified_name(self) -> str:
        return self.ref.qualified_name

    @property
    def has_primary_key(self) -> bool:
        return bool(self.primary_key)

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


class Schema(_Frozen):
    name: str
    description: str | None = None
    tables: tuple[Table, ...] = ()


class Database(_Frozen):
    name: str
    platform: str = Field(description="Connector name that produced this, e.g. 'postgres'.")
    location: str | None = Field(
        default=None,
        description="Where the database lives, e.g. 'postgres://db.internal:5432/warehouse'. "
        "Never contains credentials. Used to tell runs against different servers apart.",
    )
    schemas: tuple[Schema, ...] = ()

    def iter_tables(self) -> Iterator[Table]:
        for schema in self.schemas:
            yield from schema.tables
