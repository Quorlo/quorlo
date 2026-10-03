"""What all built-in checks share."""

from __future__ import annotations

from typing import ClassVar

from quorlo.models import Table
from quorlo.readiness.base import Dimension, Finding, Scope, Severity


class BaseCheck:
    """Declarations every check makes, plus a factory for its findings."""

    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float] = 1.0
    version: ClassVar[int] = 1
    description: ClassVar[str]

    def applies_to(self, table: Table) -> bool:
        return self.scope is Scope.TABLE or bool(table.columns)

    def finding(
        self,
        table: str,
        message: str,
        remedy: str,
        column: str | None = None,
        key: str | None = None,
    ) -> Finding:
        """A finding from this check about `table` (its qualified name)."""
        return Finding(
            check_id=self.id,
            dimension=self.dimension,
            severity=self.severity,
            scope=self.scope,
            table=table,
            column=column,
            key=key,
            message=message,
            remedy=remedy,
        )


def is_blank(text: str | None) -> bool:
    return not (text and text.strip())
