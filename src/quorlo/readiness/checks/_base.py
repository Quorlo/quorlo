"""What all built-in checks share."""

from __future__ import annotations

from collections.abc import Sequence
from string import Formatter
from typing import ClassVar

from quorlo.models import Table
from quorlo.readiness.base import Dimension, Finding, Scope, Severity


class BaseCheck:
    """Declarations every check makes, plus a factory for its findings.

    A subclass that leaves out a required declaration, or whose `fix_hint` uses a
    placeholder other than {table} or {column}, fails at import time, not in a scan.
    """

    id: ClassVar[str]
    dimension: ClassVar[Dimension]
    scope: ClassVar[Scope]
    severity: ClassVar[Severity]
    weight: ClassVar[float] = 1.0
    version: ClassVar[int] = 1
    description: ClassVar[str]
    summary: ClassVar[str]
    fix_hint: ClassVar[str]

    _required: ClassVar[tuple[str, ...]] = (
        "id",
        "dimension",
        "scope",
        "severity",
        "description",
        "summary",
        "fix_hint",
    )

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [name for name in cls._required if not getattr(cls, name, None)]
        if missing:
            raise TypeError(f"Check {cls.__name__} must declare: {', '.join(missing)}")
        FixHint(cls.fix_hint)  # validates its placeholders

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


class FixHint:
    """A check's one-line fix, with {table} and {column} filled in for a specific place."""

    PLACEHOLDERS: ClassVar[frozenset[str]] = frozenset({"table", "column"})

    def __init__(self, template: str) -> None:
        fields = {name for _, name, _, _ in Formatter().parse(template) if name}
        unknown = fields - self.PLACEHOLDERS
        if unknown:
            raise ValueError(f"Unknown fix_hint placeholders: {', '.join(sorted(unknown))}")
        self._template = template

    def render(self, table: str, columns: Sequence[str] = ()) -> str:
        """For one column, name it; for several, leave a <column> placeholder to fill in."""
        column = columns[0] if len(columns) == 1 else "<column>"
        return self._template.format(table=table, column=column)


def is_blank(text: str | None) -> bool:
    return not (text and text.strip())
