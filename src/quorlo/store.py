"""Saving scan runs. A local SQLite file is the only backend for now.

Each run is stored twice over, on purpose:

- the full run as compressed JSON, so loading it back is exact; and
- per-table scores and findings as plain rows, so the history can be queried with any
  SQLite client ("which tables got worse this month?").

Nothing here ever holds data from a scanned table: runs carry metadata and findings only.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from quorlo.history import RunTarget, ScanRun
from quorlo.models import Database
from quorlo.readiness import ScanReport


class StoreError(Exception):
    pass


class RunNotFoundError(StoreError):
    pass


class RunSummary(BaseModel):
    """A run without its report and snapshot, for listings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    started_at: datetime
    target: RunTarget
    schemas: tuple[str, ...] | None
    score: float | None
    tables: int
    findings: int


class RunStore(Protocol):
    def save(self, run: ScanRun) -> None: ...

    def get(self, run_id: str) -> ScanRun:
        """Load a run by its id, or by a prefix that matches exactly one run."""
        ...

    def list(self, target: RunTarget | None = None, limit: int = 20) -> list[RunSummary]:
        """Newest first."""
        ...

    def latest(
        self,
        target: RunTarget,
        schemas: tuple[str, ...] | None = None,
        before: datetime | None = None,
    ) -> ScanRun | None:
        """The newest run of this target that scanned the same schemas, if any."""
        ...


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


# Each entry upgrades the schema by one version; never edit one that has shipped.
_MIGRATIONS = [
    """
    CREATE TABLE runs (
        id              TEXT PRIMARY KEY,
        started_at      TEXT NOT NULL,          -- ISO 8601, UTC
        finished_at     TEXT NOT NULL,
        quorlo_version  TEXT NOT NULL,
        platform        TEXT NOT NULL,
        location        TEXT,                   -- never contains credentials
        database        TEXT NOT NULL,
        target_key      TEXT NOT NULL,
        schemas         TEXT,                   -- comma-separated; NULL means all
        score           REAL,
        table_count     INTEGER NOT NULL,
        finding_count   INTEGER NOT NULL,
        report          BLOB NOT NULL,          -- zlib-compressed ScanReport JSON
        snapshot        BLOB NOT NULL           -- zlib-compressed Database JSON
    );
    CREATE INDEX runs_by_target ON runs (target_key, started_at);

    CREATE TABLE table_scores (
        run_id      TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
        table_name  TEXT NOT NULL,
        dimension   TEXT NOT NULL,              -- 'overall' or a dimension name
        score       REAL,
        PRIMARY KEY (run_id, table_name, dimension)
    );

    CREATE TABLE findings (
        run_id       TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
        fingerprint  TEXT NOT NULL,
        check_id     TEXT NOT NULL,
        dimension    TEXT NOT NULL,
        severity     TEXT NOT NULL,
        table_name   TEXT NOT NULL,
        column_name  TEXT,
        message      TEXT NOT NULL
    );
    CREATE INDEX findings_by_run ON findings (run_id);
    CREATE INDEX findings_by_fingerprint ON findings (fingerprint);
    """,
]


def _target_key(target: RunTarget) -> str:
    return "\x1f".join((target.platform, target.location or "", target.database))


def _schemas_text(schemas: tuple[str, ...] | None) -> str | None:
    return ",".join(schemas) if schemas else None


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _pack(model: BaseModel) -> bytes:
    return zlib.compress(model.model_dump_json().encode())


class SqliteRunStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        try:
            if str(path) != ":memory:":
                self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
        except (OSError, sqlite3.Error) as exc:
            raise StoreError(f"Cannot open the run store at {self.path}: {exc}") from None
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        current = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if current > len(_MIGRATIONS):
            raise StoreError(
                f"The run store at {self.path} was written by a newer Quorlo "
                f"(schema {current}, this version knows {len(_MIGRATIONS)}). Upgrade Quorlo."
            )
        for version, script in enumerate(_MIGRATIONS[current:], start=current + 1):
            # One transaction per step, so a failed upgrade leaves the previous version intact.
            try:
                self._conn.executescript(
                    f"BEGIN; {script}; PRAGMA user_version = {version}; COMMIT;"
                )
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise StoreError(f"Cannot upgrade the run store at {self.path}: {exc}") from None

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            with self._conn:
                yield self._conn
        except sqlite3.Error as exc:
            raise StoreError(f"Run store error: {exc}") from None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteRunStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    # --- writing -------------------------------------------------------------------------

    def save(self, run: ScanRun) -> None:
        report = run.report
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run.id,
                    _utc(run.started_at),
                    _utc(run.finished_at),
                    run.quorlo_version,
                    run.target.platform,
                    run.target.location,
                    run.target.database,
                    _target_key(run.target),
                    _schemas_text(run.schemas),
                    report.score,
                    len(report.tables),
                    len(report.findings),
                    _pack(report),
                    _pack(run.snapshot),
                ),
            )
            conn.executemany(
                "INSERT INTO table_scores VALUES (?, ?, ?, ?)",
                [
                    (run.id, t.table, dimension, score)
                    for t in report.tables
                    for dimension, score in [
                        ("overall", t.score),
                        *((d.value, s) for d, s in t.dimensions.items()),
                    ]
                ],
            )
            conn.executemany(
                "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run.id,
                        f.fingerprint,
                        f.check_id,
                        f.dimension.value,
                        f.severity.value,
                        f.table,
                        f.column,
                        f.message,
                    )
                    for f in report.findings
                ],
            )

    # --- reading -------------------------------------------------------------------------

    def _load(self, row: sqlite3.Row) -> ScanRun:
        return ScanRun(
            id=row["id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            quorlo_version=row["quorlo_version"],
            target=RunTarget(
                platform=row["platform"], location=row["location"], database=row["database"]
            ),
            schemas=tuple(row["schemas"].split(",")) if row["schemas"] else None,
            report=ScanReport.model_validate_json(zlib.decompress(row["report"])),
            snapshot=Database.model_validate_json(zlib.decompress(row["snapshot"])),
        )

    def get(self, run_id: str) -> ScanRun:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE id = ? OR id LIKE ? ESCAPE '\\' ORDER BY id LIMIT 2",
            (run_id, run_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"),
        ).fetchall()
        exact = [r for r in rows if r["id"] == run_id]
        if exact:
            return self._load(exact[0])
        if not rows:
            raise RunNotFoundError(f"No saved run matches {run_id!r}.")
        if len(rows) > 1:
            raise RunNotFoundError(f"{run_id!r} matches more than one run; give more of the id.")
        return self._load(rows[0])

    def list(self, target: RunTarget | None = None, limit: int = 20) -> list[RunSummary]:
        sql = "SELECT * FROM runs"
        params: tuple = ()
        if target is not None:
            sql += " WHERE target_key = ?"
            params = (_target_key(target),)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        return [
            RunSummary(
                id=r["id"],
                started_at=datetime.fromisoformat(r["started_at"]),
                target=RunTarget(
                    platform=r["platform"], location=r["location"], database=r["database"]
                ),
                schemas=tuple(r["schemas"].split(",")) if r["schemas"] else None,
                score=r["score"],
                tables=r["table_count"],
                findings=r["finding_count"],
            )
            for r in self._conn.execute(sql, (*params, limit))
        ]

    def latest(
        self,
        target: RunTarget,
        schemas: tuple[str, ...] | None = None,
        before: datetime | None = None,
    ) -> ScanRun | None:
        sql = "SELECT * FROM runs WHERE target_key = ? AND schemas IS ?"
        params: list = [_target_key(target), _schemas_text(schemas)]
        if before is not None:
            sql += " AND started_at < ?"
            params.append(_utc(before))
        row = self._conn.execute(
            sql + " ORDER BY started_at DESC, id DESC LIMIT 1", params
        ).fetchone()
        return self._load(row) if row else None


__all__ = [
    "RunNotFoundError",
    "RunStore",
    "RunSummary",
    "SqliteRunStore",
    "StoreError",
    "default_store_path",
]
