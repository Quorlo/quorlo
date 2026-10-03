"""Scan runs over time: what a run holds, how two runs compare, and where runs are kept.

`models` is pure (no I/O); `store` saves and loads runs.
"""

from quorlo.history.findings import CheckGroup, FindingGrouper, FindingQuery, TableFindings
from quorlo.history.models import (
    RunDiff,
    RunHeader,
    RunTarget,
    ScanRun,
    ScoreChange,
    TableChange,
    diff_runs,
    new_run_id,
)
from quorlo.history.store import (
    FindingChanges,
    RunNotFoundError,
    RunStore,
    RunSummary,
    RunWriter,
    SinceLastRun,
    SqliteRunStore,
    SqliteRunWriter,
    StoreError,
    default_store_path,
)

__all__ = [
    "CheckGroup",
    "FindingChanges",
    "FindingGrouper",
    "FindingQuery",
    "RunDiff",
    "RunHeader",
    "RunNotFoundError",
    "RunStore",
    "RunSummary",
    "RunTarget",
    "RunWriter",
    "ScanRun",
    "ScoreChange",
    "SinceLastRun",
    "SqliteRunStore",
    "SqliteRunWriter",
    "StoreError",
    "TableChange",
    "TableFindings",
    "default_store_path",
    "diff_runs",
    "new_run_id",
]
