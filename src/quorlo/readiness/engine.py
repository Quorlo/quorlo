"""Run checks over streamed metadata and turn their results into scores.

Scoring works per check, then rolls up:

- A check evaluates one unit per table (TABLE scope) or one per column (COLUMN scope),
  and only on tables it `applies_to`. Its pass rate is `1 - findings / units`.
- A table's score in a dimension is the weight-averaged pass rate of the checks in that
  dimension; its overall score averages all checks the same way. Normalising per check
  keeps a wide table's column checks from drowning out its table-level checks.
- A report's scores are the mean of its tables' scores.

A score is None when nothing was evaluated, which is different from scoring zero.

Findings are handed to a `FindingSink` as soon as they exist and are not kept here, so
an assessment's memory grows with the number of tables, not with columns or findings.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from statistics import fmean
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from quorlo.models import Database, Schema, Table, TableKind
from quorlo.readiness.base import (
    Check,
    Dimension,
    EstateCheck,
    EstateCheckRun,
    Finding,
    Scope,
    TableCheck,
)
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
    finding_count: int


class ScanReport(_Frozen):
    """Scores for a scan. Findings live in a `FindingSink`, not here."""

    database: str
    platform: str
    checks: dict[str, int] = Field(
        default_factory=dict, description="Every check that ran, by id, with its version."
    )
    score: float | None
    dimensions: dict[Dimension, float]
    tables: tuple[TableReadiness, ...]

    @property
    def finding_count(self) -> int:
        return sum(t.finding_count for t in self.tables)


class FindingSink(Protocol):
    """Where findings go as a scan produces them."""

    def add(self, findings: Iterable[Finding]) -> None: ...


class FindingList:
    """Keeps findings in memory: for small scans, tests, and runs that are not saved."""

    def __init__(self) -> None:
        self._findings: list[Finding] = []

    def add(self, findings: Iterable[Finding]) -> None:
        self._findings.extend(findings)

    def __iter__(self) -> Iterator[Finding]:
        return iter(self._findings)

    def __len__(self) -> int:
        return len(self._findings)

    def for_table(self, table: str) -> list[Finding]:
        return [f for f in self._findings if f.table == table]


class Scorecard:
    """Weight-averaged pass rates over a set of check results."""

    def __init__(self, results: Sequence[CheckResult]) -> None:
        self._results = results

    def overall(self) -> float | None:
        return self._weighted(self._results)

    def by_dimension(self) -> dict[Dimension, float]:
        scores = {
            d: self._weighted([r for r in self._results if r.dimension is d]) for d in Dimension
        }
        return {d: s for d, s in scores.items() if s is not None}

    @staticmethod
    def _weighted(results: Sequence[CheckResult]) -> float | None:
        total = sum(r.weight for r in results)
        if not total:
            return None
        return sum(r.weight * r.pass_rate for r in results) / total


def _units(check: Check, table: Table) -> int:
    """How many things a check judges on this table: the table, or each column."""
    return 1 if check.scope is Scope.TABLE else len(table.columns)


class TableTally:
    """One table's check results while the scan is still running."""

    def __init__(self, table: Table) -> None:
        self.name = table.qualified_name
        self.kind = table.kind
        self._evaluated: dict[str, tuple[Check, int]] = {}
        self._failed: Counter[str] = Counter()
        self.finding_count = 0

    def evaluated(self, check: Check, units: int) -> None:
        self._evaluated[check.id] = (check, units)

    def failed(self, findings: Sequence[Finding]) -> None:
        self._failed.update(f.check_id for f in findings)
        self.finding_count += len(findings)

    def readiness(self) -> TableReadiness:
        results = [
            CheckResult(
                check_id=check.id,
                dimension=check.dimension,
                weight=check.weight,
                evaluated=units,
                # A misbehaving check cannot push a score below zero.
                failed=min(self._failed[check.id], units),
            )
            for check, units in self._evaluated.values()
        ]
        card = Scorecard(results)
        return TableReadiness(
            table=self.name,
            kind=self.kind,
            score=card.overall(),
            dimensions=card.by_dimension(),
            checks=tuple(results),
            finding_count=self.finding_count,
        )


