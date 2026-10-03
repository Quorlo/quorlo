import pytest

from factories import make_column, make_table
from quorlo.models import TableKind, TypeKind
from quorlo.readiness import Dimension, ScanContext
from quorlo.readiness.checks import FreshnessUntracked
from quorlo.readiness.names import is_freshness_column_name

CTX = ScanContext(())
check = FreshnessUntracked()


@pytest.mark.parametrize(
    "name",
    [
        "updated_at",
        "last_modified",
        "_etl_loaded_at",
        "ingestion_ts",
        "loadDate",
        "refreshed_on",
        "row_changed_at",
    ],
)
def test_freshness_names(name):
    assert is_freshness_column_name(name)


@pytest.mark.parametrize("name", ["created_at", "ord_dt", "birth_date", "event_ts", "download_url"])
def test_not_freshness_names(name):
    assert not is_freshness_column_name(name)


def ts(name, kind=TypeKind.TIMESTAMP):
    return make_column(name, kind=kind)


def test_table_with_updated_at_passes():
    table = make_table(columns=[make_column("id"), ts("updated_at")])
    assert check.dimension is Dimension.TRUST
    assert not list(check.run(table, CTX))


def test_date_typed_load_column_counts():
    assert not list(check.run(make_table(columns=[ts("load_date", TypeKind.DATE)]), CTX))


def test_freshness_name_with_wrong_type_does_not_count():
    table = make_table(columns=[make_column("updated_by", kind=TypeKind.STRING)])
    assert len(list(check.run(table, CTX))) == 1


def test_table_without_freshness_column_fails():
    table = make_table(columns=[make_column("id"), ts("created_at")])
    (finding,) = check.run(table, CTX)
    assert finding.column is None
    assert "updated_at" in finding.remedy


@pytest.mark.parametrize(
    ("kind", "applies"),
    [
        (TableKind.TABLE, True),
        (TableKind.MATERIALIZED_VIEW, True),
        (TableKind.VIEW, False),
        (TableKind.FOREIGN, False),
    ],
)
def test_applies_to(kind, applies):
    assert check.applies_to(make_table(kind=kind)) is applies
