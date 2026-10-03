"""Run checks over scanned metadata and turn findings into scores.

Scoring works per check, then rolls up:

- A check evaluates one unit per table (TABLE scope) or one per column (COLUMN scope),
  and only on tables it `applies_to`. Its pass rate is `1 - findings / units`.
- A table's score in a dimension is the weight-averaged pass rate of the checks in that
  dimension; its overall score averages all checks the same way. Normalising per check
  keeps a wide table's column checks from drowning out its table-level checks.
- A report's scores are the mean of its tables' scores.

A score is None when nothing was evaluated, which is different from scoring zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from statistics import fmean

from pydantic import BaseModel, ConfigDict

from quorlo.models import Database, Table, TableKind
from quorlo.readiness.base import Check, Dimension, Finding, ScanContext, Scope
from quorlo.readiness.checks import DEFAULT_CHECKS


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CheckResult(_Frozen):
    check_id: str
    dimension: Dimension
    weight: float
    evaluated: int
    failed: int

    @property
    def pass_rate(self) -> float:
        return 1.0 - self.failed / self.evaluated


class TableReadiness(_Frozen):
    table: str
    kind: TableKind
    score: float | None
    dimensions: dict[Dimension, float]
    checks: tuple[CheckResult, ...]
    findings: tuple[Finding, ...]


class ScanReport(_Frozen):
    database: str
    platform: str
    score: float | None
    dimensions: dict[Dimension, float]
    tables: tuple[TableReadiness, ...]

    @property
    def findings(self) -> list[Finding]:
        return [f for t in self.tables for f in t.findings]


def _weighted(results: Iterable[CheckResult]) -> float | None:
    results = list(results)
    total = sum(r.weight for r in results)
    if not total:
        return None
    return sum(r.weight * r.pass_rate for r in results) / total


def evaluate_table(
    table: Table,
    checks: Sequence[Check] = DEFAULT_CHECKS,
    context: ScanContext | None = None,
) -> TableReadiness:
    """Score one table. Without a context, cross-table checks see only this table."""
    context = context or ScanContext.of_tables([table])
    results: list[CheckResult] = []
    findings: list[Finding] = []
    for check in checks:
        if not check.applies_to(table):
            continue
        units = 1 if check.scope is Scope.TABLE else len(table.columns)
        if units == 0:
            continue
        found = list(check.run(table, context))
        # A misbehaving check cannot push a score below zero.
        failed = min(len(found), units)
        results.append(
            CheckResult(
                check_id=check.id,
                dimension=check.dimension,
                weight=check.weight,
                evaluated=units,
                failed=failed,
            )
        )
        findings.extend(found)

    dimensions = {}
    for dim in Dimension:
        score = _weighted(r for r in results if r.dimension is dim)
        if score is not None:
            dimensions[dim] = score

    return TableReadiness(
        table=table.qualified_name,
        kind=table.kind,
        score=_weighted(results),
        dimensions=dimensions,
        checks=tuple(results),
        findings=tuple(findings),
    )


def evaluate(database: Database, checks: Sequence[Check] = DEFAULT_CHECKS) -> ScanReport:
    context = ScanContext.of(database)
    tables = tuple(evaluate_table(t, checks, context) for t in context.tables)

    scores = [t.score for t in tables if t.score is not None]
    dimensions = {}
    for dim in Dimension:
        dim_scores = [t.dimensions[dim] for t in tables if dim in t.dimensions]
        if dim_scores:
            dimensions[dim] = fmean(dim_scores)

    return ScanReport(
        database=database.name,
        platform=database.platform,
        score=fmean(scores) if scores else None,
        dimensions=dimensions,
        tables=tables,
    )
