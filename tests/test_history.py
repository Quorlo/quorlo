from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from factories import make_column, make_table
from quorlo.history import RunTarget, ScanRun, diff_runs, new_run_id
from quorlo.models import Database, Schema
from quorlo.readiness import Dimension, evaluate
from quorlo.readiness.checks import ColumnDescriptionMissing, TableDescriptionMissing


def _evaluated(db, checks=None):
    evaluation = evaluate(db, checks) if checks else evaluate(db)
    return evaluation.report, evaluation.findings


T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CHECKS = (TableDescriptionMissing(), ColumnDescriptionMissing())


def database(*tables, location="postgres://h:5432/db"):
    return Database(
        name="db",
        platform="postgres",
        location=location,
        schemas=(Schema(name="public", tables=tables),),
    )


def run(db, at=T0, checks=CHECKS, schemas=None):
    return ScanRun.record(
        db, *_evaluated(db, checks), started_at=at, finished_at=at, schemas=schemas
    )


def orders(description=None, total_description=None):
    return make_table(
        "orders",
        description=description,
        columns=[make_column("order_id", "Key."), make_column("total", total_description)],
    )


def test_run_id_sorts_by_time():
    a, b = new_run_id(T0), new_run_id(T0 + timedelta(seconds=1))
    assert a.startswith("20261001T120000Z-")
    assert a < b


def test_record_captures_target_and_checks():
    r = run(database(orders()), schemas=["sales", "public"])
    assert r.target == RunTarget(
        platform="postgres", location="postgres://h:5432/db", database="db"
    )
    assert r.schemas == ("public", "sales")
    assert r.checks == {"table.description.missing": 1, "column.description.missing": 1}
    assert not hasattr(r, "snapshot")  # the store keeps metadata per schema, not the run


def test_timestamps_must_be_aware():
    db = database(orders())
    with pytest.raises(ValidationError, match="timezone-aware"):
        ScanRun.record(db, *_evaluated(db, CHECKS), started_at=datetime(2026, 1, 1))


def test_run_round_trips_through_json():
    r = run(database(orders()))
    assert ScanRun.model_validate_json(r.model_dump_json()) == r


def test_diff_shows_resolved_and_new_findings():
    base = run(database(orders()))
    # The table gets a description, but a new undocumented column appears.
    improved = make_table(
        "orders",
        description="One row per order.",
        columns=[
            make_column("order_id", "Key."),
            make_column("total", "Amount."),
            make_column("notes"),
        ],
    )
    head = run(database(improved), at=T0 + timedelta(days=1))
    diff = diff_runs(base, head)

    assert diff.base == base.id and diff.head == head.id
    assert [(f.check_id, f.column) for f in diff.resolved_findings] == [
        ("table.description.missing", None),
        ("column.description.missing", "total"),
    ]
    assert [(f.check_id, f.column) for f in diff.new_findings] == [
        ("column.description.missing", "notes")
    ]
    assert diff.unchanged_findings == 0
    assert diff.score.before < diff.score.after
    assert diff.score.delta == pytest.approx(diff.score.after - diff.score.before)
    assert diff.dimensions[Dimension.MEANING].delta > 0
    (change,) = diff.tables_changed
    assert (change.table, change.new_findings, change.resolved_findings) == (
        "db.public.orders",
        1,
        2,
    )
    assert diff.warnings == ()


def test_identical_runs_have_no_changes():
    base = run(database(orders()))
    head = run(database(orders()), at=T0 + timedelta(hours=1))
    diff = diff_runs(base, head)
    assert diff.new_findings == diff.resolved_findings == ()
    assert diff.tables_changed == ()
    assert diff.unchanged_findings == 2  # table description, and the `total` column
    assert diff.score.delta == 0


def test_tables_added_and_removed():
    base = run(database(orders(), make_table("legacy")))
    head = run(database(orders(), make_table("customers")))
    diff = diff_runs(base, head)
    assert diff.tables_added == ("db.public.customers",)
    assert diff.tables_removed == ("db.public.legacy",)
    assert {f.table for f in diff.resolved_findings} == {"db.public.legacy"}


def test_warns_when_check_rules_changed():
    class StricterTableDescription(TableDescriptionMissing):
        version = 2

    base = run(database(orders()))
    head = run(database(orders()), checks=(StricterTableDescription(), ColumnDescriptionMissing()))
    (warning,) = diff_runs(base, head).warnings
    assert "Check rules changed" in warning
    assert "table.description.missing" in warning


def test_warns_about_added_and_removed_checks():
    base = run(database(orders()), checks=(TableDescriptionMissing(),))
    head = run(database(orders()), checks=(ColumnDescriptionMissing(),))
    warnings = diff_runs(base, head).warnings
    assert any("added" in w and "column.description.missing" in w for w in warnings)
    assert any("no longer run" in w and "table.description.missing" in w for w in warnings)


def test_warns_about_different_targets_and_schemas():
    base = run(database(orders()), schemas=["public"])
    head = run(database(orders(), location="postgres://other:5432/db"))
    warnings = diff_runs(base, head).warnings
    assert any("Different targets" in w for w in warnings)
    assert any("public vs all schemas" in w for w in warnings)


def test_score_change_without_a_side_has_no_delta():
    base = run(Database(name="db", platform="postgres"))
    head = run(database(orders()))
    assert diff_runs(base, head).score.delta is None
