"""Built-in readiness checks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from quorlo.models import Table, TableKind
from quorlo.readiness.base import Check, Dimension, Finding, ScanContext, Scope, Severity
from quorlo.readiness.names import cryptic_reason


class _BaseCheck:
    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float] = 1.0
    description: ClassVar[str]

    def applies_to(self, table: Table) -> bool:
        return self.scope is Scope.TABLE or bool(table.columns)

    def _finding(self, table: Table, message: str, remedy: str, column: str | None = None):
        return Finding(
            check_id=self.id,
            dimension=self.dimension,
            severity=self.severity,
            scope=self.scope,
            table=table.qualified_name,
            column=column,
            message=message,
            remedy=remedy,
        )


def _blank(text: str | None) -> bool:
    return not (text and text.strip())


class TableDescriptionMissing(_BaseCheck):
    id = "table.description.missing"
    dimension = Dimension.MEANING
    scope = Scope.TABLE
    severity = Severity.HIGH
    weight = 2.0
    description = "The table has a business description."

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        if _blank(table.description):
            yield self._finding(
                table,
                "Table has no description.",
                "Describe what one row represents and what the table is used for.",
            )


class ColumnDescriptionMissing(_BaseCheck):
    id = "column.description.missing"
    dimension = Dimension.MEANING
    scope = Scope.COLUMN
    severity = Severity.MEDIUM
    weight = 1.0
    description = "Each column has a description."

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        for col in table.columns:
            if _blank(col.description):
                yield self._finding(
                    table,
                    "Column has no description.",
                    "Describe the column, including units and the meaning of any codes.",
                    column=col.name,
                )


class PrimaryKeyMissing(_BaseCheck):
    id = "table.primary_key.missing"
    dimension = Dimension.MEANING
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    description = "The table declares a primary key, so an agent knows what identifies a row."

    def applies_to(self, table: Table) -> bool:
        # Views and foreign tables cannot declare one, so they are not penalised for it.
        return table.kind in (TableKind.TABLE, TableKind.OTHER)

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        if not table.has_primary_key:
            yield self._finding(
                table,
                "Table has no primary key.",
                "Declare a primary key, or document which columns identify a row.",
            )


class ColumnNameCryptic(_BaseCheck):
    id = "column.name.cryptic"
    dimension = Dimension.MEANING
    scope = Scope.COLUMN
    severity = Severity.LOW
    weight = 1.0
    description = "Column names are readable words, not cryptic abbreviations."

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        for col in table.columns:
            reason = cryptic_reason(col.name)
            if reason:
                yield self._finding(
                    table,
                    f"Column name is cryptic ({reason}).",
                    "Rename the column, or describe it so the abbreviation is explained.",
                    column=col.name,
                )


DEFAULT_CHECKS: tuple[Check, ...] = (
    TableDescriptionMissing(),
    ColumnDescriptionMissing(),
    PrimaryKeyMissing(),
    ColumnNameCryptic(),
)
