from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import ClassVar

import pytest
from pydantic import SecretStr

from factories import make_column, make_table
from quorlo.connectors import (
    ConnectionConfig,
    ConnectorCapabilities,
    ConnectorError,
    DatabaseInfo,
    FetchStats,
)
from quorlo.models import Schema
from quorlo.readiness import ReadinessEngine
from quorlo.scanner import Scanner
from quorlo.stats import Phase
from quorlo.store import SqliteRunStore


class StreamingConnector:
    """Yields schemas one at a time and can check what the scan did in between."""

    name: ClassVar[str] = "stream"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig, schemas: int = 3, fail_at: int | None = None):
        self._count = schemas
        self._fail_at = fail_at
        self._stats = FetchStats()
        self.between_schemas = None  # called before each schema after the first

    def test_connection(self) -> None:
        pass

    def describe(self) -> DatabaseInfo:
        return DatabaseInfo(name="db", platform="stream", location="stream://test/db")

    def list_schemas(self) -> list[str]:
        return [f"s{i}" for i in range(self._count)]

    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
        for i in range(self._count):
            if i == self._fail_at:
                raise ConnectorError("connection lost")
            if i and self.between_schemas:
                self.between_schemas(i)
            self._stats = self._stats.plus(rows=2, seconds=0.0)
            table = make_table(
                "orders", schema=f"s{i}", columns=[make_column("c1"), make_column("email")]
            )
            yield Schema(name=f"s{i}", tables=(table,))

    @property
    def stats(self) -> FetchStats:
        return self._stats

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass


def connector(**kwargs) -> StreamingConnector:
    return StreamingConnector(ConnectionConfig(dsn=SecretStr("stream://")), **kwargs)


@pytest.fixture
def store(tmp_path):
    with SqliteRunStore(tmp_path / "runs.db") as s:
        yield s


def test_saved_scan_records_report_stats_and_findings(store):
    scanner = Scanner(ReadinessEngine(), store)
    outcome = scanner.scan(connector())

    assert outcome.saved
    stats = outcome.stats
    assert (stats.schemas, stats.tables, stats.columns, stats.queries) == (3, 3, 6, 3)
    assert set(stats.phases) == set(Phase)
    assert sum(stats.phases.values()) <= stats.seconds + 1e-6

    run = store.get(outcome.header.id)
    assert run.report == outcome.report
    assert run.stats == stats
    assert len(run.findings) == outcome.report.finding_count > 0
    assert [s.name for s in store.snapshot(run.id)] == ["s0", "s1", "s2"]
    assert list(scanner.findings(outcome)) == list(run.findings)


def test_schemas_are_saved_as_they_stream(store):
    seen = []
    source = connector()
    source.between_schemas = lambda i: seen.append(
        store._conn.execute("SELECT COUNT(*) FROM schema_snapshots").fetchone()[0]
    )
    Scanner(ReadinessEngine(), store).scan(source)
    assert seen == [1, 2]  # each schema was written before the next one was fetched


def test_second_scan_compares_with_the_first(store):
    scanner = Scanner(ReadinessEngine(), store)
    first = scanner.scan(connector())
    second = scanner.scan(connector())
    since = second.since_last_run
    assert since is not None
    assert since.previous.id == first.header.id
    assert (since.findings.new, since.findings.resolved) == (0, 0)
    assert since.findings.unchanged == first.report.finding_count
    assert first.since_last_run is None


def test_unsaved_scan_keeps_findings_in_memory():
    scanner = Scanner(ReadinessEngine())
    outcome = scanner.scan(connector())
    assert not outcome.saved
    assert outcome.stats.phases[Phase.PERSISTENCE] == 0
    assert len(list(scanner.findings(outcome))) == outcome.report.finding_count > 0


def test_interrupted_scan_leaves_no_visible_run(store):
    with pytest.raises(ConnectorError):
        Scanner(ReadinessEngine(), store).scan(connector(fail_at=2))
    assert store.list() == []
    status = store._conn.execute("SELECT status FROM runs").fetchall()
    assert [r[0] for r in status] == ["running"]
