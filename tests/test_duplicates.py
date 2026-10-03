import time

import pytest

from factories import (
    estate_findings_for,
    evaluate_tables,
    make_column,
    make_table,
    run_estate_check,
)
from quorlo.models import TypeKind
from quorlo.readiness import Dimension
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


def test_numbers_after_a_marker_are_dropped():
    assert concept_key("orders_bak_2023") == concept_key("orders") == {"orders"}
    assert concept_key("revenue_v2") == {"revenue"}


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


def test_message_names_at_most_five_matches():
    tables = [revenue("orders", TypeKind.INTEGER)] + [
        revenue(f"orders_v{i}", TypeKind.INTEGER) for i in range(2, 10)
    ]
    (finding,) = estate_findings_for(check, tables, tables[0])
    assert finding.message.count("public.orders_v") == 5
    assert "and 3 more" in finding.message


def test_check_version_records_the_rule_change():
    assert check.version == 2


def test_numbered_tables_at_scale_are_fast_and_not_duplicates():
    tables = [revenue(f"table_{i}", TypeKind.INTEGER, TypeKind.STRING) for i in range(5000)]
    started = time.perf_counter()
    findings = run_estate_check(check, tables)
    assert findings == []
    assert time.perf_counter() - started < 2.0


def test_findings_grow_linearly_with_many_copies():
    # 300 copies of one table: one finding each, not one per pair (which would be 89,700).
    tables = [revenue(f"orders_v{i}", TypeKind.INTEGER) for i in range(300)]
    assert len(run_estate_check(check, tables)) == 300


def test_flags_both_tables_of_a_pair():
    a = revenue("revenue_daily", TypeKind.DATE, TypeKind.DECIMAL)
    b = revenue("daily_revenue_v2", TypeKind.DATE, TypeKind.DECIMAL, TypeKind.DECIMAL)
    (finding,) = estate_findings_for(check, [a, b], a)
    assert check.dimension is Dimension.CERTIFICATION
    assert "public.daily_revenue_v2" in finding.message
    assert len(estate_findings_for(check, [a, b], b)) == 1


def test_same_name_but_different_shape_is_not_a_duplicate():
    a = revenue("customers", TypeKind.INTEGER, TypeKind.STRING)
    b = revenue("customers_old", TypeKind.JSON)
    assert not estate_findings_for(check, [a, b], a)


def test_matches_across_schemas():
    a = revenue("orders", TypeKind.INTEGER, schema="raw")
    b = revenue("orders", TypeKind.INTEGER, schema="analytics")
    (finding,) = estate_findings_for(check, [a, b], a)
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
    assert declares_status(a)
    assert run_estate_check(check, [a, b]) == []


def test_certified_tag_resolves_pair():
    a = revenue("orders", TypeKind.INTEGER).model_copy(update={"tags": ("certified",)})
    b = revenue("orders_v2", TypeKind.INTEGER)
    assert not estate_findings_for(check, [a, b], b)


def test_scored_against_the_whole_scan():
    a = revenue("orders", TypeKind.INTEGER)
    b = revenue("orders_v2", TypeKind.INTEGER, schema="raw")
    (alone,) = evaluate_tables([a], [check]).report.tables
    assert alone.dimensions[Dimension.CERTIFICATION] == 1.0
    together = evaluate_tables([a, b], [check])
    assert {t.dimensions[Dimension.CERTIFICATION] for t in together.report.tables} == {0.0}
    assert len(together.findings) == 2
