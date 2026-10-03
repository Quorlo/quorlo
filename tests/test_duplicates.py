import pytest

from factories import make_column, make_table
from quorlo.models import TypeKind
from quorlo.readiness import Dimension, ScanContext, evaluate_table
from quorlo.readiness.checks import DuplicateSuspected, column_type_overlap, declares_status
from quorlo.readiness.names import concept_key

check = DuplicateSuspected()


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("revenue_daily", "daily_revenue_v2"),
        ("customers", "customers_old"),
        ("orders", "orders_bak_2023"),
        ("dailyRevenue", "revenue_daily"),
        ("product_copy", "product"),
    ],
)
def test_same_concept(a, b):
    assert concept_key(a) == concept_key(b)


@pytest.mark.parametrize(
    ("a", "b"), [("orders", "order_lines"), ("revenue_daily", "revenue_monthly")]
)
def test_different_concept(a, b):
    assert concept_key(a) != concept_key(b)


def test_markers_only_name_has_no_concept():
    assert concept_key("tmp_v2") == frozenset()


def revenue(name, *kinds, description=None, schema="public"):
    cols = [make_column(f"c{i}", kind=k) for i, k in enumerate(kinds)]
    return make_table(name, columns=cols, description=description, schema=schema)


def test_type_overlap():
    a = revenue("a", TypeKind.DATE, TypeKind.DECIMAL)
    b = revenue("b", TypeKind.DATE, TypeKind.DECIMAL, TypeKind.DECIMAL)
    assert column_type_overlap(a, b) == pytest.approx(2 / 3)
    assert column_type_overlap(a, revenue("c", TypeKind.STRING)) == 0.0
    assert column_type_overlap(revenue("d"), revenue("e")) == 0.0


def test_flags_both_tables_of_a_pair():
    a = revenue("revenue_daily", TypeKind.DATE, TypeKind.DECIMAL)
    b = revenue("daily_revenue_v2", TypeKind.DATE, TypeKind.DECIMAL, TypeKind.DECIMAL)
    ctx = ScanContext.of_tables([a, b])
    (finding,) = check.run(a, ctx)
    assert check.dimension is Dimension.CERTIFICATION
    assert "public.daily_revenue_v2" in finding.message
    assert len(list(check.run(b, ctx))) == 1


def test_same_name_but_different_shape_is_not_a_duplicate():
    a = revenue("customers", TypeKind.INTEGER, TypeKind.STRING)
    b = revenue("customers_old", TypeKind.JSON)
    assert not list(check.run(a, ScanContext.of_tables([a, b])))


def test_matches_across_schemas():
    a = revenue("orders", TypeKind.INTEGER, schema="raw")
    b = revenue("orders", TypeKind.INTEGER, schema="analytics")
    (finding,) = check.run(a, ScanContext.of_tables([a, b]))
    assert "analytics.orders" in finding.message


@pytest.mark.parametrize(
    "description",
    [
        "Certified revenue by day.",
        "The source of truth for revenue.",
        "Deprecated: use revenue_daily.",
    ],
)
def test_pair_is_resolved_when_either_table_declares_status(description):
    a = revenue("revenue_daily", TypeKind.DATE, description=description)
    b = revenue("daily_revenue_v2", TypeKind.DATE)
    ctx = ScanContext.of_tables([a, b])
    assert declares_status(a)
    assert not list(check.run(a, ctx))
    assert not list(check.run(b, ctx))


def test_certified_tag_resolves_pair():
    a = revenue("orders", TypeKind.INTEGER).model_copy(update={"tags": ("certified",)})
    b = revenue("orders_v2", TypeKind.INTEGER)
    assert not list(check.run(b, ScanContext.of_tables([a, b])))


def test_scored_against_the_scan_context():
    a = revenue("orders", TypeKind.INTEGER)
    b = revenue("orders_v2", TypeKind.INTEGER)
    alone = evaluate_table(a, [check])
    assert alone.dimensions[Dimension.CERTIFICATION] == 1.0
    together = evaluate_table(a, [check], ScanContext.of_tables([a, b]))
    assert together.dimensions[Dimension.CERTIFICATION] == 0.0
