"""Checks for "Is it the right one?": near-duplicate tables that don't say which to use."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from quorlo.models import Table, TypeKind
from quorlo.readiness.base import Dimension, Finding, Scope, Severity
from quorlo.readiness.checks._base import BaseCheck
from quorlo.readiness.names import concept_key

_STATUS_DESCRIPTION = re.compile(
    r"\b(certified|source of truth|deprecated|superseded|do not use)\b", re.I
)
_STATUS_TAGS = frozenset({"certified", "deprecated"})


def declares_status(table: Table) -> bool:
    """Says whether it is the trusted source or a stale copy, by tag or in its description."""
    if any(tag.lower() in _STATUS_TAGS for tag in table.tags):
        return True
    return bool(table.description and _STATUS_DESCRIPTION.search(table.description))


@dataclass(frozen=True)
class TableSignature:
    """What the duplicate check needs to remember about a table: a few bytes, not its columns."""

    qualified_name: str
    display_name: str
    concept: frozenset[str]
    column_kinds: Counter[TypeKind]
    declares_status: bool

    @classmethod
    def of(cls, table: Table) -> TableSignature:
        return cls(
            qualified_name=table.qualified_name,
            display_name=f"{table.ref.schema_name}.{table.name}",
            concept=concept_key(table.name),
            column_kinds=Counter(c.data_type.kind for c in table.columns),
            declares_status=declares_status(table),
        )

    def type_overlap(self, other: TableSignature) -> float:
        """Share of column types in common, from 0 to 1 (multiset Jaccard)."""
        union = sum((self.column_kinds | other.column_kinds).values())
        shared = sum((self.column_kinds & other.column_kinds).values())
        return shared / union if union else 0.0


def column_type_overlap(a: Table, b: Table) -> float:
    return TableSignature.of(a).type_overlap(TableSignature.of(b))


class DuplicateSuspected(BaseCheck):
    id = "table.duplicate.suspected"
    dimension = Dimension.CERTIFICATION
    scope = Scope.TABLE
    severity = Severity.MEDIUM
    weight = 1.0
    # 2: one finding per table instead of one per matching pair, and plain numbers in a
    # name (orders_2023) no longer count as version markers.
    version = 2
    description = "No other table looks like the same thing without saying which one to use."

    min_type_overlap: ClassVar[float] = 0.5
    max_named_matches: ClassVar[int] = 5

    def start(self) -> _DuplicateRun:
        return _DuplicateRun(self)

    def is_match(self, a: TableSignature, b: TableSignature) -> bool:
        return (
            a.qualified_name != b.qualified_name
            and not b.declares_status
            and a.type_overlap(b) >= self.min_type_overlap
        )

    def describe_matches(self, matches: Iterable[TableSignature]) -> str:
        names = sorted(m.display_name for m in matches)
        shown = ", ".join(names[: self.max_named_matches])
        hidden = len(names) - self.max_named_matches
        return f"{shown} and {hidden} more" if hidden > 0 else shown


class _DuplicateRun:
    """Groups table signatures by name key as they stream past; judges each group at the end.

    Grouping keeps the work O(n) over the estate instead of comparing every pair.
    """

    def __init__(self, check: DuplicateSuspected) -> None:
        self._check = check
        self._groups: dict[frozenset[str], list[TableSignature]] = defaultdict(list)

    def observe(self, table: Table) -> None:
        signature = TableSignature.of(table)
        if signature.concept:
            self._groups[signature.concept].append(signature)

    def findings(self) -> Iterable[Finding]:
        for group in self._groups.values():
            if len(group) > 1:
                yield from self._judge(group)

    def _judge(self, group: list[TableSignature]) -> Iterable[Finding]:
        for table in group:
            if table.declares_status:
                continue
            matches = [other for other in group if self._check.is_match(table, other)]
            if matches:
                yield self._check.finding(
                    table.qualified_name,
                    f"Looks like the same data as {self._check.describe_matches(matches)}, "
                    "and nothing says which to use.",
                    "Mark the trusted table as certified (a tag, or 'source of truth' in its "
                    "description), and the others as deprecated, or remove them.",
                )
