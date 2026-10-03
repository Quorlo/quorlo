from __future__ import annotations

import json
from collections.abc import Sequence
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from factories import make_column, make_table
from quorlo import registry
from quorlo.cli import app
from quorlo.connector import ConnectionConfig, ConnectorCapabilities, ConnectorError
from quorlo.models import Database, Schema
from quorlo.readiness import evaluate
from quorlo.registry import ConnectorInfo
from quorlo.render import _name_prefix

runner = CliRunner()


class StubConnector:
    name: ClassVar[str] = "stub"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()
    last_config: ClassVar[ConnectionConfig | None] = None
    last_schemas: ClassVar[Sequence[str] | None] = None

    def __init__(self, config: ConnectionConfig) -> None:
        StubConnector.last_config = config

    def test_connection(self) -> None:
        pass

    def list_schemas(self) -> list[str]:
        return ["public"]

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        StubConnector.last_schemas = schemas
        good = make_table(
            "customers",
            description="One row per customer.",
            columns=[make_column("customer_id", "Key.")],
            primary_key=("customer_id",),
        )
        bad = make_table("stg_imp", columns=[make_column("c1"), make_column("f2")])
        return Database(
            name="db", platform="stub", schemas=(Schema(name="public", tables=(good, bad)),)
        )

    def close(self) -> None:
        pass

    def __enter__(self) -> StubConnector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class FailingConnector(StubConnector):
    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        raise ConnectorError("could not connect to server")


@pytest.fixture
def stub_registry(monkeypatch):
    connectors = {"stub": StubConnector, "failing": FailingConnector}

    def load(name: str):
        if name not in connectors:
            raise registry.ConnectorNotFoundError(name, list(connectors))
        return connectors[name]

    monkeypatch.setattr(registry, "load_connector", load)
    monkeypatch.setattr(
        registry,
        "available_connectors",
        lambda: [
            ConnectorInfo("stub", "quorlo-stub", "1.2.3", StubConnector.capabilities),
            ConnectorInfo("broken", "quorlo-broken", "0.1", None, error="missing: scan"),
        ],
    )
    monkeypatch.delenv("QUORLO_DSN", raising=False)


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.startswith("quorlo ")


def test_connectors_lists_capabilities_and_errors(stub_registry):
    result = runner.invoke(app, ["connectors"])
    assert result.exit_code == 0
    assert "stub" in result.output
    assert "1.2.3" in result.output
    assert "missing: scan" in result.output


def test_scan_table_output(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "stub", "--dsn", "stub://", "--details"])
    assert result.exit_code == 0, result.output
    title, rows = result.output.split("\n", 1)
    summary = rows.split("Overall", 1)[0]
    # One schema scanned: it moves to the title and rows show bare table names.
    assert "AI readiness: db.public (stub)" in title
    assert "customers" in summary
    assert "stg_imp" in summary
    assert "public." not in summary
    assert "…" not in result.output
    assert "Overall" in result.output
    assert "column.name.cryptic" in result.output


def test_scan_json_output(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "stub", "--dsn", "stub://", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    scores = {t["table"]: t["score"] for t in data["tables"]}
    assert scores["db.public.customers"] > scores["db.public.stg_imp"]
    assert data["score"] == pytest.approx(sum(scores.values()) / 2)
    assert data["findings_count"] == len([f for t in data["tables"] for f in t["findings"]])


def test_scan_reads_dsn_from_env_and_passes_schemas(stub_registry, monkeypatch):
    monkeypatch.setenv("QUORLO_DSN", "stub://user:secret@host/db")
    result = runner.invoke(app, ["scan", "-c", "stub", "-s", "a", "-s", "b"])
    assert result.exit_code == 0, result.output
    assert StubConnector.last_config.dsn.get_secret_value() == "stub://user:secret@host/db"
    assert list(StubConnector.last_schemas) == ["a", "b"]
    assert "secret" not in result.output


def test_scan_requires_dsn(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "stub"])
    assert result.exit_code != 0


def test_scan_unknown_connector(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "nope", "--dsn", "x"])
    assert result.exit_code == 2
    assert "Installed connectors: failing, stub" in result.output


def test_scan_connector_error(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "failing", "--dsn", "x"])
    assert result.exit_code == 2
    assert "could not connect" in result.output


def test_scan_details_shows_full_targets_without_shared_prefix(stub_registry):
    result = runner.invoke(app, ["scan", "-c", "stub", "--dsn", "stub://", "--details"])
    assert result.exit_code == 0, result.output
    findings = result.output.split("Findings in db.public", 1)[1]
    assert "stg_imp.c1" in findings
    assert "public." not in findings
    assert "…" not in findings


def test_scan_keeps_schema_in_names_when_several_schemas():
    db = Database(
        name="db",
        platform="stub",
        schemas=(
            Schema(name="raw", tables=(make_table("orders", schema="raw"),)),
            Schema(name="mart", tables=(make_table("orders", schema="mart"),)),
        ),
    )
    assert _name_prefix(evaluate(db)) == "db."
