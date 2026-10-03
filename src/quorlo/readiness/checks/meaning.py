"""Checks for "What is it?": descriptions, keys and readable names."""

from __future__ import annotations

from collections.abc import Iterable

from quorlo.models import Table, TableKind
from quorlo.readiness.base import Dimension, Finding, Scope, Severity
from quorlo.readiness.checks._base import BaseCheck, is_blank
from quorlo.readiness.names import cryptic_reason


class TableDescriptionMissing(BaseCheck):
    id = "table.description.missing"
    dimension = Dimension.MEANING
    scope = Scope.TABLE
    severity = Severity.HIGH
    weight = 2.0
    description = "The table has a business description."
    summary = "no table description"
    fix_hint = "COMMENT ON TABLE {table} IS '<what one row represents, and what it is for>';"

    def run(self, table: Table) -> Iterable[Finding]:
        if is_blank(table.description):
            yield self.finding(
                table.qualified_name,
                "Table has no description.",
                "Describe what one row represents and what the table is used for.",
            )


class ColumnDescriptionMissing(BaseCheck):
    id = "column.description.missing"
    dimension = Dimension.MEANING
    scope = Scope.COLUMN
    severity = Severity.MEDIUM
    weight = 1.0
    description = "Each column has a description."
    summary = "no column description"
    fix_hint = "COMMENT ON COLUMN {table}.{column} IS '<meaning, units, codes>';"

    def run(self, table: Table) -> Iterable[Finding]:
        for col in table.columns:
            if is_blank(col.description):
                yield self.finding(
                    table.qualified_name,
                    "Column has no description.",
                    "Describe the column, including units and the meaning of any codes.",
                    column=col.name,
                )


class PrimaryKeyMissing(BaseCheck):
    id = "table.primary_key.missing"
    dimension = Dimension.MEANING
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    description = "The table declares a primary key, so an agent knows what identifies a row."
    summary = "no primary key"
    fix_hint = "ALTER TABLE {table} ADD PRIMARY KEY (<columns>);  or name them in the description"

    def applies_to(self, table: Table) -> bool:
        # Views and foreign tables cannot declare one, so they are not penalised for it.
        return table.kind in (TableKind.TABLE, TableKind.OTHER)

    def run(self, table: Table) -> Iterable[Finding]:
        if not table.has_primary_key:
            yield self.finding(
                table.qualified_name,
                "Table has no primary key.",
                "Declare a primary key, or document which columns identify a row.",
            )


class ColumnNameCryptic(BaseCheck):
    id = "column.name.cryptic"
    dimension = Dimension.MEANING
    scope = Scope.COLUMN
    severity = Severity.LOW
    weight = 1.0
    description = "Column names are readable words, not cryptic abbreviations."
    summary = "cryptic column name"
    fix_hint = "rename, or explain it: COMMENT ON COLUMN {table}.{column} IS '<what it means>';"

    def run(self, table: Table) -> Iterable[Finding]:
        for col in table.columns:
            reason = cryptic_reason(col.name)
            if reason:
                yield self.finding(
                    table.qualified_name,
                    f"Column name is cryptic ({reason}).",
                    "Rename the column, or describe it so the abbreviation is explained.",
                    column=col.name,
                )
