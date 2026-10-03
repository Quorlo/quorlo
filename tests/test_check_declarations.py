import pytest

from quorlo.models import Table
from quorlo.readiness import DEFAULT_CHECKS, Dimension, Scope, Severity
from quorlo.readiness.checks._base import BaseCheck, FixHint


def test_every_default_check_has_a_summary_and_a_usable_fix_hint():
    for check in DEFAULT_CHECKS:
        assert check.summary and check.fix_hint, check.id
        rendered = FixHint(check.fix_hint).render("sales.orders", ["email"])
        assert "{" not in rendered, check.id


def test_a_check_without_a_fix_hint_fails_at_definition():
    with pytest.raises(TypeError, match="must declare: fix_hint"):

        class NoHint(BaseCheck):
            id = "x"
            dimension = Dimension.MEANING
            scope = Scope.TABLE
            severity = Severity.LOW
            description = "x"
            summary = "x"

            def run(self, table: Table):
                return []


def test_a_fix_hint_with_an_unknown_placeholder_fails_at_definition():
    with pytest.raises(ValueError, match="Unknown fix_hint placeholders: schema"):

        class BadHint(BaseCheck):
            id = "x"
            dimension = Dimension.MEANING
            scope = Scope.TABLE
            severity = Severity.LOW
            description = "x"
            summary = "x"
            fix_hint = "COMMENT ON SCHEMA {schema}"

            def run(self, table: Table):
                return []


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        ((), "COMMENT ON COLUMN s.t.<column> IS '...';"),
        (("email",), "COMMENT ON COLUMN s.t.email IS '...';"),
        (("email", "phone"), "COMMENT ON COLUMN s.t.<column> IS '...';"),
    ],
)
def test_fix_hint_names_a_single_column_only(columns, expected):
    assert (
        FixHint("COMMENT ON COLUMN {table}.{column} IS '...';").render("s.t", columns) == expected
    )
