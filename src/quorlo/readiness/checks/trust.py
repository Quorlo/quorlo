"""Checks for "Can I trust it?": whether freshness can be judged at all."""

from __future__ import annotations

from collections.abc import Iterable

from quorlo.models import Table, TableKind, TypeKind
from quorlo.readiness.base import Dimension, Finding, Scope, Severity
from quorlo.readiness.checks._base import BaseCheck
from quorlo.readiness.names import is_freshness_column_name


class FreshnessUntracked(BaseCheck):
    id = "table.freshness.untracked"
    dimension = Dimension.TRUST
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    description = "The table has a column that tells an agent how fresh its data is."
    summary = "nothing shows when rows were last loaded or updated"
    fix_hint = "ALTER TABLE {table} ADD COLUMN updated_at timestamp;  -- kept current by the load"

    def applies_to(self, table: Table) -> bool:
        # A view is as fresh as the tables it reads; those are checked instead.
        return table.kind in (TableKind.TABLE, TableKind.MATERIALIZED_VIEW, TableKind.OTHER)

    def run(self, table: Table) -> Iterable[Finding]:
        has_freshness_column = any(
            col.data_type.kind in (TypeKind.TIMESTAMP, TypeKind.DATE)
            and is_freshness_column_name(col.name)
            for col in table.columns
        )
        if not has_freshness_column:
            yield self.finding(
                table.qualified_name,
                "No column shows when rows were last loaded or updated.",
                "Add a timestamp such as updated_at or loaded_at, maintained by the load "
                "process, so agents can tell whether the data is current.",
            )
