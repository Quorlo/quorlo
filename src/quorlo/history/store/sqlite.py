"""A run store in a local SQLite file.

Runs are written while their scan streams: findings in batches and metadata one schema
at a time, so a large scan never has to be held in memory to be saved. Besides the
report JSON, scores and findings are plain rows that any SQLite client can query.
"""

from __future__ import annotations

import sqlite3
import zlib
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from quorlo.history.findings import FindingQuery
from quorlo.history.models import RunHeader, RunTarget, ScanRun
from quorlo.history.store.base import (
    FindingChanges,
    RunNotFoundError,
    RunSummary,
    StoreError,
)
from quorlo.history.store.migrations import MIGRATIONS
from quorlo.models import Schema
from quorlo.readiness import Finding, ScanReport
from quorlo.stats import ScanStats

_RUNNING, _COMPLETE = "running", "complete"


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _pack(model: BaseModel) -> bytes:
    return zlib.compress(model.model_dump_json().encode())


def _target_key(target: RunTarget) -> str:
    return "\x1f".join((target.platform, target.location or "", target.database))


def _schemas_text(schemas: tuple[str, ...] | None) -> str | None:
    return ",".join(schemas) if schemas else None


def _schemas_tuple(text: str | None) -> tuple[str, ...] | None:
    return tuple(text.split(",")) if text else None


class _FindingRows:
    """Maps findings to and from rows of the `findings` table."""

    # Finding field -> column. The fingerprint is derived, so it is stored but not read.
    FIELDS: ClassVar[dict[str, str]] = {
        "check_id": "check_id",
        "dimension": "dimension",
        "severity": "severity",
        "scope": "scope",
        "table": "table_name",
        "column": "column_name",
        "key": "finding_key",
        "message": "message",
        "remedy": "remedy",
    }
    INSERT: ClassVar[str] = (
        f"INSERT INTO findings (run_id, fingerprint, {', '.join(FIELDS.values())}) "
        f"VALUES ({', '.join('?' * (len(FIELDS) + 2))})"
    )
    SELECT_ALL: ClassVar[str] = f"SELECT {', '.join(FIELDS.values())} FROM findings"
    SELECT: ClassVar[str] = (
        f"SELECT {', '.join(FIELDS.values())} FROM findings WHERE run_id = ? ORDER BY rowid"
    )

    @classmethod
    def row(cls, run_id: str, finding: Finding) -> tuple[object, ...]:
        data = finding.model_dump(mode="json")
        return (run_id, finding.fingerprint, *(data[field] for field in cls.FIELDS))

    @classmethod
    def finding(cls, row: sqlite3.Row) -> Finding:
        return Finding(**{field: row[column] for field, column in cls.FIELDS.items()})


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _FindingFilter:
    """Turns a FindingQuery into an SQL condition, so filtering never loads a whole run."""

    def __init__(self, query: FindingQuery) -> None:
        self._query = query

    def sql(self) -> tuple[str, list[object]]:
        clauses: list[str] = []
        params: list[object] = []
        if self._query.tables:
            # The table itself, or any table whose qualified name ends in ".<value>".
            clauses.append(
                "("
                + " OR ".join(
                    "table_name = ? OR table_name LIKE ? ESCAPE '\\'" for _ in self._query.tables
                )
                + ")"
            )
            for table in self._query.tables:
                params += [table, f"%.{_like_escape(table)}"]
        for column, values in (
            ("dimension", [d.value for d in self._query.dimensions]),
            ("check_id", list(self._query.checks)),
        ):
            if values:
                clauses.append(f"{column} IN ({', '.join('?' * len(values))})")
                params += values
        return "".join(f" AND {c}" for c in clauses), params


