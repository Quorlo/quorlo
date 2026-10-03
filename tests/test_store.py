import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from factories import make_column, make_table
from quorlo.history import ScanRun, diff_runs
from quorlo.models import Database, Schema
from quorlo.readiness import evaluate
from quorlo.store import (
    RunNotFoundError,
    RunStore,
    SqliteRunStore,
    StoreError,
    default_store_path,
)

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def database(description=None, location="postgres://h:5432/db"):
    table = make_table(
        "orders",
        description=description,
        columns=[make_column("order_id", "Key."), make_column("email")],
        primary_key=("order_id",),
    )
    return Database(
        name="db",
        platform="postgres",
        location=location,
        schemas=(Schema(name="public", tables=(table,)),),
    )


def run(db=None, at=T0, schemas=None):
    db = db or database()
    return ScanRun.record(
        db, evaluate(db), started_at=at, finished_at=at + timedelta(seconds=3), schemas=schemas
    )


@pytest.fixture
def store(tmp_path):
    with SqliteRunStore(tmp_path / "nested" / "quorlo.db") as s:
        yield s


def test_satisfies_protocol(store):
    assert isinstance(store, SqliteRunStore)
    _: RunStore = store


def test_creates_parent_directory_and_schema(tmp_path, store):
    assert (tmp_path / "nested" / "quorlo.db").exists()
    assert store.schema_version == 1


def test_save_and_get_round_trip(store):
    r = run(schemas=["public"])
    store.save(r)
    loaded = store.get(r.id)
    assert loaded == r
    assert loaded.started_at.tzinfo is not None


def test_get_by_unique_prefix(store):
    r = run()
    store.save(r)
    assert store.get(r.id[:12]).id == r.id


def test_get_unknown_or_ambiguous(store):
    store.save(run())
    store.save(run(at=T0 + timedelta(seconds=1)))
    with pytest.raises(RunNotFoundError, match="No saved run"):
        store.get("19990101")
    with pytest.raises(RunNotFoundError, match="more than one"):
        store.get("20261001T12")


def test_prefix_wildcards_are_literal(store):
    store.save(run())
    with pytest.raises(RunNotFoundError):
        store.get("%")
    with pytest.raises(RunNotFoundError):
        store.get("_")


def test_list_newest_first_and_by_target(store):
    a = run()
    b = run(at=T0 + timedelta(days=1))
    other = run(database(location="postgres://other:5432/db"), at=T0 + timedelta(days=2))
    for r in (a, b, other):
        store.save(r)
    assert [s.id for s in store.list()] == [other.id, b.id, a.id]
    assert [s.id for s in store.list(target=a.target)] == [b.id, a.id]
    assert len(store.list(limit=1)) == 1
    summary = store.list(target=a.target)[0]
    assert (summary.tables, summary.findings, summary.score) == (
        1,
        len(b.report.findings),
        b.report.score,
    )


def test_latest_matches_target_and_schemas(store):
    all_schemas = run()
    only_public = run(at=T0 + timedelta(hours=1), schemas=["public"])
    newer = run(at=T0 + timedelta(hours=2))
    for r in (all_schemas, only_public, newer):
        store.save(r)
    assert store.latest(newer.target).id == newer.id
    assert store.latest(newer.target, before=newer.started_at).id == all_schemas.id
    assert store.latest(newer.target, schemas=("public",)).id == only_public.id
    assert store.latest(run(database(location="postgres://x:1/db")).target) is None


def test_saved_runs_can_be_diffed(store):
    base = run()
    head = run(database(description="One row per order."), at=T0 + timedelta(days=1))
    store.save(base)
    store.save(head)
    diff = diff_runs(store.get(base.id), store.get(head.id))
    assert [f.check_id for f in diff.resolved_findings] == ["table.description.missing"]


def test_rows_are_queryable_with_plain_sql(tmp_path):
    path = tmp_path / "q.db"
    r = run()
    with SqliteRunStore(path) as s:
        s.save(r)
    conn = sqlite3.connect(path)
    overall = conn.execute(
        "SELECT score FROM table_scores WHERE table_name = 'db.public.orders' AND dimension = 'overall'"
    ).fetchone()[0]
    assert overall == pytest.approx(r.report.tables[0].score)
    governance = conn.execute(
        "SELECT score FROM table_scores WHERE dimension = 'governance'"
    ).fetchone()[0]
    assert governance == 0.0  # the email column
    fingerprints = {row[0] for row in conn.execute("SELECT fingerprint FROM findings")}
    assert fingerprints == {f.fingerprint for f in r.report.findings}


def test_duplicate_run_id_is_an_error(store):
    r = run()
    store.save(r)
    with pytest.raises(StoreError):
        store.save(r)
    assert len(store.list()) == 1  # the failed save left nothing behind


def test_refuses_a_store_from_a_newer_quorlo(tmp_path):
    path = tmp_path / "future.db"
    sqlite3.connect(path).execute("PRAGMA user_version = 99")
    with pytest.raises(StoreError, match="newer Quorlo"):
        SqliteRunStore(path)


def test_reopening_does_not_rerun_migrations(tmp_path):
    path = tmp_path / "q.db"
    r = run()
    with SqliteRunStore(path) as s:
        s.save(r)
    with SqliteRunStore(path) as s:
        assert s.schema_version == 1
        assert s.get(r.id) == r


def test_default_store_path(monkeypatch, tmp_path):
    monkeypatch.setenv("QUORLO_STORE", str(tmp_path / "custom.db"))
    assert default_store_path() == tmp_path / "custom.db"
    monkeypatch.delenv("QUORLO_STORE")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_store_path() == tmp_path / "xdg" / "quorlo" / "quorlo.db"
