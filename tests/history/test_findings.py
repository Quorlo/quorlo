from datetime import UTC, datetime

import pytest

from factories import make_column, make_table
from quorlo.history import FindingGrouper, FindingQuery, ScanRun, SqliteRunStore
from quorlo.models import Database, Schema, TableKind, TypeKind
from quorlo.readiness import CHECKS_BY_ID, Dimension, Finding, Scope, Severity, evaluate

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def demo_like_database():
    customers = make_table(
        "cust_mstr",
        schema="retail",
        columns=[
            make_column("cust_id", "Key."),
            make_column("nm"),
            make_column("eml"),
            make_column("phn"),
        ],
        primary_key=("cust_id",),
    )
    product = make_table(
        "dim_product",
        schema="retail",
        description="One row per product.",
        columns=[
            make_column("product_id", "Key."),
            make_column("product_name", "Name."),
            make_column("updated_at", "Last change.", kind=TypeKind.TIMESTAMP),
        ],
        primary_key=("product_id",),
    )
    staging = make_table(
        "stg_imp", schema="staging", columns=[make_column("c1"), make_column("c2")]
    )
    view = make_table("v_orders", schema="retail", kind=TableKind.VIEW, columns=[make_column("id")])
    return Database(
        name="db",
        platform="postgres",
        schemas=(
            Schema(name="retail", tables=(customers, product, view)),
            Schema(name="staging", tables=(staging,)),
        ),
    )


@pytest.fixture
def evaluation():
    return evaluate(demo_like_database())


def grouped(evaluation, findings=None):
    return FindingGrouper(evaluation.report, CHECKS_BY_ID).group(
        evaluation.findings if findings is None else findings
    )


def test_tables_are_ordered_worst_first(evaluation):
    tables = grouped(evaluation)
    scores = [t.score for t in tables]
    assert scores == sorted(scores)
    assert "db.retail.dim_product" not in {t.table for t in tables}  # nothing to fix there


def test_one_line_per_check_listing_its_columns(evaluation):
    customers = next(t for t in grouped(evaluation) if t.table == "db.retail.cust_mstr")
    by_check = {g.check_id: g for g in customers.groups}
    described = by_check["column.description.missing"]
    assert described.columns == ("nm", "eml", "phn")
    assert described.count == 3
    assert described.summary == "no column description"
    assert by_check["column.pii.unclassified"].columns == ("nm", "eml", "phn")


def test_table_level_groups_keep_their_message(evaluation):
    customers = next(t for t in grouped(evaluation) if t.table == "db.retail.cust_mstr")
    group = next(g for g in customers.groups if g.check_id == "table.description.missing")
    assert group.columns == ()
    assert group.messages == ("Table has no description.",)


def test_fix_hint_names_the_table_and_a_single_column(evaluation):
    tables = {t.table: t for t in grouped(evaluation)}
    hints = {g.check_id: g.fix_hint for g in tables["db.retail.cust_mstr"].groups}
    assert hints["table.description.missing"].startswith("COMMENT ON TABLE retail.cust_mstr IS")
    # Several columns: the hint keeps a placeholder rather than picking one.
    assert "retail.cust_mstr.<column>" in hints["column.description.missing"]


def test_groups_sit_under_the_five_questions_by_severity(evaluation):
    customers = next(t for t in grouped(evaluation) if t.table == "db.retail.cust_mstr")
    dims = customers.by_dimension()
    assert list(dims) == [d for d in Dimension if d in dims]  # usual question order
    meaning = [g.severity for g in dims[Dimension.MEANING]]
    order = [Severity.HIGH, Severity.MEDIUM, Severity.LOW]
    assert meaning == sorted(meaning, key=order.index)


def test_a_check_that_no_longer_exists_falls_back_to_its_own_words(evaluation):
    retired = Finding(
        check_id="table.retired.check",
        dimension=Dimension.TRUST,
        severity=Severity.LOW,
        scope=Scope.TABLE,
        table="db.retail.cust_mstr",
        message="Old message.",
        remedy="Old remedy.",
    )
    (table,) = grouped(evaluation, [retired])
    (group,) = table.groups
    assert (group.summary, group.fix_hint) == ("Old message.", "Old remedy.")


@pytest.mark.parametrize(
    ("wanted", "matches"),
    [
        ("cust_mstr", True),
        ("retail.cust_mstr", True),
        ("db.retail.cust_mstr", True),
        ("mstr", False),
    ],
)
def test_table_matching(wanted, matches):
    assert FindingQuery.table_matches("db.retail.cust_mstr", wanted) is matches


# --- filtering in the store ----------------------------------------------------------


@pytest.fixture
def saved(tmp_path, evaluation):
    db = demo_like_database()
    run = ScanRun.record(db, evaluation.report, evaluation.findings, started_at=T0)
    with SqliteRunStore(tmp_path / "runs.db") as store:
        store.save(run)
        yield store, run


def tables_of(findings):
    return {f.table.split(".", 1)[1] for f in findings}


def test_store_filters_by_table_name_in_any_form(saved):
    store, run = saved
    for wanted in ("cust_mstr", "retail.cust_mstr", "db.retail.cust_mstr"):
        assert tables_of(store.findings(run.id, FindingQuery(tables=(wanted,)))) == {
            "retail.cust_mstr"
        }


def test_store_filters_by_dimension_and_check(saved):
    store, run = saved
    governance = list(store.findings(run.id, FindingQuery(dimensions=(Dimension.GOVERNANCE,))))
    assert {f.check_id for f in governance} == {"column.pii.unclassified"}
    pk = list(store.findings(run.id, FindingQuery(checks=("table.primary_key.missing",))))
    assert tables_of(pk) == {"staging.stg_imp"}


def test_store_filters_combine(saved):
    store, run = saved
    query = FindingQuery(tables=("cust_mstr", "stg_imp"), checks=("column.description.missing",))
    found = list(store.findings(run.id, query))
    assert tables_of(found) == {"retail.cust_mstr", "staging.stg_imp"}
    assert {f.check_id for f in found} == {"column.description.missing"}


def test_like_wildcards_in_a_filter_are_literal(saved):
    store, run = saved
    assert list(store.findings(run.id, FindingQuery(tables=("%",)))) == []
    assert list(store.findings(run.id, FindingQuery(tables=("stg_im_",)))) == []


def test_store_returns_findings_grouped_by_table(saved):
    store, run = saved
    names = [f.table for f in store.findings(run.id)]
    assert names == sorted(names)
