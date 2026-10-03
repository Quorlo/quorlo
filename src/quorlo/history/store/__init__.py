"""Saved scan runs. A local SQLite file is the only backend for now.

Nothing here ever holds data from a scanned table: runs carry metadata and findings only.
"""

from quorlo.history.store.base import (
    FindingChanges,
    RunNotFoundError,
    RunStore,
    RunSummary,
    RunWriter,
    SinceLastRun,
    StoreError,
    default_store_path,
)
from quorlo.history.store.sqlite import SqliteRunStore, SqliteRunWriter

__all__ = [
    "FindingChanges",
    "RunNotFoundError",
    "RunStore",
    "RunSummary",
    "RunWriter",
    "SinceLastRun",
    "SqliteRunStore",
    "SqliteRunWriter",
    "StoreError",
    "default_store_path",
]
