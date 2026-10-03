"""Built-in readiness checks."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import ClassVar

from quorlo.models import Column, Table, TableKind, TypeKind
from quorlo.readiness.base import Check, Dimension, Finding, ScanContext, Scope, Severity
from quorlo.readiness.names import (
    concept_key,
    cryptic_reason,
    is_freshness_column_name,
    pii_category,
)


class _BaseCheck:
    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float] = 1.0
    version: ClassVar[int] = 1
    description: ClassVar[str]

    def applies_to(self, table: Table) -> bool:
        return self.scope is Scope.TABLE or bool(table.columns)

    def _finding(
        self,
        table: Table,
        message: str,
        remedy: str,
        column: str | None = None,
        key: str | None = None,
    ) -> Finding:
        return Finding(
            check_id=self.id,
            dimension=self.dimension,
            severity=self.severity,
            scope=self.scope,
            table=table.qualified_name,
            column=column,
            key=key,
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


PII_TAGS = frozenset({"pii", "personal", "personal_data", "sensitive", "gdpr"})
_PII_DESCRIPTION = re.compile(
    r"\b(pii|personal data|personally identifiable|personal information|sensitive)\b", re.I
)


def is_classified_as_pii(column: Column) -> bool:
    """Marked as personal data, by a platform tag or, where there are no tags, its description."""
    if any(tag.lower() in PII_TAGS or tag.lower().startswith("pii") for tag in column.tags):
        return True
    return bool(column.description and _PII_DESCRIPTION.search(column.description))


class PiiUnclassified(_BaseCheck):
    id = "column.pii.unclassified"
    dimension = Dimension.GOVERNANCE
    # Scored per table: one unmarked personal-data column is enough to make the whole
    # table unsafe for an agent to use. Findings still name each column.
    scope = Scope.TABLE
    severity = Severity.HIGH
    weight = 1.0
    description = "Columns that look like personal data are marked as such."

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        for col in table.columns:
            category = pii_category(col.name, table.name, col.data_type.raw)
            if category and not is_classified_as_pii(col):
                yield self._finding(
                    table,
                    f"Column looks like personal data ({category}) but is not marked as PII.",
                    "Tag the column as PII, or say so in its description, so agents and "
                    "access policies can treat it accordingly.",
                    column=col.name,
                )


class FreshnessUntracked(_BaseCheck):
    id = "table.freshness.untracked"
    dimension = Dimension.TRUST
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    description = "The table has a column that tells an agent how fresh its data is."

    def applies_to(self, table: Table) -> bool:
        # A view is as fresh as the tables it reads; those are checked instead.
        return table.kind in (TableKind.TABLE, TableKind.MATERIALIZED_VIEW, TableKind.OTHER)

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        has_freshness_column = any(
            col.data_type.kind in (TypeKind.TIMESTAMP, TypeKind.DATE)
            and is_freshness_column_name(col.name)
            for col in table.columns
        )
        if not has_freshness_column:
            yield self._finding(
                table,
                "No column shows when rows were last loaded or updated.",
                "Add a timestamp such as updated_at or loaded_at, maintained by the load "
                "process, so agents can tell whether the data is current.",
            )


_STATUS_DESCRIPTION = re.compile(
    r"\b(certified|source of truth|deprecated|superseded|do not use)\b", re.I
)
_STATUS_TAGS = frozenset({"certified", "deprecated"})


def declares_status(table: Table) -> bool:
    """Says whether it is the trusted source or a stale copy, by tag or in its description."""
    if any(tag.lower() in _STATUS_TAGS for tag in table.tags):
        return True
    return bool(table.description and _STATUS_DESCRIPTION.search(table.description))


def column_type_overlap(a: Table, b: Table) -> float:
    """Share of column types two tables have in common, from 0 to 1 (multiset Jaccard)."""
    kinds_a = Counter(c.data_type.kind for c in a.columns)
    kinds_b = Counter(c.data_type.kind for c in b.columns)
    union = sum((kinds_a | kinds_b).values())
    return sum((kinds_a & kinds_b).values()) / union if union else 0.0


class DuplicateSuspected(_BaseCheck):
    id = "table.duplicate.suspected"
    dimension = Dimension.CERTIFICATION
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    description = "No other table looks like the same thing without saying which one to use."

    min_type_overlap: ClassVar[float] = 0.5

    def is_duplicate(self, a: Table, b: Table) -> bool:
        key = concept_key(a.name)
        return (
            bool(key)
            and key == concept_key(b.name)
            and column_type_overlap(a, b) >= self.min_type_overlap
        )

    def run(self, table: Table, context: ScanContext) -> Iterable[Finding]:
        for other in context.others(table):
            if self.is_duplicate(table, other) and not (
                declares_status(table) or declares_status(other)
            ):
                other_name = f"{other.ref.schema_name}.{other.name}"
                yield self._finding(
                    table,
                    f"Looks like the same data as {other_name}, and neither says which to use.",
                    "Mark the trusted table as certified (a tag, or 'source of truth' in its "
                    "description), and the other as deprecated, or remove one.",
                    key=other.qualified_name,
                )


DEFAULT_CHECKS: tuple[Check, ...] = (
    TableDescriptionMissing(),
    ColumnDescriptionMissing(),
    PrimaryKeyMissing(),
    ColumnNameCryptic(),
    PiiUnclassified(),
    FreshnessUntracked(),
    DuplicateSuspected(),
)
