"""What changed between two runs."""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.history import RunDiff, ScanRun
from quorlo.output.format import delta_text


class DiffView:
    """Two runs compared: header, score changes, changed tables, new and resolved findings."""

    def __init__(self, diff: RunDiff, base: ScanRun, head: ScanRun) -> None:
        self._diff = diff
        self._base = base
        self._head = head
        self._prefix = f"{head.target.database}."

    def render(self, console: Console) -> None:
        self._header(console)
        self._scores(console)
        self._table_changes(console)
        self._findings(console)

    def _header(self, console: Console) -> None:
        console.print(f"[bold]{escape(self._head.target.label)}[/bold]")
        for label, run in (("base", self._base), ("head", self._head)):
            console.print(f"  {label}  {run.id}  {run.started_at:%Y-%m-%d %H:%M %Z}")
        for warning in self._diff.warnings:
            console.print(f"[yellow]Warning:[/yellow] {escape(warning)}")
        console.print()

    def _scores(self, console: Console) -> None:
        diff = self._diff
        console.print(Text("Overall: ").append_text(delta_text(diff.score)))
        for dim, change in diff.dimensions.items():
            console.print(Text(f"  {dim.question:<26}").append_text(delta_text(change)))
        console.print(
            f"Findings: {len(diff.resolved_findings)} resolved, {len(diff.new_findings)} new, "
            f"{diff.unchanged_findings} unchanged"
        )

    def _table_changes(self, console: Console) -> None:
        diff = self._diff
        if diff.tables_added or diff.tables_removed:
            console.print()
            for name in diff.tables_added:
                console.print(f"[green]+ table[/green] {escape(self._short(name))}")
            for name in diff.tables_removed:
                console.print(f"[red]- table[/red] {escape(self._short(name))}")
        if diff.tables_changed:
            console.print()
            console.print(self._changed_tables())

    def _changed_tables(self) -> RichTable:
        table = RichTable(title="Changed tables", box=box.SIMPLE_HEAD, pad_edge=False)
        table.add_column("Table", overflow="fold")
        table.add_column("Score", no_wrap=True)
        table.add_column("Resolved", justify="right")
        table.add_column("New", justify="right")
        for t in sorted(self._diff.tables_changed, key=lambda t: t.score.delta or 0.0):
            table.add_row(
                self._short(t.table),
                delta_text(t.score),
                str(t.resolved_findings),
                str(t.new_findings),
            )
        return table

    def _findings(self, console: Console) -> None:
        for title, findings, style in (
            ("New findings", self._diff.new_findings, "red"),
            ("Resolved findings", self._diff.resolved_findings, "green"),
        ):
            if findings:
                console.print(f"\n[{style}]{title}[/{style}]")
                for f in findings:
                    # Text, not markup: a table or column name may contain [brackets].
                    line = Text(f"  {self._short(f.target)}: {f.message} ")
                    console.print(line.append(f"({f.check_id})", style="dim"))

    def _short(self, name: str) -> str:
        return name.removeprefix(self._prefix)


def diff_json(diff: RunDiff) -> str:
    data = diff.model_dump(mode="json")
    data["score"]["delta"] = diff.score.delta
    for dim, change in diff.dimensions.items():
        data["dimensions"][dim.value]["delta"] = change.delta
    return json.dumps(data, indent=2)
