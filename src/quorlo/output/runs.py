"""Saved runs, and how a scan compares with the previous run."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from rich import box
from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.history import RunSummary, ScoreChange, SinceLastRun
from quorlo.output.format import ago, delta_text, score_text


def change_line(since: SinceLastRun, now: datetime) -> Text:
    """'Since last run (2 days ago): 44% → 51% (+7 pts), 6 resolved, 1 new.'"""
    line = Text(f"Since last run ({ago(since.previous.started_at, now)}): ")
    line.append_text(delta_text(ScoreChange(before=since.score_before, after=since.score_after)))
    line.append(f", {since.findings.resolved} resolved, {since.findings.new} new")
    if since.rules_changed:
        line.append(" (check rules changed; see quorlo diff)", style="yellow")
    return line


class RunsView:
    """Saved runs as a table. When they all share one target, it moves to the title."""

    def __init__(self, runs: Sequence[RunSummary], now: datetime) -> None:
        self._runs = runs
        self._now = now
        self._one_target = len({r.target for r in runs}) == 1

    def render(self, console: Console) -> None:
        if not self._runs:
            console.print("No saved runs yet. Run [bold]quorlo scan[/bold] to save one.")
            return
        console.print(self._table())

    def _table(self) -> RichTable:
        title = f"Runs of {self._runs[0].target.label}" if self._one_target else None
        table = RichTable(title=title, box=box.SIMPLE_HEAD, pad_edge=False)
        table.add_column("Run", no_wrap=True)
        table.add_column("When", no_wrap=True)
        if not self._one_target:
            table.add_column("Target", overflow="fold")
        table.add_column("Schemas", overflow="fold")
        table.add_column("Score", justify="right")
        table.add_column("Tables", justify="right")
        table.add_column("Findings", justify="right")
        for r in self._runs:
            table.add_row(*self._cells(r))
        return table

    def _cells(self, run: RunSummary) -> list[str | Text]:
        target = [] if self._one_target else [run.target.label]
        return [
            run.id,
            ago(run.started_at, self._now),
            *target,
            ", ".join(run.schemas) if run.schemas else "all",
            score_text(run.score),
            str(run.tables),
            str(run.findings),
        ]
