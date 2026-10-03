"""What any run store offers, independent of how it keeps runs."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from quorlo.history.findings import FindingQuery
from quorlo.history.models import RunHeader, RunTarget, ScanRun
from quorlo.models import Schema
from quorlo.readiness import Finding, ScanReport
from quorlo.stats import ScanStats


class StoreError(Exception):
    pass


class RunNotFoundError(StoreError):
    pass


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunSummary(_Frozen):
    """A finished run without its report, findings or snapshot, for listings."""

    id: str
    started_at: datetime
    target: RunTarget
    schemas: tuple[str, ...] | None
    score: float | None
    tables: int
    findings: int


class FindingChanges(_Frozen):
    """How two runs' findings compare, counted without loading either run's findings."""

    new: int
    resolved: int
    unchanged: int


class SinceLastRun(_Frozen):
    """A finished scan compared with the previous run of the same target and schemas."""

    previous: RunSummary
    score_before: float | None
    score_after: float | None
    findings: FindingChanges
    rules_changed: bool = False

    @classmethod
    def between(
        cls, store: RunStore, previous: RunSummary, run_id: str, report: ScanReport
    ) -> SinceLastRun:
        return cls(
            previous=previous,
            score_before=previous.score,
            score_after=report.score,
            findings=store.finding_changes(previous.id, run_id),
            rules_changed=store.report(previous.id).checks != report.checks,
        )


class RunWriter(Protocol):
    """A run being written while its scan streams. Also the scan's `FindingSink`."""

    def add(self, findings: Iterable[Finding]) -> None: ...

    def add_schema(self, schema: Schema) -> None:
        """Keep the scanned metadata of one schema."""
        ...

    def finish(
        self, report: ScanReport, finished_at: datetime, stats: ScanStats | None = None
    ) -> None:
        """Mark the run complete. A run that never finishes is never listed or compared."""
        ...


class RunStore(Protocol):
    def open_run(self, header: RunHeader) -> RunWriter: ...

    def save(self, run: ScanRun, schemas: Iterable[Schema] = ()) -> None:
        """Write a finished run held in memory in one go."""
        ...

    def get(self, run_id: str) -> ScanRun:
        """Load a finished run by its id, or by a prefix that matches exactly one run."""
        ...

    def summary(self, run_id: str) -> RunSummary:
        """A finished run's id, target and counts, by id or unique prefix."""
        ...

    def report(self, run_id: str) -> ScanReport:
        """A finished run's scores, without loading its findings."""
        ...

    def snapshot(self, run_id: str) -> Iterator[Schema]:
        """The metadata a run scanned, one schema at a time."""
        ...

    def findings(self, run_id: str, query: FindingQuery | None = None) -> Iterator[Finding]:
        """A run's findings, filtered and grouped by table, streamed rather than loaded."""
        ...

    def list(self, target: RunTarget | None = None, limit: int = 20) -> list[RunSummary]:
        """Finished runs, newest first."""
        ...

    def previous(self, header: RunHeader) -> RunSummary | None:
        """The newest finished run before this one, of the same target and schemas."""
        ...

    def latest(self, target: RunTarget, schemas: tuple[str, ...] | None = None) -> ScanRun | None:
        """The newest finished run of this target that scanned the same schemas."""
        ...

    def finding_changes(self, base_id: str, head_id: str) -> FindingChanges: ...


def default_store_path() -> Path:
    """$QUORLO_STORE, else the per-user data directory for this platform."""
    if env := os.environ.get("QUORLO_STORE"):
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "quorlo" / "quorlo.db"
