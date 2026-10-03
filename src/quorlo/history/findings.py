"""A run's findings made actionable: filtered, collapsed per check, ordered worst first.

Pure: no I/O. The store does the filtering in SQL (`FindingQuery`); this module groups
what comes back.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from quorlo.readiness import Check, Dimension, Finding, ScanReport, Severity
from quorlo.readiness.checks._base import FixHint

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FindingQuery(_Frozen):
    """Which findings to show. Values of one filter widen; different filters narrow."""

    tables: tuple[str, ...] = ()
    dimensions: tuple[Dimension, ...] = ()
    checks: tuple[str, ...] = ()

    @staticmethod
    def table_matches(qualified_name: str, wanted: str) -> bool:
        """'cust_mstr', 'retail_raw.cust_mstr' and the full name all match the table."""
        return qualified_name == wanted or qualified_name.endswith(f".{wanted}")


class CheckGroup(_Frozen):
    """Everything one check found on one table, on one line."""

    check_id: str
    dimension: Dimension
    severity: Severity
    summary: str
    columns: tuple[str, ...]
    messages: tuple[str, ...]
    fix_hint: str
    count: int


class TableFindings(_Frozen):
    table: str
    score: float | None
    finding_count: int
    groups: tuple[CheckGroup, ...]

    def by_dimension(self) -> dict[Dimension, list[CheckGroup]]:
        """Groups under each of the five questions, in their usual order."""
        return {
            d: [g for g in self.groups if g.dimension is d]
            for d in Dimension
            if any(g.dimension is d for g in self.groups)
        }


@dataclass
class _Collector:
    """Findings of one check on one table, as they arrive."""

    first: Finding
    columns: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    count: int = 0

    def add(self, finding: Finding) -> None:
        self.count += 1
        if finding.column and finding.column not in self.columns:
            self.columns.append(finding.column)
        elif not finding.column and finding.message not in self.messages:
            self.messages.append(finding.message)


class FindingGrouper:
    """Collapses a run's findings into one line per check per table, worst table first."""

    def __init__(self, report: ScanReport, checks: Mapping[str, Check]) -> None:
        self._tables = {t.table: t for t in report.tables}
        self._checks = checks
        self._prefix = f"{report.database}."

    def group(self, findings: Iterable[Finding]) -> list[TableFindings]:
        collected: dict[str, dict[str, _Collector]] = {}
        for finding in findings:
            by_check = collected.setdefault(finding.table, {})
            by_check.setdefault(finding.check_id, _Collector(finding)).add(finding)
        tables = [self._table(name, by_check) for name, by_check in collected.items()]
        return sorted(tables, key=self._worst_first)

    def _table(self, name: str, by_check: dict[str, _Collector]) -> TableFindings:
        readiness = self._tables.get(name)
        groups = sorted(
            (self._group(name, c) for c in by_check.values()),
            key=lambda g: (_SEVERITY_ORDER[g.severity], g.check_id),
        )
        return TableFindings(
            table=name,
            score=readiness.score if readiness else None,
            finding_count=readiness.finding_count if readiness else len(groups),
            groups=tuple(groups),
        )

    def _group(self, table: str, collector: _Collector) -> CheckGroup:
        first = collector.first
        check = self._checks.get(first.check_id)
        short_table = table.removeprefix(self._prefix)
        return CheckGroup(
            check_id=first.check_id,
            dimension=first.dimension,
            severity=first.severity,
            # A check this version no longer has still shows what it said at the time.
            summary=check.summary if check else first.message,
            columns=tuple(collector.columns),
            messages=tuple(collector.messages),
            fix_hint=FixHint(check.fix_hint).render(short_table, collector.columns)
            if check
            else first.remedy,
            count=collector.count,
        )

    @staticmethod
    def _worst_first(table: TableFindings) -> tuple[bool, float, int, str]:
        unscored = table.score is None
        return (unscored, table.score or 0.0, -table.finding_count, table.table)
