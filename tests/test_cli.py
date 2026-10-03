from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from factories import make_column, make_table
from quorlo import registry
from quorlo.cli import app
from quorlo.connector import (
    ConnectionConfig,
    ConnectorCapabilities,
    ConnectorError,
    DatabaseInfo,
    FetchStats,
)
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
    # Flip to simulate someone documenting the staging table between two scans.
    staging_documented: ClassVar[bool] = False

    def __init__(self, config: ConnectionConfig) -> None:
        StubConnector.last_config = config

    def test_connection(self) -> None:
        pass

    def list_schemas(self) -> list[str]:
        return ["public"]

    def describe(self) -> DatabaseInfo:
        return DatabaseInfo(name="db", platform="stub")

    @property
    def stats(self) -> FetchStats:
        return FetchStats()

    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
        StubConnector.last_schemas = schemas
        good = make_table(
            "customers",
            description="One row per customer.",
            columns=[make_column("customer_id", "Key.")],
            primary_key=("customer_id",),
        )
        bad = make_table(
            "stg_imp",
            description="Raw import." if StubConnector.staging_documented else None,
            columns=[make_column("c1"), make_column("f2")],
        )
        yield Schema(name="public", tables=(good, bad))

    def close(self) -> None:
        pass

    def __enter__(self) -> StubConnector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class FailingConnector(StubConnector):
    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
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
    monkeypatch.setattr(StubConnector, "staging_documented", False)


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
    assert data["findings_count"] == len(data["findings"]) > 0
    assert all("fingerprint" in f for f in data["findings"])


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
    assert _name_prefix(evaluate(db).report) == "db."


# --- run history ---------------------------------------------------------------------


def scan_stub(*extra):
    result = runner.invoke(app, ["scan", "-c", "stub", "--dsn", "stub://", *extra])
    assert result.exit_code == 0, result.output
    return result


def test_scan_saves_runs_by_default(stub_registry, isolated_run_store):
    result = scan_stub()
    assert "Saved as run " in result.output
    assert "Since last run" not in result.output  # nothing to compare with yet
    assert isolated_run_store.exists()
    assert "stub:db" in runner.invoke(app, ["runs"]).output


def test_no_save_writes_nothing(stub_registry, isolated_run_store):
    result = scan_stub("--no-save")
    assert "Saved as run" not in result.output
    assert not isolated_run_store.exists()


def test_store_option_overrides_default(stub_registry, tmp_path, isolated_run_store):
    custom = tmp_path / "elsewhere.db"
    scan_stub("--store", str(custom))
    assert custom.exists()
    assert not isolated_run_store.exists()


def test_second_scan_reports_change_since_last_run(stub_registry, monkeypatch):
    scan_stub()
    monkeypatch.setattr(StubConnector, "staging_documented", True)
    result = scan_stub()
    assert "Since last run (just now):" in result.output
    assert "1 resolved, 0 new" in result.output


def test_scan_json_includes_run_id_only_when_saved(stub_registry):
    saved = json.loads(scan_stub("--format", "json").output)
    assert saved["run_id"]
    unsaved = json.loads(scan_stub("--format", "json", "--no-save").output)
    assert "run_id" not in unsaved


def test_runs_lists_newest_first_and_show_reprints(stub_registry, monkeypatch):
    first = json.loads(scan_stub("--format", "json").output)["run_id"]
    monkeypatch.setattr(StubConnector, "staging_documented", True)
    second = json.loads(scan_stub("--format", "json").output)["run_id"]

    listing = runner.invoke(app, ["runs"]).output
    assert listing.index(second) < listing.index(first)
    assert runner.invoke(app, ["runs", "--limit", "1"]).output.count("stub:db") == 1

    shown = runner.invoke(app, ["runs", "show", first[:18]])
    assert shown.exit_code == 0, shown.output
    assert f"Run {first}" in shown.output
    assert "stg_imp" in shown.output
    as_json = json.loads(runner.invoke(app, ["runs", "show", first, "-f", "json"]).output)
    assert as_json["run_id"] == first


def test_runs_when_empty(stub_registry):
    assert "No saved runs yet" in runner.invoke(app, ["runs"]).output


def test_diff_defaults_to_the_latest_two_runs(stub_registry, monkeypatch):
    scan_stub()
    monkeypatch.setattr(StubConnector, "staging_documented", True)
    scan_stub()
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0, result.output
    assert "Findings: 1 resolved, 0 new" in result.output
    assert "Resolved findings" in result.output
    assert "stg_imp: Table has no description." in result.output


def test_diff_with_explicit_runs_and_json(stub_registry, monkeypatch):
    first = json.loads(scan_stub("--format", "json").output)["run_id"]
    monkeypatch.setattr(StubConnector, "staging_documented", True)
    second = json.loads(scan_stub("--format", "json").output)["run_id"]

    data = json.loads(runner.invoke(app, ["diff", first, second, "-f", "json"]).output)
    assert (data["base"], data["head"]) == (first, second)
    assert [f["check_id"] for f in data["resolved_findings"]] == ["table.description.missing"]
    assert data["score"]["delta"] > 0

    # BASE alone compares it with the latest run of the same target.
    data = json.loads(runner.invoke(app, ["diff", first, "-f", "json"]).output)
    assert data["head"] == second


def test_diff_needs_two_runs(stub_registry):
    assert "No saved runs yet" in runner.invoke(app, ["diff"]).output
    scan_stub()
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 2
    assert "Only one run" in result.output


def test_diff_unknown_run(stub_registry):
    scan_stub()
    result = runner.invoke(app, ["diff", "nope"])
    assert result.exit_code == 2
    assert "No saved run matches 'nope'" in result.output


def test_unwritable_store_is_a_clean_error(stub_registry, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    result = runner.invoke(
        app, ["scan", "-c", "stub", "--dsn", "x", "--store", str(blocker / "q.db")]
    )
    assert result.exit_code == 2, result.exception
    assert "Cannot open the run store" in result.output
