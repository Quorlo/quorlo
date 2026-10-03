"""The run store's schema history. Never edit a step that has shipped; add a new one."""

from __future__ import annotations

import json
import sqlite3
import zlib
from collections.abc import Callable, Iterator
from typing import Protocol

from quorlo.models import Database
from quorlo.readiness import Finding


class Migration(Protocol):
    """One step up in the store's schema version."""

    def apply(self, conn: sqlite3.Connection) -> None: ...


class SqlMigration:
    def __init__(self, script: str) -> None:
        self._script = script

    def apply(self, conn: sqlite3.Connection) -> None:
        # Not executescript(): it commits first, which would break the step's transaction.
        for statement in self.statements():
            conn.execute(statement)

    def statements(self) -> Iterator[str]:
        """Split on statement boundaries as SQLite's own tokenizer sees them, so a ';'
        inside a comment or string does not end a statement."""
        pending = ""
        for line in self._script.splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                yield pending
                pending = ""
        if pending.strip():
            raise ValueError(f"Incomplete SQL statement in migration: {pending.strip()[:60]}")


class PythonMigration:
    """A step that has to transform existing rows, not just reshape tables."""

    def __init__(self, step: Callable[[sqlite3.Connection], None]) -> None:
        self._step = step

    def apply(self, conn: sqlite3.Connection) -> None:
        self._step(conn)


_SCHEMA_V1 = """
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
"""


def _complete_finding_rows(conn: sqlite3.Connection) -> None:
    """v2: findings move out of the report JSON into complete rows.

    v1 kept each finding twice: in full inside the report blob, and partly as a row.
    Fill in the missing columns from the blob, then drop findings from the blob.
    """
    for column in ("scope TEXT", "finding_key TEXT", "remedy TEXT"):
        conn.execute(f"ALTER TABLE findings ADD COLUMN {column}")
    for run_id, blob in conn.execute("SELECT id, report FROM runs").fetchall():
        report = json.loads(zlib.decompress(blob))
        for table in report["tables"]:
            findings = table.pop("findings", [])
            table["finding_count"] = len(findings)
            for f in findings:
                finding = Finding.model_validate(f)
                conn.execute(
                    "UPDATE findings SET scope = ?, finding_key = ?, remedy = ? "
                    "WHERE run_id = ? AND fingerprint = ?",
                    (finding.scope.value, finding.key, finding.remedy, run_id, finding.fingerprint),
                )
        conn.execute(
            "UPDATE runs SET report = ? WHERE id = ?",
            (zlib.compress(json.dumps(report).encode()), run_id),
        )


def _split_snapshots_and_track_status(conn: sqlite3.Connection) -> None:
    """v3: runs are written incrementally while a scan streams.

    The metadata snapshot moves from one blob per run to one row per schema, so it can be
    written schema by schema and read back the same way. Runs get a status, so a scan
    that never finished is not mistaken for a complete one.
    """
    conn.execute(
        """
        CREATE TABLE schema_snapshots (
            run_id       TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
            position     INTEGER NOT NULL,      -- order in which the scan saw the schema
            schema_name  TEXT NOT NULL,
            snapshot     BLOB NOT NULL,         -- zlib-compressed Schema JSON
            PRIMARY KEY (run_id, position)
        )
        """
    )
    conn.execute("ALTER TABLE runs ADD COLUMN status TEXT NOT NULL DEFAULT 'complete'")
    for run_id, blob in conn.execute("SELECT id, snapshot FROM runs").fetchall():
        database = Database.model_validate_json(zlib.decompress(blob))
        conn.executemany(
            "INSERT INTO schema_snapshots VALUES (?, ?, ?, ?)",
            [
                (run_id, position, schema.name, zlib.compress(schema.model_dump_json().encode()))
                for position, schema in enumerate(database.schemas)
            ],
        )
    conn.execute("ALTER TABLE runs DROP COLUMN snapshot")


# v4: each run keeps its timing and size (ScanStats JSON); NULL for older runs.
_RUN_STATS = "ALTER TABLE runs ADD COLUMN stats TEXT;"

MIGRATIONS: list[Migration] = [
    SqlMigration(_SCHEMA_V1),
    PythonMigration(_complete_finding_rows),
    PythonMigration(_split_snapshots_and_track_status),
    SqlMigration(_RUN_STATS),
]
