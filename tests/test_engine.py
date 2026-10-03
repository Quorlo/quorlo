import pytest

from factories import make_column, make_table
from quorlo.models import Database, Schema, TableKind
from quorlo.readiness import (
    Dimension,
    Finding,
    FindingList,
    ReadinessEngine,
    Scope,
    Severity,
    evaluate,
    evaluate_table,
)
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


def readiness(table):
    (result,) = evaluate_table(table, CHECKS).report.tables
    return result


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
    result = readiness(documented_table())
    assert result.score == 1.0
    assert result.dimensions == {Dimension.MEANING: 1.0}
    assert result.finding_count == 0


def test_empty_table_scores_zero():
    table = make_table("stg", columns=[make_column("c1"), make_column("c2")])
    result = readiness(table)
    assert result.score == 0.0
    by_check = {r.check_id: r for r in result.checks}
    assert by_check["column.description.missing"].evaluated == 2
    assert by_check["column.description.missing"].failed == 2
    assert by_check["table.description.missing"].evaluated == 1


def test_score_is_weighted_per_check_not_per_unit():
    # 20 documented, readable columns and a key, but no table description (weight 2 of 5).
    columns = [make_column(f"metric_number_{w}", "Documented.") for w in "abcdefghijklmnopqrst"]
    table = make_table(columns=columns, primary_key=("metric_number_a",))
    result = readiness(table)
    assert result.score == pytest.approx(1 - 2 / 5)


def test_partial_column_failures():
    table = documented_table().model_copy(
        update={"columns": (*documented_table().columns, make_column("notes", ordinal=3))}
    )
    result = readiness(table)
    by_check = {r.check_id: r for r in result.checks}
    assert by_check["column.description.missing"].pass_rate == pytest.approx(2 / 3)
    # weights: table desc 2, column desc 1, pk 1, cryptic 1
    assert result.score == pytest.approx((2 + 2 / 3 + 1 + 1) / 5)


def test_views_are_not_penalised_for_missing_primary_key():
    view = make_table(
        "v", kind=TableKind.VIEW, description="A view.", columns=[make_column("id", "Key.")]
    )
    result = readiness(view)
    assert "table.primary_key.missing" not in {r.check_id for r in result.checks}
    assert result.score == 1.0


def test_report_averages_tables_and_dimensions():
    bad = make_table("stg", columns=[make_column("c1")])
    db = Database(
        name="db",
        platform="test",
        schemas=(Schema(name="public", tables=(documented_table(), bad)),),
    )
    evaluation = evaluate(db, CHECKS)
    report = evaluation.report
    assert [t.table for t in report.tables] == ["db.public.customers", "db.public.stg"]
    assert report.score == pytest.approx(0.5)
    assert report.dimensions[Dimension.MEANING] == pytest.approx(0.5)
    assert Dimension.LINEAGE not in report.dimensions
    assert report.finding_count == len(evaluation.findings) == 4
    assert len(evaluation.findings_for("db.public.stg")) == 4


def test_empty_database_has_no_score():
    report = evaluate(Database(name="db", platform="test"), CHECKS).report
    assert report.score is None
    assert report.dimensions == {}


class SpyEstateCheck:
    """An EstateCheck that records what it sees and fails the first table it observed."""

    id = "spy"
    dimension = Dimension.CERTIFICATION
    scope = Scope.TABLE
    severity = Severity.LOW
    weight = 1.0
    version = 1
    description = "Records what it can see."

    def __init__(self) -> None:
        self.observed: list[str] = []
        self.reported_after: list[str] = []

    def applies_to(self, table):
        return table.kind is TableKind.TABLE

    def start(self):
        return self

    def observe(self, table):
        self.observed.append(table.name)

    def findings(self):
        self.reported_after = list(self.observed)
        first = self.observed[0]
        yield Finding(
            check_id=self.id,
            dimension=self.dimension,
            severity=self.severity,
            scope=self.scope,
            table=f"db.public.{first}",
            message="Spied.",
            remedy="None.",
        )


def test_estate_checks_observe_every_table_then_report_once():
    spy = SpyEstateCheck()
    db = Database(
        name="db",
        platform="test",
        schemas=(
            Schema(name="public", tables=(make_table("a"), make_table("b", kind=TableKind.VIEW))),
            Schema(name="other", tables=(make_table("c", schema="other"),)),
        ),
    )
    evaluation = evaluate(db, checks=[spy])
    assert spy.observed == ["a", "c"]  # the view is not a table it applies to
    assert spy.reported_after == ["a", "c"]
    scores = {t.table: t.dimensions.get(Dimension.CERTIFICATION) for t in evaluation.report.tables}
    assert scores == {"db.public.a": 0.0, "db.public.b": None, "db.other.c": 1.0}


def test_findings_go_to_the_sink_not_the_report():
    sink = FindingList()
    assessment = ReadinessEngine(CHECKS).start(sink)
    assessment.add(Schema(name="public", tables=(make_table("stg", columns=[make_column("c1")]),)))
    assessment.finish_checks()
    report = assessment.report("db", "test")
    assert len(sink) == report.finding_count == 4
    assert "findings" not in report.model_dump()["tables"][0]


def test_report_requires_finished_checks():
    assessment = ReadinessEngine(CHECKS).start(FindingList())
    with pytest.raises(RuntimeError, match="finish_checks"):
        assessment.report("db", "test")


def test_assessment_consumes_schemas_one_at_a_time():
    consumed: list[str] = []

    def stream():
        for name in ("a", "b", "c"):
            consumed.append(name)
            yield Schema(name=name, tables=(make_table(f"t_{name}", schema=name),))

    assessment = ReadinessEngine(CHECKS).start(FindingList())
    for schema in stream():
        assessment.add(schema)
        assert consumed[-1] == schema.name  # nothing read ahead
    assert assessment.tables == 3


def test_report_records_check_versions():
    report = evaluate(Database(name="db", platform="test"), CHECKS).report
    assert report.checks == {
        "table.description.missing": 1,
        "column.description.missing": 1,
        "table.primary_key.missing": 1,
        "column.name.cryptic": 1,
    }
