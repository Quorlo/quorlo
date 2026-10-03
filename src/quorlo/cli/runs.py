"""`quorlo runs` and `quorlo runs show`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from quorlo.cli.common import (
    FormatOption,
    OutputFormat,
    StoreOption,
    console,
    fail,
    open_store,
)
from quorlo.history import (
    RunNotFoundError,
)
from quorlo.output import (
    ReportView,
    RunsView,
    report_json,
)

runs_app = typer.Typer(
    help="Saved scan runs. Without a subcommand, lists the most recent ones.",
    invoke_without_command=True,
)


@runs_app.callback()
def runs(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(min=1, help="How many runs to list.")] = 20,
    store_path: StoreOption = None,
) -> None:
    """List saved scan runs, newest first."""
    if ctx.invoked_subcommand is not None:
        return
    with open_store(store_path) as store:
        RunsView(store.list(limit=limit), datetime.now(UTC)).render(console)


@runs_app.command("show")
def runs_show(
    run_id: Annotated[str, typer.Argument(help="Run id, or a unique prefix of one.")],
    details: Annotated[bool, typer.Option(help="List every finding.")] = False,
    output: FormatOption = OutputFormat.TABLE,
    store_path: StoreOption = None,
) -> None:
    """Show the report of a saved run."""
    with open_store(store_path) as store:
        try:
            run = store.get(run_id)
        except RunNotFoundError as exc:
            fail(str(exc))
    if output is OutputFormat.JSON:
        typer.echo(report_json(run.report, run.findings, run_id=run.id))
        return
    console.print(f"[dim]Run {run.id}, {run.started_at:%Y-%m-%d %H:%M %Z}[/dim]")
    ReportView(run.report, run.findings).render(console, details=details)
