"""The `quorlo` command line."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.table import Table as RichTable

import quorlo
from quorlo import registry
from quorlo.connector import ConnectionConfig, ConnectorError
from quorlo.readiness import evaluate
from quorlo.render import render_report, report_json

app = typer.Typer(
    help="Make your data AI-ready: scan platforms and score how ready each table is.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"


@app.command()
def version() -> None:
    """Show the Quorlo version."""
    console.print(f"quorlo {quorlo.__version__}")


@app.command()
def connectors() -> None:
    """List installed connectors and what they are allowed to do."""
    infos = registry.available_connectors()
    if not infos:
        console.print("No connectors installed.")
        return
    table = RichTable()
    for col in ("Name", "Package", "Version", "Reads data", "Write-back", "Sample values"):
        table.add_column(col)
    for info in infos:
        if info.capabilities is None:
            table.add_row(
                info.name, info.package or "", info.version or "", f"[red]{info.error}[/red]"
            )
            continue
        caps = info.capabilities
        table.add_row(
            info.name,
            info.package or "",
            info.version or "",
            *(
                "yes" if v else "no"
                for v in (caps.reads_data, caps.metadata_write_back, caps.sample_values)
            ),
        )
    console.print(table)


@app.command()
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
    output: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.TABLE,
) -> None:
    """Scan a platform read-only and score how AI-ready each table is."""
    try:
        connector_cls = registry.load_connector(connector)
        with connector_cls(ConnectionConfig(dsn=SecretStr(dsn))) as conn:
            database = conn.scan(schema or None)
    except ConnectorError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from None

    report = evaluate(database)
    if output is OutputFormat.JSON:
        typer.echo(report_json(report))
    else:
        render_report(report, console, details=details)
