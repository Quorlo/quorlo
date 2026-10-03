import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from factories import make_column, make_table
from quorlo.history import RunHeader, ScanRun, diff_runs
from quorlo.models import Database, Schema
from quorlo.readiness import evaluate
from quorlo.store import (
    RunNotFoundError,
    RunStore,
    SinceLastRun,
    SqliteRunStore,
    SqliteRunWriter,
    StoreError,
    default_store_path,
)


def _evaluated(db, checks=None):
    evaluation = evaluate(db, checks) if checks else evaluate(db)
    return evaluation.report, evaluation.findings


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
        db, *_evaluated(db), started_at=at, finished_at=at + timedelta(seconds=3), schemas=schemas
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
    assert store.schema_version == 4


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
        len(b.findings),
        b.report.score,
    )


def test_latest_matches_target_and_schemas(store):
    all_schemas = run()
    only_public = run(at=T0 + timedelta(hours=1), schemas=["public"])
    newer = run(at=T0 + timedelta(hours=2))
    for r in (all_schemas, only_public, newer):
        store.save(r)
    assert store.latest(newer.target).id == newer.id
    assert store.previous(newer).id == all_schemas.id
    assert store.previous(all_schemas) is None
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
    assert fingerprints == {f.fingerprint for f in r.findings}


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
        assert s.schema_version == 4
        assert s.get(r.id) == r


def test_default_store_path(monkeypatch, tmp_path):
    monkeypatch.setenv("QUORLO_STORE", str(tmp_path / "custom.db"))
    assert default_store_path() == tmp_path / "custom.db"
    monkeypatch.delenv("QUORLO_STORE")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_store_path() == tmp_path / "xdg" / "quorlo" / "quorlo.db"


def test_upgrades_a_version_1_store_without_losing_findings(tmp_path):
    """v1 kept full findings inside the report JSON; v2 keeps them as complete rows."""
    import json
    import zlib

    from quorlo.store.migrations import _SCHEMA_V1, SqlMigration

    r = run()
    path = tmp_path / "v1.db"
    conn = sqlite3.connect(path)
    for statement in SqlMigration(_SCHEMA_V1).statements():
        conn.execute(statement)
    v1_report = r.report.model_dump(mode="json")
    for table in v1_report["tables"]:
        table.pop("finding_count")
        table["findings"] = [
            f.model_dump(mode="json") for f in r.findings if f.table == table["table"]
        ]
    conn.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (r.id, r.started_at.isoformat(), r.finished_at.isoformat(), "0.0.1", "postgres",
         r.target.location, "db", "postgres\x1fpostgres://h:5432/db\x1fdb", None, r.report.score,
         1, len(r.findings), zlib.compress(json.dumps(v1_report).encode()),
         zlib.compress(database().model_dump_json().encode())),
    )  # fmt: skip
    conn.executemany(
        "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(r.id, f.fingerprint, f.check_id, f.dimension.value, f.severity.value, f.table,
          f.column, f.message) for f in r.findings],
    )  # fmt: skip
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    with SqliteRunStore(path) as store:
        assert store.schema_version == 4
        upgraded = store.get(r.id)
        snapshot = list(store.snapshot(r.id))
    assert upgraded.findings == r.findings  # remedy, scope and key recovered from the blob
    assert upgraded.report == r.report  # finding_count filled in, findings moved out
    assert snapshot == list(database().schemas)  # v3: one snapshot row per schema


def test_sql_migration_splits_on_real_statement_ends_only():
    from quorlo.store.migrations import SqlMigration

    script = "CREATE TABLE a (x TEXT); -- a comment; with a semicolon\nCREATE TABLE b (y TEXT);\n"
    assert len(list(SqlMigration(script).statements())) == 2


# --- incremental writing (schema v3) --------------------------------------------------


def test_run_is_invisible_until_finished(store):
    r = run()
    writer = store.open_run(RunHeader.start(r.target, started_at=r.started_at))
    writer.add(r.findings)
    assert store.list() == []
    assert store.previous(run(at=T0 + timedelta(days=1))) is None
    with pytest.raises(RunNotFoundError):
        store.get(writer._run_id)
    writer.finish(r.report, r.finished_at)
    assert len(store.list()) == 1


def test_writer_flushes_findings_in_batches(store, monkeypatch):
    monkeypatch.setattr(SqliteRunWriter, "batch_size", 2)
    r = run()
    writer = store.open_run(RunHeader.start(r.target, started_at=r.started_at))
    writer.add(r.findings[:1])
    assert _rows(store, "findings") == 0  # below the batch size: still buffered
    writer.add(r.findings[1:])
    assert _rows(store, "findings") == len(r.findings)
    writer.finish(r.report, r.finished_at)
    assert store.get(writer._run_id).findings == r.findings


def test_snapshot_streams_schemas_in_scan_order(store):
    r = run()
    schemas = [Schema(name=n, tables=()) for n in ("zeta", "alpha", "mid")]
    store.save(r, schemas)
    assert [s.name for s in store.snapshot(r.id)] == ["zeta", "alpha", "mid"]


def test_finding_changes_are_counted_in_sql(store):
    base = run()
    head = run(database(description="One row per order."), at=T0 + timedelta(days=1))
    store.save(base)
    store.save(head)
    changes = store.finding_changes(base.id, head.id)
    diff = diff_runs(base, head)
    assert (changes.new, changes.resolved, changes.unchanged) == (
        len(diff.new_findings),
        len(diff.resolved_findings),
        diff.unchanged_findings,
    )
    assert changes.resolved == 1


def test_report_loads_scores_without_findings(store):
    r = run()
    store.save(r)
    assert store.report(r.id) == r.report


def test_since_last_run(store):
    base = run()
    head = run(database(description="One row per order."), at=T0 + timedelta(days=1))
    store.save(base)
    store.save(head)
    since = SinceLastRun.between(store, store.previous(head), head.id, head.report)
    assert since.previous.id == base.id
    assert (since.score_before, since.score_after) == (base.report.score, head.report.score)
    assert since.findings.resolved == 1
    assert not since.rules_changed


def _rows(store, table):
    return store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
