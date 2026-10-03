"""The `quorlo` command line: every command, registered in one place."""

import typer

from quorlo.cli import diff, findings, info, runs, scan

app = typer.Typer(
    help="Make your data AI-ready: scan platforms and score how ready each table is.",
    no_args_is_help=True,
    add_completion=False,
)
app.command()(info.version)
app.command()(info.connectors)
app.command()(scan.scan)
app.command()(findings.findings)
app.add_typer(runs.runs_app, name="runs")
app.command()(diff.diff)
