"""Scan the demo database twice through the CLI, with a fix in between, and compare."""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from psycopg import sql
from typer.testing import CliRunner

from quorlo.cli import app

DSN = os.environ.get("QUORLO_TEST_DSN")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="QUORLO_TEST_DSN is not set"),
]

runner = CliRunner()


def scan() -> dict:
    result = runner.invoke(app, ["scan", "--dsn", DSN, "-s", "retail_raw", "-f", "json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def documented_ord_ln():
    """Give ord_ln a description for the duration of a test, then put the demo back."""

    def set_comment(text: str | None) -> None:
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(
                sql.SQL("COMMENT ON TABLE retail_raw.ord_ln IS {}").format(sql.Literal(text))
            )

    yield lambda: set_comment("Order lines. One row per product on an order.")
    set_comment(None)


def test_diff_shows_the_fixed_finding_as_resolved(documented_ord_ln, isolated_run_store):
    before = scan()
    documented_ord_ln()
    after = scan()

    result = runner.invoke(app, ["diff", "-f", "json"])
    assert result.exit_code == 0, result.output
    diff = json.loads(result.output)

    assert (diff["base"], diff["head"]) == (before["run_id"], after["run_id"])
    resolved = [(f["check_id"], f["table"].rsplit(".", 1)[1]) for f in diff["resolved_findings"]]
    assert resolved == [("table.description.missing", "ord_ln")]
    assert diff["new_findings"] == []
    assert diff["warnings"] == []
    assert diff["score"]["delta"] > 0
    assert isolated_run_store.exists()