class SqliteRunWriter:
    """Writes one run as its scan streams. Each batch is its own transaction."""

    batch_size: ClassVar[int] = 5000

    def __init__(self, store: SqliteRunStore, header: RunHeader) -> None:
        self._store = store
        self._run_id = header.id
        self._pending: list[Finding] = []
        self._schemas = 0

    def add(self, findings: Iterable[Finding]) -> None:
        self._pending.extend(findings)
        if len(self._pending) >= self.batch_size:
            self._flush()

    def add_schema(self, schema: Schema) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "INSERT INTO schema_snapshots VALUES (?, ?, ?, ?)",
                (self._run_id, self._schemas, schema.name, _pack(schema)),
            )
        self._schemas += 1

    def finish(
        self, report: ScanReport, finished_at: datetime, stats: ScanStats | None = None
    ) -> None:
        self._flush()
        with self._store.transaction() as conn:
            conn.executemany(
                "INSERT INTO table_scores VALUES (?, ?, ?, ?)",
                [
                    (self._run_id, t.table, dimension, score)
                    for t in report.tables
                    for dimension, score in [
                        ("overall", t.score),
                        *((d.value, s) for d, s in t.dimensions.items()),
                    ]
                ],
            )
            conn.execute(
                "UPDATE runs SET finished_at = ?, score = ?, table_count = ?, "
                "finding_count = ?, report = ?, stats = ?, status = ? WHERE id = ?",
                (
                    _utc(finished_at),
                    report.score,
                    len(report.tables),
                    report.finding_count,
                    _pack(report),
                    stats.model_dump_json() if stats else None,
                    _COMPLETE,
                    self._run_id,
                ),
            )

    def _flush(self) -> None:
        if not self._pending:
            return
        with self._store.transaction() as conn:
            conn.executemany(
                _FindingRows.INSERT, [_FindingRows.row(self._run_id, f) for f in self._pending]
            )
        self._pending.clear()


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
        self._conn.isolation_level = None  # transactions are begun explicitly, never implied
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL with NORMAL sync: a commit no longer waits for the disk, so writing a large
        # scan in batches is fast. Still crash-safe; only a power cut can lose the last
        # commit, and an unfinished run is never shown as complete anyway.
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    # --- lifecycle -----------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteRunStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def schema_version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self) -> None:
        current = self.schema_version
        if current > len(MIGRATIONS):
            raise StoreError(
                f"The run store at {self.path} was written by a newer Quorlo "
                f"(schema {current}, this version knows {len(MIGRATIONS)}). Upgrade Quorlo."
            )
        for version, migration in enumerate(MIGRATIONS[current:], start=current + 1):
            # One transaction per step, so a failed upgrade leaves the previous version intact.
            with self.transaction(f"Cannot upgrade the run store at {self.path}") as conn:
                migration.apply(conn)
                conn.execute(f"PRAGMA user_version = {version}")

    @contextmanager
    def transaction(self, failure: str = "Run store error") -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise StoreError(f"{failure}: {exc}") from None
        except BaseException:
            self._conn.rollback()
            raise
        self._conn.commit()

    # --- writing -------------------------------------------------------------------------

    def open_run(self, header: RunHeader) -> SqliteRunWriter:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO runs (id, started_at, finished_at, quorlo_version, platform, "
                "location, database, target_key, schemas, score, table_count, finding_count, "
                "report, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, ?, ?)",
                (
                    header.id,
                    _utc(header.started_at),
                    _utc(header.started_at),
                    header.quorlo_version,
                    header.target.platform,
                    header.target.location,
                    header.target.database,
                    _target_key(header.target),
                    _schemas_text(header.schemas),
                    b"",
                    _RUNNING,
                ),
            )
        return SqliteRunWriter(self, header)

    def save(self, run: ScanRun, schemas: Iterable[Schema] = ()) -> None:
        header = RunHeader.model_validate(run.model_dump(include=set(RunHeader.model_fields)))
        writer = self.open_run(header)
        for schema in schemas:
            writer.add_schema(schema)
        writer.add(run.findings)
        writer.finish(run.report, run.finished_at, run.stats)

    # --- reading -------------------------------------------------------------------------

    def get(self, run_id: str) -> ScanRun:
        return self._load(self._resolve(run_id))

    def report(self, run_id: str) -> ScanReport:
        """A finished run's scores alone: cheap, since findings are not loaded."""
        return ScanReport.model_validate_json(zlib.decompress(self._resolve(run_id)["report"]))

    def snapshot(self, run_id: str) -> Iterator[Schema]:
        rows = self._conn.execute(
            "SELECT snapshot FROM schema_snapshots WHERE run_id = ? ORDER BY position",
            (self._resolve(run_id)["id"],),
        )
        for row in rows:
            yield Schema.model_validate_json(zlib.decompress(row["snapshot"]))

    def findings(self, run_id: str, query: FindingQuery | None = None) -> Iterator[Finding]:
        where, params = _FindingFilter(query or FindingQuery()).sql()
        rows = self._conn.execute(
            f"{_FindingRows.SELECT_ALL} WHERE run_id = ?{where} ORDER BY table_name, rowid",
            (self._resolve(run_id)["id"], *params),
        )
        for row in rows:
            yield _FindingRows.finding(row)

    def list(self, target: RunTarget | None = None, limit: int = 20) -> list[RunSummary]:
        sql = f"SELECT * FROM runs WHERE status = '{_COMPLETE}'"
        params: tuple = ()
        if target is not None:
            sql += " AND target_key = ?"
            params = (_target_key(target),)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        return [self._summary(row) for row in self._conn.execute(sql, (*params, limit))]

    def previous(self, header: RunHeader) -> RunSummary | None:
        row = self._newest(header.target, header.schemas, before=header.started_at)
        return self._summary(row) if row else None

    def latest(self, target: RunTarget, schemas: tuple[str, ...] | None = None) -> ScanRun | None:
        row = self._newest(target, schemas)
        return self._load(row) if row else None

    def finding_changes(self, base_id: str, head_id: str) -> FindingChanges:
        row = self._conn.execute(
            """
            WITH base AS (SELECT DISTINCT fingerprint FROM findings WHERE run_id = :base),
                 head AS (SELECT DISTINCT fingerprint FROM findings WHERE run_id = :head)
            SELECT
                (SELECT COUNT(*) FROM head WHERE fingerprint NOT IN base) AS new,
                (SELECT COUNT(*) FROM base WHERE fingerprint NOT IN head) AS resolved,
                (SELECT COUNT(*) FROM head WHERE fingerprint IN base) AS unchanged
            """,
            {"base": base_id, "head": head_id},
        ).fetchone()
        return FindingChanges(new=row["new"], resolved=row["resolved"], unchanged=row["unchanged"])

    def _resolve(self, run_id: str) -> sqlite3.Row:
        """The finished run with this id, or the only one whose id starts with it."""
        pattern = _like_escape(run_id) + "%"
        rows = self._conn.execute(
            f"SELECT * FROM runs WHERE status = '{_COMPLETE}' "
            "AND (id = ? OR id LIKE ? ESCAPE '\\') ORDER BY id LIMIT 2",
            (run_id, pattern),
        ).fetchall()
        exact = [r for r in rows if r["id"] == run_id]
        if exact:
            return exact[0]
        if not rows:
            raise RunNotFoundError(f"No saved run matches {run_id!r}.")
        if len(rows) > 1:
            raise RunNotFoundError(f"{run_id!r} matches more than one run; give more of the id.")
        return rows[0]

    def _newest(
        self,
        target: RunTarget,
        schemas: tuple[str, ...] | None,
        before: datetime | None = None,
    ) -> sqlite3.Row | None:
        sql = f"SELECT * FROM runs WHERE status = '{_COMPLETE}' AND target_key = ? AND schemas IS ?"
        params: list = [_target_key(target), _schemas_text(schemas)]
        if before is not None:
            sql += " AND started_at < ?"
            params.append(_utc(before))
        return self._conn.execute(
            sql + " ORDER BY started_at DESC, id DESC LIMIT 1", params
        ).fetchone()

    def _load(self, row: sqlite3.Row) -> ScanRun:
        findings = self._conn.execute(_FindingRows.SELECT, (row["id"],))
        return ScanRun(
            id=row["id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            quorlo_version=row["quorlo_version"],
            target=self._target(row),
            schemas=_schemas_tuple(row["schemas"]),
            report=ScanReport.model_validate_json(zlib.decompress(row["report"])),
            findings=tuple(_FindingRows.finding(f) for f in findings),
            stats=ScanStats.model_validate_json(row["stats"]) if row["stats"] else None,
        )

    @staticmethod
    def _target(row: sqlite3.Row) -> RunTarget:
        return RunTarget(
            platform=row["platform"], location=row["location"], database=row["database"]
        )

    def _summary(self, row: sqlite3.Row) -> RunSummary:
        return RunSummary(
            id=row["id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            target=self._target(row),
            schemas=_schemas_tuple(row["schemas"]),
            score=row["score"],
            tables=row["table_count"],
            findings=row["finding_count"],
        )
