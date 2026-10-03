import pytest

from factories import make_column, make_table
from quorlo.models import Database, Schema, TableKind
from quorlo.readiness import Dimension, ScanContext, Scope, Severity, evaluate, evaluate_table
from quorlo.readiness.checks import (
    ColumnDescriptionMissing,
    ColumnNameCryptic,
    PrimaryKeyMissing,
    TableDescriptionMissing,
)

# Pinned, so these scoring tests don't shift each time a check is added to the defaults.
CHECKS = (
    TableDescriptionMissing(),
    ColumnDescriptionMissing(),
    PrimaryKeyMissing(),
    ColumnNameCryptic(),
)


def documented_table():
    return make_table(
        "customers",
        description="One row per customer.",
        columns=[
            make_column("customer_id", "Surrogate key."),
            make_column("email", "Contact email address."),
        ],
        primary_key=("customer_id",),
    )


def test_fully_documented_table_scores_one():
    result = evaluate_table(documented_table(), CHECKS)
    assert result.score == 1.0
    assert result.dimensions == {Dimension.MEANING: 1.0}
    assert not result.findings


def test_empty_table_scores_zero():
    table = make_table("stg", columns=[make_column("c1"), make_column("c2")])
    result = evaluate_table(table, CHECKS)
    assert result.score == 0.0
    by_check = {r.check_id: r for r in result.checks}
    assert by_check["column.description.missing"].evaluated == 2
    assert by_check["column.description.missing"].failed == 2
    assert by_check["table.description.missing"].evaluated == 1


def test_score_is_weighted_per_check_not_per_unit():
    # 20 documented, readable columns and a key, but no table description (weight 2 of 5).
    columns = [make_column(f"metric_number_{w}", "Documented.") for w in "abcdefghijklmnopqrst"]
    table = make_table(columns=columns, primary_key=("metric_number_a",))
    result = evaluate_table(table, CHECKS)
    assert result.score == pytest.approx(1 - 2 / 5)


def test_partial_column_failures():
    table = documented_table().model_copy(
        update={"columns": (*documented_table().columns, make_column("notes", ordinal=3))}
    )
    result = evaluate_table(table, CHECKS)
    by_check = {r.check_id: r for r in result.checks}
    assert by_check["column.description.missing"].pass_rate == pytest.approx(2 / 3)
    # weights: table desc 2, column desc 1, pk 1, cryptic 1
    assert result.score == pytest.approx((2 + 2 / 3 + 1 + 1) / 5)


def test_views_are_not_penalised_for_missing_primary_key():
    view = make_table(
        "v", kind=TableKind.VIEW, description="A view.", columns=[make_column("id", "Key.")]
    )
    result = evaluate_table(view, CHECKS)
    assert "table.primary_key.missing" not in {r.check_id for r in result.checks}
    assert result.score == 1.0


def test_report_averages_tables_and_dimensions():
    bad = make_table("stg", columns=[make_column("c1")])
    db = Database(
        name="db",
        platform="test",
        schemas=(Schema(name="public", tables=(documented_table(), bad)),),
    )
    report = evaluate(db, CHECKS)
    assert [t.table for t in report.tables] == ["db.public.customers", "db.public.stg"]
    assert report.score == pytest.approx(0.5)
    assert report.dimensions[Dimension.MEANING] == pytest.approx(0.5)
    assert Dimension.LINEAGE not in report.dimensions
    assert len(report.findings) == 4


def test_empty_database_has_no_score():
    report = evaluate(Database(name="db", platform="test"), CHECKS)
    assert report.score is None
    assert report.dimensions == {}


def test_checks_receive_every_scanned_table():
    seen: list[tuple[str, ...]] = []

    class SpyCheck:
        id = "spy"
        dimension = Dimension.CERTIFICATION
        scope = Scope.TABLE
        severity = Severity.LOW
        weight = 1.0
        version = 1
        description = "Records what it can see."

        def applies_to(self, table):
            return True

        def run(self, table, context: ScanContext):
            seen.append(tuple(t.name for t in context.others(table)))
            return []

    db = Database(
        name="db",
        platform="test",
        schemas=(Schema(name="public", tables=(make_table("a"), make_table("b"))),),
    )
    evaluate(db, checks=[SpyCheck()])
    assert seen == [("b",), ("a",)]


def test_scan_context_lookup():
    ctx = ScanContext.of_tables([make_table("a"), make_table("b")])
    assert ctx.table("db.public.a").name == "a"
    assert ctx.table("db.public.zzz") is None


def test_report_records_check_versions():
    report = evaluate(Database(name="db", platform="test"), CHECKS)
    assert report.checks == {
        "table.description.missing": 1,
        "column.description.missing": 1,
        "table.primary_key.missing": 1,
        "column.name.cryptic": 1,
    }


def test_scan_context_memo_builds_once_per_context():
    builds = []
    ctx = ScanContext.of_tables([make_table("a")])
    for _ in range(3):
        assert ctx.memo("index", lambda: builds.append(1) or "built") == "built"
    assert len(builds) == 1
    assert ScanContext.of_tables([]).memo("index", lambda: "fresh") == "fresh"
