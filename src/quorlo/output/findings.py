"""A run's findings, grouped: worst table first, under the five questions, with fixes."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.history import CheckGroup, FindingQuery, RunSummary, TableFindings
from quorlo.output.format import count, pct


class FindingsView:
    """Prints grouped findings. Long column lists are cut, so one line stays one line."""

    max_columns = 10

    def __init__(
        self, run: RunSummary, tables: Sequence[TableFindings], query: FindingQuery
    ) -> None:
        self._run = run
        self._tables = tables
        self._query = query
        self._prefix = f"{run.target.database}."
        # One width for every grid, so details line up across tables and questions.
        self._check_width = max((len(g.check_id) for t in tables for g in t.groups), default=0)
        self._width = max((len(g.check_id) for t in tables for g in t.groups), default=0)

    def render(self, console: Console) -> None:
        console.print(self._header())
        if not self._tables:
            console.print(
                "\nNo findings match." if self._filtered else "\nNo findings: every check passed."
            )
            return
        for table in self._tables:
            console.print()
            self._render_table(console, table)

    @property
    def _filtered(self) -> bool:
        return bool(self._query.tables or self._query.dimensions or self._query.checks)

    def _header(self) -> Text:
        header = Text(f"Findings in run {self._run.id} · {self._run.target.label}", style="bold")
        if self._filtered:
            header.append(f"  ({self._describe_query()})", style="dim")
        return header

    def _describe_query(self) -> str:
        parts = []
        for label, values in (
            ("table", self._query.tables),
            ("dimension", [d.value for d in self._query.dimensions]),
            ("check", self._query.checks),
        ):
            if values:
                parts.append(f"{label}: {', '.join(values)}")
        return "; ".join(parts)

    def _render_table(self, console: Console, table: TableFindings) -> None:
        title = Text(table.table.removeprefix(self._prefix), style="bold")
        title.append(
            f"  ({pct(table.score)}, {count(table.finding_count, 'finding')})", style="dim"
        )
        console.print(title)
        for dimension, groups in table.by_dimension().items():
            console.print(f"  {dimension.question}")
            console.print(self._groups_grid(groups))

    def _groups_grid(self, groups: Sequence[CheckGroup]) -> RichTable:
        """Check ids in one column and details in the next, so wrapped text stays aligned."""
        grid = RichTable.grid(padding=(0, 2), pad_edge=False)
        grid.add_column(width=2)  # indent
        grid.add_column(style="cyan", no_wrap=True, min_width=self._check_width)
        grid.add_column(overflow="fold")
        for group in groups:
            grid.add_row("", group.check_id, self._detail(group))
            grid.add_row("", "", Text(f"fix: {group.fix_hint}", style="dim"))
        return grid

    def _detail(self, group: CheckGroup) -> Text:
        if not group.columns:
            # A table-level finding says it best in its own words (e.g. which tables match).
            return Text("; ".join(group.messages) or group.summary)
        shown = ", ".join(group.columns[: self.max_columns])
        hidden = len(group.columns) - self.max_columns
        if hidden > 0:
            shown += f" and {hidden} more"
        return Text(shown).append(f" · {group.summary}", style="dim")


def findings_json(run: RunSummary, tables: Sequence[TableFindings], query: FindingQuery) -> str:
    return json.dumps(
        {
            "run_id": run.id,
            "target": run.target.model_dump(mode="json"),
            "query": query.model_dump(mode="json"),
            "tables": [t.model_dump(mode="json") for t in tables],
        },
        indent=2,
    )
