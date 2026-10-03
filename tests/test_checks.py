import pytest

from factories import make_column, make_table
from quorlo.models import TableKind
from quorlo.readiness import DEFAULT_CHECKS, Check, Dimension
from quorlo.readiness.checks import (
    ColumnDescriptionMissing,
    ColumnNameCryptic,
    PrimaryKeyMissing,
    TableDescriptionMissing,
    cryptic_reason,
)


def test_default_checks_satisfy_protocol_and_have_unique_ids():
    assert all(isinstance(c, Check) for c in DEFAULT_CHECKS)
    assert len({c.id for c in DEFAULT_CHECKS}) == len(DEFAULT_CHECKS)


def test_every_check_has_a_dimension():
    assert all(isinstance(c.dimension, Dimension) for c in DEFAULT_CHECKS)


@pytest.mark.parametrize("description", [None, "", "   "])
def test_table_description_missing(description):
    findings = list(TableDescriptionMissing().run(make_table(description=description)))
    assert len(findings) == 1
    assert findings[0].target == "db.public.orders"


def test_table_description_present():
    assert not list(TableDescriptionMissing().run(make_table(description="One row per order.")))


def test_column_description_missing_reports_each_column():
    table = make_table(columns=[make_column("a"), make_column("b", "Documented"), make_column("c")])
    findings = list(ColumnDescriptionMissing().run(table))
    assert [f.column for f in findings] == ["a", "c"]
    assert findings[0].target == "db.public.orders.a"


def test_primary_key_missing():
    check = PrimaryKeyMissing()
    assert len(list(check.run(make_table(columns=[make_column("id")])))) == 1
    keyed = make_table(columns=[make_column("id")], primary_key=("id",))
    assert not list(check.run(keyed))


def test_primary_key_check_skips_views():
    check = PrimaryKeyMissing()
    assert not check.applies_to(make_table(kind=TableKind.VIEW))
    assert not check.applies_to(make_table(kind=TableKind.MATERIALIZED_VIEW))
    assert check.applies_to(make_table(kind=TableKind.TABLE))


@pytest.mark.parametrize(
    "name",
    ["st", "nm", "pc", "c1", "f2", "col1", "cust_nm", "ord_amt", "cntry_cd", "phn", "addr1"],
)
def test_cryptic_names(name):
    assert cryptic_reason(name) is not None


@pytest.mark.parametrize(
    "name",
    [
        "id",
        "customer_id",
        "email",
        "order_total",
        "created_at",
        "product_url",
        "sku",
        "unitPrice",
        "line_number",
        "country_code",
        "address_line_1",
    ],
)
def test_readable_names(name):
    assert cryptic_reason(name) is None


def test_cryptic_check_reports_reason():
    table = make_table(columns=[make_column("cust_nm"), make_column("email")])
    findings = list(ColumnNameCryptic().run(table))
    assert [f.column for f in findings] == ["cust_nm"]
    assert "'nm'" in findings[0].message