class Assessment:
    """One scan in progress: feed it schemas, then finish the checks, then get the report."""

    def __init__(self, checks: Sequence[Check], sink: FindingSink) -> None:
        self._table_checks = [c for c in checks if isinstance(c, TableCheck)]
        self._estate_runs: list[tuple[EstateCheck, EstateCheckRun]] = [
            (c, c.start()) for c in checks if isinstance(c, EstateCheck)
        ]
        self._versions = {c.id: c.version for c in checks}
        self._sink = sink
        self._tallies: dict[str, TableTally] = {}
        self._checks_finished = False

    @property
    def tables(self) -> int:
        return len(self._tallies)

    def add(self, schema: Schema) -> None:
        for table in schema.tables:
            self._add_table(table)

    def _add_table(self, table: Table) -> None:
        tally = self._tallies[table.qualified_name] = TableTally(table)
        for check in self._table_checks:
            if units := self._applicable_units(check, table):
                tally.evaluated(check, units)
                self._record(tally, list(check.run(table)))
        for check, run in self._estate_runs:
            if units := self._applicable_units(check, table):
                tally.evaluated(check, units)
                run.observe(table)

    @staticmethod
    def _applicable_units(check: Check, table: Table) -> int:
        return _units(check, table) if check.applies_to(table) else 0

    def finish_checks(self) -> None:
        """Let cross-table checks report, now that every table has been seen."""
        for _check, run in self._estate_runs:
            by_table: dict[str, list[Finding]] = {}
            for finding in run.findings():
                by_table.setdefault(finding.table, []).append(finding)
            for table, findings in by_table.items():
                self._record(self._tallies[table], findings)
        self._checks_finished = True

    def _record(self, tally: TableTally, findings: list[Finding]) -> None:
        if findings:
            tally.failed(findings)
            self._sink.add(findings)

    def report(self, database: str, platform: str) -> ScanReport:
        """Score every table and the scan as a whole."""
        if not self._checks_finished:
            raise RuntimeError("finish_checks() must run before report()")
        tables = tuple(tally.readiness() for tally in self._tallies.values())
        scores = [t.score for t in tables if t.score is not None]
        return ScanReport(
            database=database,
            platform=platform,
            checks=self._versions,
            score=fmean(scores) if scores else None,
            dimensions=self._mean_dimensions(tables),
            tables=tables,
        )

    @staticmethod
    def _mean_dimensions(tables: Sequence[TableReadiness]) -> dict[Dimension, float]:
        means = {}
        for dim in Dimension:
            scores = [t.dimensions[dim] for t in tables if dim in t.dimensions]
            if scores:
                means[dim] = fmean(scores)
        return means


class ReadinessEngine:
    """Runs a fixed set of checks. Stateless and reusable: each scan gets an `Assessment`."""

    def __init__(self, checks: Sequence[Check] = DEFAULT_CHECKS) -> None:
        self._checks = tuple(checks)

    def start(self, sink: FindingSink) -> Assessment:
        return Assessment(self._checks, sink)


class Evaluation(_Frozen):
    """A whole database assessed in memory, with its findings."""

    report: ScanReport
    findings: tuple[Finding, ...]

    def findings_for(self, table: str) -> list[Finding]:
        return [f for f in self.findings if f.table == table]


def evaluate(database: Database, checks: Sequence[Check] = DEFAULT_CHECKS) -> Evaluation:
    """Assess a database held in memory. Scans stream instead; see `quorlo.scanner`."""
    findings = FindingList()
    assessment = ReadinessEngine(checks).start(findings)
    for schema in database.schemas:
        assessment.add(schema)
    assessment.finish_checks()
    return Evaluation(
        report=assessment.report(database.name, database.platform), findings=tuple(findings)
    )


def evaluate_table(table: Table, checks: Sequence[Check] = DEFAULT_CHECKS) -> Evaluation:
    """Assess a single table on its own. Cross-table checks see only this table."""
    schema = Schema(name=table.ref.schema_name, tables=(table,))
    database = Database(name=table.ref.database, platform="", schemas=(schema,))
    return evaluate(database, checks)
