"""Scan runs over time: what a saved run holds, and what changed between two runs.

This module is pure: no I/O. Storage lives in `quorlo.store`.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

import quorlo
from quorlo.connector import DatabaseInfo
from quorlo.models import Database
from quorlo.readiness import Dimension, Finding, ScanReport
from quorlo.stats import ScanStats


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunTarget(_Frozen):
    """What was scanned. Runs are only compared against runs of the same target."""

    platform: str
    location: str | None = None
    database: str

    @property
    def label(self) -> str:
        return self.location or f"{self.platform}:{self.database}"

    @classmethod
    def of(cls, source: Database | DatabaseInfo) -> RunTarget:
        return cls(platform=source.platform, location=source.location, database=source.name)


def new_run_id(started_at: datetime) -> str:
    """Sortable and readable: '20261003T171844Z-3f9a1c'."""
    return f"{started_at.astimezone(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


class RunHeader(_Frozen):
    """What is known about a run when it starts: enough to open it in the store."""

    id: str
    started_at: datetime
    quorlo_version: str
    target: RunTarget
    schemas: tuple[str, ...] | None = Field(
        default=None, description="Schemas the scan was limited to; None means all of them."
    )

    @field_validator("started_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @classmethod
    def start(
        cls,
        target: RunTarget,
        schemas: Sequence[str] | None = None,
        started_at: datetime | None = None,
    ) -> RunHeader:
        started_at = started_at or datetime.now(UTC)
        return cls(
            id=new_run_id(started_at),
            started_at=started_at,
            quorlo_version=quorlo.__version__,
            target=target,
            schemas=tuple(sorted(schemas)) if schemas else None,
        )


class ScanRun(RunHeader):
    """A finished run: its header plus what the scan found.

    The scanned metadata is not held here. The store keeps it per schema and streams it
    back on request, so loading a run never pulls a whole estate into memory.
    """

    finished_at: datetime
    report: ScanReport
    findings: tuple[Finding, ...] = ()
    stats: ScanStats | None = Field(default=None, description="None for runs saved before v4.")

    @field_validator("finished_at")
    @classmethod
    def _aware_finish(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @property
    def checks(self) -> dict[str, int]:
        return self.report.checks

    @classmethod
    def record(
        cls,
        database: Database,
        report: ScanReport,
        findings: Sequence[Finding],
        started_at: datetime,
        finished_at: datetime | None = None,
        schemas: Sequence[str] | None = None,
    ) -> ScanRun:
        """A finished run of a database held in memory."""
        header = RunHeader.start(RunTarget.of(database), schemas, started_at)
        return cls(
            **header.model_dump(),
            finished_at=finished_at or datetime.now(UTC),
            report=report,
            findings=tuple(findings),
        )


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


class ScoreChange(_Frozen):
    before: float | None
    after: float | None

    @property
    def delta(self) -> float | None:
        if self.before is None or self.after is None:
            return None
        return self.after - self.before


class TableChange(_Frozen):
    table: str
    score: ScoreChange
    new_findings: int
    resolved_findings: int


class RunDiff(_Frozen):
    base: str
    head: str
    score: ScoreChange
    dimensions: dict[Dimension, ScoreChange]
    tables_added: tuple[str, ...]
    tables_removed: tuple[str, ...]
    tables_changed: tuple[TableChange, ...]
    new_findings: tuple[Finding, ...]
    resolved_findings: tuple[Finding, ...]
    unchanged_findings: int
    warnings: tuple[str, ...] = Field(
        default=(), description="Reasons the two runs are not strictly comparable."
    )


def _findings_by_fingerprint(run: ScanRun) -> dict[str, Finding]:
    return {f.fingerprint: f for f in run.findings}


def _comparability_warnings(base: ScanRun, head: ScanRun) -> list[str]:
    warnings = []
    if base.target != head.target:
        warnings.append(f"Different targets: {base.target.label} vs {head.target.label}.")
    if base.schemas != head.schemas:

        def describe(schemas: tuple[str, ...] | None) -> str:
            return ", ".join(schemas) if schemas else "all schemas"

        warnings.append(
            f"Different schemas scanned: {describe(base.schemas)} vs {describe(head.schemas)}."
        )
    changed = sorted(
        c for c in base.checks.keys() & head.checks.keys() if base.checks[c] != head.checks[c]
    )
    if changed:
        warnings.append(
            "Check rules changed, so some differences may come from Quorlo rather than "
            f"the data: {', '.join(changed)}."
        )
    added = sorted(head.checks.keys() - base.checks.keys())
    if added:
        warnings.append(f"Checks added since the base run: {', '.join(added)}.")
    removed = sorted(base.checks.keys() - head.checks.keys())
    if removed:
        warnings.append(f"Checks no longer run: {', '.join(removed)}.")
    return warnings


def diff_runs(base: ScanRun, head: ScanRun) -> RunDiff:
    """What changed from `base` to `head`. Findings are matched by fingerprint."""
    before = _findings_by_fingerprint(base)
    after = _findings_by_fingerprint(head)
    new = [after[k] for k in after.keys() - before.keys()]
    resolved = [before[k] for k in before.keys() - after.keys()]

    base_tables = {t.table: t for t in base.report.tables}
    head_tables = {t.table: t for t in head.report.tables}

    changed = []
    for name in sorted(base_tables.keys() & head_tables.keys()):
        old, cur = base_tables[name], head_tables[name]
        n_new = sum(1 for f in new if f.table == name)
        n_resolved = sum(1 for f in resolved if f.table == name)
        if old.score != cur.score or n_new or n_resolved:
            changed.append(
                TableChange(
                    table=name,
                    score=ScoreChange(before=old.score, after=cur.score),
                    new_findings=n_new,
                    resolved_findings=n_resolved,
                )
            )

    def order(f: Finding) -> tuple[str, str, str]:
        return (f.table, f.column or "", f.check_id)

    return RunDiff(
        base=base.id,
        head=head.id,
        score=ScoreChange(before=base.report.score, after=head.report.score),
        dimensions={
            d: ScoreChange(
                before=base.report.dimensions.get(d), after=head.report.dimensions.get(d)
            )
            for d in Dimension
            if d in base.report.dimensions or d in head.report.dimensions
        },
        tables_added=tuple(sorted(head_tables.keys() - base_tables.keys())),
        tables_removed=tuple(sorted(base_tables.keys() - head_tables.keys())),
        tables_changed=tuple(changed),
        new_findings=tuple(sorted(new, key=order)),
        resolved_findings=tuple(sorted(resolved, key=order)),
        unchanged_findings=len(before.keys() & after.keys()),
        warnings=tuple(_comparability_warnings(base, head)),
    )
