"""`quorlo scan`."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Annotated

import typer
from pydantic import SecretStr

from quorlo.cli.common import (
    FormatOption,
    OutputFormat,
    StoreOption,
    console,
    fail,
    open_store,
)
from quorlo.connectors import ConnectionConfig, ConnectorError, registry
from quorlo.output import (
    ReportView,
    change_line,
    report_json,
    stats_lines,
)
from quorlo.readiness import ReadinessEngine
from quorlo.scanner import Scanner, ScanOutcome


def scan(
    dsn: Annotated[
        str,
        typer.Option(
            envvar="QUORLO_DSN",
            help="Connection string. Prefer the env var: it keeps passwords out of shell history.",
            show_default=False,
        ),
    ],
    connector: Annotated[
        str, typer.Option("--connector", "-c", help="Connector name.")
    ] = "postgres",
    schema: Annotated[
        list[str] | None,
        typer.Option("--schema", "-s", help="Schema to scan. Repeat for several. Default: all."),
    ] = None,
    details: Annotated[bool, typer.Option(help="List every finding.")] = False,
    output: FormatOption = OutputFormat.TABLE,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="Save this run to the run history.")
    ] = True,
    store_path: StoreOption = None,
) -> None:
    """Scan a platform read-only and score how AI-ready each table is."""
    # Open the run history first, so a bad --store fails before a long scan, not after.
    with open_store(store_path) if save else nullcontext() as store:
        scanner = Scanner(ReadinessEngine(), store)
        try:
            connector_cls = registry.load_connector(connector)
            with connector_cls(ConnectionConfig(dsn=SecretStr(dsn))) as conn:
                outcome = scanner.scan(conn, schema or None)
        except ConnectorError as exc:
            fail(str(exc))
        _show_scan(outcome, scanner, output, details)


def _show_scan(outcome: ScanOutcome, scanner: Scanner, output: OutputFormat, details: bool) -> None:
    run_id = outcome.header.id if outcome.saved else None
    if output is OutputFormat.JSON:
        findings = scanner.findings(outcome)
        typer.echo(report_json(outcome.report, findings, run_id=run_id, stats=outcome.stats))
        return
    findings = scanner.findings(outcome) if details else ()
    ReportView(outcome.report, findings).render(console, details=details)
    if outcome.since_last_run is not None:
        console.print(change_line(outcome.since_last_run, datetime.now(UTC)))
    for line in stats_lines(outcome.stats):
        console.print(line)
    if run_id:
        console.print(f"[dim]Saved as run {run_id}.[/dim]")
