import pytest
from pydantic import ValidationError

from factories import make_column, make_table
from quorlo.models import Column, Database, DataType, Schema, Table, TableRef


def test_table_ref_qualified_name():
    ref = TableRef(database="shop", schema="sales", table="orders")
    assert ref.qualified_name == "shop.sales.orders"
    assert ref.schema_name == "sales"


def test_table_helpers():
    table = make_table(columns=[make_column("id"), make_column("total")], primary_key=("id",))
    assert table.qualified_name == "db.public.orders"
    assert table.has_primary_key
    assert table.column("total").ordinal == 2
    assert table.column("nope") is None


def test_table_without_primary_key():
    assert not make_table(columns=[make_column("x")]).has_primary_key


def test_models_are_frozen():
    table = make_table()
    with pytest.raises(ValidationError):
        table.description = "changed"


def test_unknown_fields_are_rejected():
    # Guards the "no sample values" rule: nothing can be smuggled in as an extra field.
    with pytest.raises(ValidationError):
        Column(name="email", data_type=DataType(raw="text"), ordinal=1, samples=["a@b.c"])


def test_no_field_can_hold_sample_values():
    forbidden = {"sample", "samples", "sample_values", "values", "rows", "examples"}
    for model in (Database, Schema, Table, Column, DataType):
        assert not forbidden & set(model.model_fields), model.__name__


def test_ref_must_match_table_name():
    with pytest.raises(ValidationError, match="does not match"):
        Table(name="a", ref=TableRef(database="d", schema="s", table="b"))


def test_primary_key_must_reference_existing_columns():
    with pytest.raises(ValidationError, match="primary key"):
        make_table(columns=[make_column("id")], primary_key=("missing",))


def test_database_iter_tables():
    db = Database(
        name="db",
        platform="test",
        schemas=(
            Schema(name="a", tables=(make_table("t1", schema="a"),)),
            Schema(name="b", tables=(make_table("t2", schema="b"), make_table("t3", schema="b"))),
        ),
    )
    assert [t.name for t in db.iter_tables()] == ["t1", "t2", "t3"]


def test_tags_default_empty_and_are_labels():
    table = make_table(columns=[make_column("email")])
    assert table.tags == ()
    assert table.columns[0].tags == ()
    tagged = table.columns[0].model_copy(update={"tags": ("pii",)})
    assert tagged.tags == ("pii",)
