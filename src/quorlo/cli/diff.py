"""`quorlo diff`."""

from __future__ import annotations

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
    ScanRun,
    SqliteRunStore,
    diff_runs,
)
from quorlo.output import (
    DiffView,
    diff_json,
)


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
    with open_store(store_path) as store:
        try:
            base, head = _pick_runs(store, base_id, head_id)
        except RunNotFoundError as exc:
            fail(str(exc))
    result = diff_runs(base, head)
    if output is OutputFormat.JSON:
        typer.echo(diff_json(result))
    else:
        DiffView(result, base, head).render(console)


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
    previous = store.previous(head)
    if previous is None:
        raise RunNotFoundError(
            f"Only one run of {head.target.label} is saved; "
            "scan again to have something to compare."
        )
    return store.get(previous.id), head
