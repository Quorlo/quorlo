"""Unit tests for the Postgres connector that need no database."""

import pytest
from pydantic import SecretStr

from quorlo.connector import ConnectionConfig, Connector, ConnectorError
from quorlo.connectors.postgres import PostgresConnector, build_database, parse_type
from quorlo.models import TableKind, TypeKind
from quorlo.registry import load_connector


@pytest.mark.parametrize(
    ("raw", "kind", "length", "precision", "scale"),
    [
        ("text", TypeKind.STRING, None, None, None),
        ("character varying(50)", TypeKind.STRING, 50, None, None),
        ("character(2)", TypeKind.STRING, 2, None, None),
        ("integer", TypeKind.INTEGER, None, None, None),
        ("bigint", TypeKind.INTEGER, None, None, None),
        ("numeric(12,2)", TypeKind.DECIMAL, None, 12, 2),
        ("numeric(5)", TypeKind.DECIMAL, None, 5, 0),
        ("numeric", TypeKind.DECIMAL, None, None, None),
        ("double precision", TypeKind.FLOAT, None, None, None),
        ("boolean", TypeKind.BOOLEAN, None, None, None),
        ("date", TypeKind.DATE, None, None, None),
        ("timestamp with time zone", TypeKind.TIMESTAMP, None, None, None),
        ("timestamp(3) without time zone", TypeKind.TIMESTAMP, None, 3, None),
        ("time(0) with time zone", TypeKind.TIME, None, 0, None),
        ("jsonb", TypeKind.JSON, None, None, None),
        ("uuid", TypeKind.UUID, None, None, None),
        ("bytea", TypeKind.BINARY, None, None, None),
        ("integer[]", TypeKind.ARRAY, None, None, None),
        ("character varying(20)[]", TypeKind.ARRAY, None, None, None),
        ("tsvector", TypeKind.OTHER, None, None, None),
    ],
)
def test_parse_type(raw, kind, length, precision, scale):
    dt = parse_type(raw)
    assert dt.raw == raw
    assert (dt.kind, dt.length, dt.precision, dt.scale) == (kind, length, precision, scale)


def test_parse_enum_type_is_string():
    assert parse_type("order_status", typtype="e").kind is TypeKind.STRING


def _col(schema, table, ordinal, name, type_="integer", description=None, nullable=True):
    return {
        "schema": schema,
        "table": table,
        "ordinal": ordinal,
        "name": name,
        "type": type_,
        "typtype": "b",
        "nullable": nullable,
        "description": description,
        "default": None,
    }


def test_build_database():
    db = build_database(
        "shop",
        schemas=[{"name": "sales", "description": "Sales data."}, {"name": "empty", "description": None}],
        tables=[
            {"schema": "sales", "name": "orders", "relkind": "r", "description": "Orders.", "reltuples": 120},
            {"schema": "sales", "name": "customers", "relkind": "p", "description": None, "reltuples": -1},
            {"schema": "sales", "name": "v_orders", "relkind": "v", "description": None, "reltuples": 0},
        ],
        columns=[
            _col("sales", "orders", 2, "customer_id"),
            _col("sales", "orders", 1, "order_id", nullable=False, description="Key."),
            _col("sales", "customers", 1, "customer_id"),
            _col("sales", "customers", 2, "email", "text"),
            _col("sales", "v_orders", 1, "order_id"),
        ],
        constraints=[
            {"name": "orders_pkey", "type": "p", "schema": "sales", "table": "orders",
             "columns": ["order_id"], "ref_schema": None, "ref_table": None, "ref_columns": []},
            {"name": "customers_email_key", "type": "u", "schema": "sales", "table": "customers",
             "columns": ["email"], "ref_schema": None, "ref_table": None, "ref_columns": []},
            {"name": "orders_customer_fk", "type": "f", "schema": "sales", "table": "orders",
             "columns": ["customer_id"], "ref_schema": "sales", "ref_table": "customers",
             "ref_columns": ["customer_id"]},
        ],
    )  # fmt: skip

    assert db.name == "shop"
    assert db.platform == "postgres"
    assert [s.name for s in db.schemas] == ["sales", "empty"]
    assert db.schemas[1].tables == ()

    orders, customers, view = db.schemas[0].tables
    assert orders.qualified_name == "shop.sales.orders"
    assert [c.name for c in orders.columns] == ["order_id", "customer_id"]
    assert orders.primary_key == ("order_id",)
    assert orders.row_count_estimate == 120
    assert orders.column("order_id").nullable is False
    assert orders.foreign_keys[0].references.qualified_name == "shop.sales.customers"
    assert orders.foreign_keys[0].referenced_columns == ("customer_id",)

    assert customers.kind is TableKind.TABLE  # partitioned parent
    assert customers.row_count_estimate is None  # never analyzed
    assert customers.unique_constraints == (("email",),)
    assert not customers.has_primary_key

    assert view.kind is TableKind.VIEW


def test_postgres_connector_is_registered_and_metadata_only():
    cls = load_connector("postgres")
    assert cls is PostgresConnector
    caps = cls.capabilities
    assert not (caps.reads_data or caps.metadata_write_back or caps.sample_values)


def test_postgres_connector_satisfies_protocol():
    # Constructing does not connect; the connection is opened lazily.
    conn = PostgresConnector(ConnectionConfig(dsn=SecretStr("postgresql://localhost/none")))
    assert isinstance(conn, Connector)


def test_postgres_connector_refuses_write_access():
    config = ConnectionConfig(dsn=SecretStr("postgresql://localhost/none"), read_only=False)
    with pytest.raises(ConnectorError, match="read-only"):
        PostgresConnector(config)


def test_connection_error_hides_password():
    config = ConnectionConfig(
        dsn=SecretStr("postgresql://user:hunter2@127.0.0.1:1/none"), options={"connect_timeout": 1}
    )
    with pytest.raises(ConnectorError) as exc_info, PostgresConnector(config) as conn:
        conn.test_connection()
    assert "hunter2" not in str(exc_info.value)
