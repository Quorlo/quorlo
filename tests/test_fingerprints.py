from factories import make_column, make_table
from quorlo.models import TypeKind
from quorlo.readiness import DEFAULT_CHECKS, Dimension, Finding, ScanContext, Scope, Severity
from quorlo.readiness.checks import DuplicateSuspected


def finding(**overrides):
    values = dict(
        check_id="column.description.missing",
        dimension=Dimension.MEANING,
        severity=Severity.MEDIUM,
        scope=Scope.COLUMN,
        table="db.s.t",
        column="c",
        message="Column has no description.",
        remedy="Describe it.",
    )
    return Finding(**(values | overrides))


def test_fingerprint_is_stable_and_ignores_wording():
    assert finding().fingerprint == finding().fingerprint
    assert finding(message="Reworded.", remedy="Other.").fingerprint == finding().fingerprint
    assert finding(severity=Severity.HIGH).fingerprint == finding().fingerprint
    assert len(finding().fingerprint) == 16


def test_fingerprint_changes_with_what_the_finding_is_about():
    base = finding().fingerprint
    assert finding(column="d").fingerprint != base
    assert finding(table="db.s.u").fingerprint != base
    assert finding(check_id="column.name.cryptic").fingerprint != base
    assert finding(key="x").fingerprint != base


def test_no_column_is_not_confused_with_empty_key():
    assert finding(column=None, key="c").fingerprint != finding(column="c", key=None).fingerprint


def test_duplicate_findings_are_told_apart_by_the_other_table():
    def t(name):
        return make_table(name, columns=[make_column("d", kind=TypeKind.DATE)])

    a, b, c = t("orders"), t("orders_v2"), t("orders_old")
    findings = list(DuplicateSuspected().run(a, ScanContext.of_tables([a, b, c])))
    assert {f.key for f in findings} == {"db.public.orders_v2", "db.public.orders_old"}
    assert len({f.fingerprint for f in findings}) == 2


def test_every_default_check_has_a_version():
    assert all(isinstance(c.version, int) and c.version >= 1 for c in DEFAULT_CHECKS)
