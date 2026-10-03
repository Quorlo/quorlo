"""`quorlo findings`: what to fix, worst table first."""

from __future__ import annotations

from typing import Annotated

import typer

from quorlo.cli.common import FormatOption, OutputFormat, StoreOption, console, fail, open_store
from quorlo.history import FindingGrouper, FindingQuery, RunNotFoundError, RunStore, RunSummary
from quorlo.output import FindingsView, findings_json
from quorlo.readiness import CHECKS_BY_ID, Dimension


def findings(
    run_id: Annotated[
        str | None,
        typer.Option("--run", help="Run id, or a unique prefix. Default: the latest saved run."),
    ] = None,
    table: Annotated[
        list[str] | None,
        typer.Option("--table", "-t", help="Table name, schema.table or full name. Repeatable."),
    ] = None,
    dimension: Annotated[
        list[Dimension] | None,
        typer.Option("--dimension", "-d", help="Only this question. Repeatable."),
    ] = None,
    check: Annotated[
        list[str] | None,
        typer.Option("--check", "-c", help="Only this check id. Repeatable."),
    ] = None,
    output: FormatOption = OutputFormat.TABLE,
    store_path: StoreOption = None,
) -> None:
    """Show what to fix in a saved run: worst table first, one line per check, with fixes."""
    query = FindingQuery(
        tables=tuple(table or ()), dimensions=tuple(dimension or ()), checks=tuple(check or ())
    )
    _reject_unknown_checks(query)
    with open_store(store_path) as store:
        run = _pick_run(store, run_id)
        grouper = FindingGrouper(store.report(run.id), CHECKS_BY_ID)
        tables = grouper.group(store.findings(run.id, query))
    if output is OutputFormat.JSON:
        typer.echo(findings_json(run, tables, query))
    else:
        FindingsView(run, tables, query).render(console)


def _reject_unknown_checks(query: FindingQuery) -> None:
    unknown = [c for c in query.checks if c not in CHECKS_BY_ID]
    if unknown:
        fail(f"Unknown check: {', '.join(unknown)}. Checks: {', '.join(sorted(CHECKS_BY_ID))}.")


def _pick_run(store: RunStore, run_id: str | None) -> RunSummary:
    try:
        if run_id:
            return store.summary(run_id)
        latest = store.list(limit=1)
    except RunNotFoundError as exc:
        fail(str(exc))
    if not latest:
        fail("No saved runs yet. Run quorlo scan first.")
    return latest[0]
