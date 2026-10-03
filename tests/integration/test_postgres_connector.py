"""Postgres connector against the demo database (demo/seed.sql).

    docker compose up -d
    QUORLO_TEST_DSN=postgresql://quorlo:quorlo@localhost:15432/quorlo_demo \
        uv run pytest -m integration
"""

from __future__ import annotations

import os

import psycopg
import pytest
from pydantic import SecretStr

from quorlo.connector import ConnectionConfig, ConnectorError, read_database
from quorlo.connectors.postgres import PostgresConnector
from quorlo.models import TableKind, TypeKind
from quorlo.readiness import Dimension, evaluate

DSN = os.environ.get("QUORLO_TEST_DSN")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="QUORLO_TEST_DSN is not set"),
]

DEMO_TABLES = {
    "cust_mstr",
    "ord_hdr",
    "ord_ln",
    "revenue_daily",
    "daily_revenue_v2",
    "stg_imp_01",
    "v_ord_summary",
    "dim_product",
}


@pytest.fixture
def connector():
    with PostgresConnector(ConnectionConfig(dsn=SecretStr(DSN))) as conn:
        yield conn


@pytest.fixture
def demo(connector):
    database = read_database(connector, ["retail_raw"])
    (schema,) = database.schemas
    return {t.name: t for t in schema.tables}


def test_connection(connector):
    connector.test_connection()


def test_lists_user_schemas_only(connector):
    schemas = connector.list_schemas()
    assert "retail_raw" in schemas
    assert not {"pg_catalog", "information_schema", "pg_toast"} & set(schemas)


def test_finds_demo_tables(demo):
    assert set(demo) == DEMO_TABLES
    assert demo["v_ord_summary"].kind is TableKind.VIEW


def test_reads_comments(connector, demo):
    assert demo["dim_product"].description.startswith("Product dimension.")
    assert demo["dim_product"].column("list_price").description.startswith("Current list price")
    assert demo["cust_mstr"].description is None
    assert demo["cust_mstr"].column("nm").description is None
    database = read_database(connector, ["retail_raw"])
    assert database.schemas[0].description.startswith("Raw retail data")


def test_reads_columns_and_types(demo):
    cust = demo["cust_mstr"]
    assert [c.name for c in cust.columns][:3] == ["cust_id", "nm", "eml"]
    updated = demo["dim_product"].column("updated_at").data_type
    assert (updated.raw, updated.kind) == ("timestamp with time zone", TypeKind.TIMESTAMP)
    nm = cust.column("nm")
    assert (nm.data_type.kind, nm.data_type.length, nm.nullable) == (TypeKind.STRING, 100, False)
    amt = demo["ord_hdr"].column("tot_amt").data_type
    assert (amt.kind, amt.precision, amt.scale) == (TypeKind.DECIMAL, 12, 2)
    assert cust.column("st").default == "1"


def test_reads_keys(demo):
    assert demo["cust_mstr"].primary_key == ("cust_id",)
    assert not demo["ord_ln"].has_primary_key
    (fk,) = demo["ord_hdr"].foreign_keys
    assert fk.columns == ("cust_id",)
    assert fk.references.table == "cust_mstr"
    assert fk.referenced_columns == ("cust_id",)


def test_row_counts_come_from_statistics(demo):
    assert demo["cust_mstr"].row_count_estimate == 5


def test_unknown_schema_is_an_error(connector):
    with pytest.raises(ConnectorError, match="nope"):
        read_database(connector, ["nope"])


def test_connection_rejects_writes(connector):
    conn = connector._runner._connection()
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("INSERT INTO retail_raw.stg_imp_01 (c1) VALUES ('should fail')")
    conn.rollback()


def test_demo_scores_show_a_range(connector):
    report = evaluate(read_database(connector, ["retail_raw"])).report
    tables = {t.table.rsplit(".", 1)[1]: t for t in report.tables}
    assert tables["dim_product"].score == 1.0
    assert tables["stg_imp_01"].dimensions[Dimension.MEANING] == 0.0
    assert 0.0 < report.score < 1.0


def test_demo_problems_land_in_the_right_dimension(connector):
    evaluation = evaluate(read_database(connector, ["retail_raw"]))
    tables = {t.table.rsplit(".", 1)[1]: t for t in evaluation.report.tables}

    # Unmarked personal data in the customer master only.
    pii = {
        f.column
        for f in evaluation.findings_for("quorlo_demo.retail_raw.cust_mstr")
        if f.check_id == "column.pii.unclassified"
    }
    assert pii == {"nm", "eml", "phn", "addr1", "pc"}
    assert [n for n, t in tables.items() if t.dimensions[Dimension.GOVERNANCE] < 1] == ["cust_mstr"]

    # The two revenue tables are the only suspected duplicates.
    duplicates = {n for n, t in tables.items() if t.dimensions[Dimension.CERTIFICATION] < 1}
    assert duplicates == {"revenue_daily", "daily_revenue_v2"}

    # Only dim_product says how fresh it is; the view isn't judged on freshness.
    assert tables["dim_product"].dimensions[Dimension.TRUST] == 1.0
    assert Dimension.TRUST not in tables["v_ord_summary"].dimensions


def test_location_comes_from_the_connection_without_credentials(connector):
    database = read_database(connector, ["retail_raw"])
    assert database.location.startswith("postgres://")
    assert database.location.endswith("/quorlo_demo")
    assert "@" not in database.location
    assert "quorlo:quorlo" not in database.location
