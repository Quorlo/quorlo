"""The `quorlo` command line."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.markup import escape
from rich.table import Table as RichTable

import quorlo
from quorlo import registry
from quorlo.connector import ConnectionConfig, ConnectorError
from quorlo.history import ScanRun, diff_runs
from quorlo.readiness import evaluate
from quorlo.render import (
    change_line,
    diff_json,
    render_diff,
    render_report,
    render_runs,
    report_json,
)
from quorlo.store import RunNotFoundError, SqliteRunStore, StoreError, default_store_path

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


StoreOption = Annotated[
    Path | None,
    typer.Option(
        "--store",
        envvar="QUORLO_STORE",
        help="Run history file. Default: quorlo.db in your user data directory.",
        show_default=False,
    ),
]
FormatOption = Annotated[OutputFormat, typer.Option("--format", "-f")]


def _fail(message: str) -> NoReturn:
    err_console.print(f"[red]Error:[/red] {escape(message)}")
    raise typer.Exit(code=2)


@contextmanager
def _open_store(path: Path | None) -> Iterator[SqliteRunStore]:
    """The run history, with any store error inside the block reported cleanly."""
    try:
        with SqliteRunStore(path or default_store_path()) as store:
            yield store
    except StoreError as exc:
        _fail(str(exc))


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
    output: FormatOption = OutputFormat.TABLE,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="Save this run to the run history.")
    ] = True,
    store_path: StoreOption = None,
) -> None:
    """Scan a platform read-only and score how AI-ready each table is."""
    # Open the run history first, so a bad --store fails before a long scan, not after.
    with _open_store(store_path) if save else nullcontext() as store:
        started_at = datetime.now(UTC)
        try:
            connector_cls = registry.load_connector(connector)
            with connector_cls(ConnectionConfig(dsn=SecretStr(dsn))) as conn:
                database = conn.scan(schema or None)
        except ConnectorError as exc:
            _fail(str(exc))

        report = evaluate(database)
        run = ScanRun.record(database, report, started_at=started_at, schemas=schema)
        previous = None
        if store is not None:
            previous = store.latest(run.target, run.schemas, before=run.started_at)
            store.save(run)

    if output is OutputFormat.JSON:
        typer.echo(report_json(report, run_id=run.id if save else None))
        return
    render_report(report, console, details=details)
    if previous is not None:
        console.print(change_line(diff_runs(previous, run), previous, datetime.now(UTC)))
    if save:
        console.print(f"[dim]Saved as run {run.id}.[/dim]")


runs_app = typer.Typer(
    help="Saved scan runs. Without a subcommand, lists the most recent ones.",
    invoke_without_command=True,
)
app.add_typer(runs_app, name="runs")


@runs_app.callback()
def runs(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(min=1, help="How many runs to list.")] = 20,
    store_path: StoreOption = None,
) -> None:
    """List saved scan runs, newest first."""
    if ctx.invoked_subcommand is not None:
        return
    with _open_store(store_path) as store:
        render_runs(store.list(limit=limit), console, datetime.now(UTC))


@runs_app.command("show")
def runs_show(
    run_id: Annotated[str, typer.Argument(help="Run id, or a unique prefix of one.")],
    details: Annotated[bool, typer.Option(help="List every finding.")] = False,
    output: FormatOption = OutputFormat.TABLE,
    store_path: StoreOption = None,
) -> None:
    """Show the report of a saved run."""
    with _open_store(store_path) as store:
        try:
            run = store.get(run_id)
        except RunNotFoundError as exc:
            _fail(str(exc))
    if output is OutputFormat.JSON:
        typer.echo(report_json(run.report, run_id=run.id))
        return
    console.print(f"[dim]Run {run.id}, {run.started_at:%Y-%m-%d %H:%M %Z}[/dim]")
    render_report(run.report, console, details=details)


@app.command()
def diff(
    base_id: Annotated[
        str | None,
        typer.Argument(
            help="Earlier run. Default: the run before HEAD of the same target.",
            show_default=False,
        ),
    ] = None,
    head_id: Annotated[
        str | None,
        typer.Argument(
            help="Later run. Default: the latest run of BASE's target, or the latest run overall.",
            show_default=False,
        ),
    ] = None,
    output: FormatOption = OutputFormat.TABLE,
    store_path: StoreOption = None,
) -> None:
    """Compare two saved runs: scores, and which findings are new or resolved."""
    with _open_store(store_path) as store:
        try:
            base, head = _pick_runs(store, base_id, head_id)
        except RunNotFoundError as exc:
            _fail(str(exc))
    result = diff_runs(base, head)
    if output is OutputFormat.JSON:
        typer.echo(diff_json(result))
    else:
        render_diff(result, base, head, console)


def _pick_runs(
    store: SqliteRunStore, base_id: str | None, head_id: str | None
) -> tuple[ScanRun, ScanRun]:
    if base_id and head_id:
        return store.get(base_id), store.get(head_id)
    if base_id:
        base = store.get(base_id)
        head = store.latest(base.target, base.schemas)
        if head is None or head.id == base.id:
            raise RunNotFoundError(
                f"No later run of {base.target.label} to compare {base.id} with."
            )
        return base, head

    newest = store.list(limit=1)
    if not newest:
        raise RunNotFoundError("No saved runs yet. Run quorlo scan first.")
    head = store.get(newest[0].id)
    base = store.latest(head.target, head.schemas, before=head.started_at)
    if base is None:
        raise RunNotFoundError(
            f"Only one run of {head.target.label} is saved; "
            "scan again to have something to compare."
        )
    return base, head
