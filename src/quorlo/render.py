"""Turn a ScanReport into terminal output or JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.history import RunDiff, ScanRun, ScoreChange
from quorlo.models import TableKind
from quorlo.readiness import Dimension, Finding, ScanReport, TableReadiness
from quorlo.stats import Phase, ScanStats
from quorlo.store import RunSummary, SinceLastRun


def _score_text(score: float | None) -> Text:
    if score is None:
        return Text("n/a", style="dim")
    style = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
    return Text(f"{score:.0%}", style=style)


# Short, whole-word headers so they never truncate in an 80-column terminal.
# The full question for each dimension is printed under the table.
_HEADERS = {
    Dimension.MEANING: "Meaning",
    Dimension.CERTIFICATION: "Certified",
    Dimension.TRUST: "Trust",
    Dimension.LINEAGE: "Lineage",
    Dimension.GOVERNANCE: "Governed",
}


def _name_prefix(report: ScanReport) -> str:
    """What every table name starts with: the database, plus the schema if there is only one."""
    schemas = {t.table.split(".")[1] for t in report.tables if t.table.count(".") >= 2}
    if len(schemas) == 1:
        return f"{report.database}.{schemas.pop()}."
    return f"{report.database}."


class ReportView:
    """A scan report in the terminal: per-table summary, overall scores, optional findings."""

    def __init__(self, report: ScanReport, findings: Iterable[Finding] = ()) -> None:
        self._report = report
        self._findings = findings
        self._prefix = _name_prefix(report)
        self._dimensions = [d for d in Dimension if d in report.dimensions]

    def render(self, console: Console, details: bool = False) -> None:
        console.print(self._summary())
        for line in self._overall():
            console.print(line)
        if details:
            findings = self._findings_table()
            if findings.row_count:
                console.print()
                console.print(findings)

    @property
    def _scope(self) -> str:
        return self._prefix.rstrip(".")

    def _summary(self) -> RichTable:
        table = RichTable(
            title=f"AI readiness: {self._scope} ({self._report.platform})",
            box=box.SIMPLE_HEAD,
            pad_edge=False,
        )
        # Fold rather than truncate: a name cut to "quorlo_demo.retai…" is useless.
        table.add_column("Table", overflow="fold")
        table.add_column("Score", justify="right", no_wrap=True)
        for dim in self._dimensions:
            table.add_column(_HEADERS[dim], justify="right", no_wrap=True)
        table.add_column("Findings", justify="right", no_wrap=True)
        for t in sorted(self._report.tables, key=lambda t: (t.score is None, t.score or 0.0)):
            table.add_row(
                self._table_name(t),
                _score_text(t.score),
                *(_score_text(t.dimensions.get(d)) for d in self._dimensions),
                str(t.finding_count),
            )
        return table

    def _table_name(self, table: TableReadiness) -> Text:
        name = Text(table.table.removeprefix(self._prefix))
        if table.kind is not TableKind.TABLE:
            name.append(f" ({table.kind.value.replace('_', ' ')})", style="dim")
        return name

    def _overall(self) -> Iterable[Text | str]:
        report = self._report
        overall = Text("Overall: ").append_text(_score_text(report.score))
        overall.append(f" across {len(report.tables)} tables, {report.finding_count} findings")
        yield overall
        for dim in self._dimensions:
            yield Text(f"  {dim.question:<26}").append_text(_score_text(report.dimensions[dim]))
        unscored = [d.value for d in Dimension if d not in report.dimensions]
        if unscored:
            yield f"  [dim]Not scored yet (no checks): {', '.join(unscored)}[/dim]"

    def _findings_table(self) -> RichTable:
        table = RichTable(title=f"Findings in {self._scope}")
        # Fold rather than truncate: a target cut to "retail_…" is useless.
        table.add_column("Target", overflow="fold")
        table.add_column("Check", style="dim", overflow="fold")
        table.add_column("Severity")
        table.add_column("Problem")
        for f in self._findings:
            table.add_row(
                f.target.removeprefix(self._prefix), f.check_id, f.severity.value, f.message
            )
        return table


def report_json(
    report: ScanReport,
    findings: Iterable[Finding] = (),
    run_id: str | None = None,
    stats: ScanStats | None = None,
) -> str:
    data = report.model_dump(mode="json")
    data["findings_count"] = report.finding_count
    data["findings"] = [
        f.model_dump(mode="json") | {"fingerprint": f.fingerprint} for f in findings
    ]
    if run_id is not None:
        data["run_id"] = run_id
    if stats is not None:
        data["stats"] = stats.model_dump(mode="json")
    return json.dumps(data, indent=2)


def _count(n: int, noun: str, plural: str | None = None) -> str:
    return f"{n:,} {noun if n == 1 else plural or noun + 's'}"


def stats_line(stats: ScanStats) -> Text:
    """'Scanned 1 schema, 8 tables, 47 columns in 0.42s: fetch 0.12s (4 queries) · ...'"""
    line = Text(
        f"Scanned {_count(stats.schemas, 'schema')}, {_count(stats.tables, 'table')}, "
        f"{_count(stats.columns, 'column')} in {stats.seconds:.2f}s: ",
        style="dim",
    )
    parts = []
    for phase in Phase:
        part = f"{phase.value} {stats.phases.get(phase, 0.0):.2f}s"
        if phase is Phase.FETCH:
            part += f" ({_count(stats.queries, 'query', 'queries')})"
        parts.append(part)
    return line.append(" · ".join(parts), style="dim")


# --- Run history ---------------------------------------------------------------------


def _ago(then: datetime, now: datetime) -> str:
    seconds = max(0, int((now - then).total_seconds()))
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def _pct(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.0%}"


def _points(score: float) -> int:
    """The whole percentage shown for a score, rounded exactly as `_pct` rounds it."""
    return int(f"{score * 100:.0f}")


def _delta_text(change: ScoreChange) -> Text:
    text = Text(f"{_pct(change.before)} → ").append_text(_score_text(change.after))
    if change.before is not None and change.after is not None:
        # The difference of the two numbers on screen, so "44% → 48%" never reads "+3".
        points = _points(change.after) - _points(change.before)
        if points:
            unit = "pt" if abs(points) == 1 else "pts"
            text.append(f" ({points:+d} {unit})", style="green" if points > 0 else "red")
    return text


def change_line(since: SinceLastRun, now: datetime) -> Text:
    """'Since last run (2 days ago): 44% → 51% (+7 pts), 6 resolved, 1 new.'"""
    line = Text(f"Since last run ({_ago(since.previous.started_at, now)}): ")
    line.append_text(_delta_text(ScoreChange(before=since.score_before, after=since.score_after)))
    line.append(f", {since.findings.resolved} resolved, {since.findings.new} new")
    if since.rules_changed:
        line.append(" (check rules changed; see quorlo diff)", style="yellow")
    return line


def render_diff(diff: RunDiff, base: ScanRun, head: ScanRun, console: Console) -> None:
    console.print(f"[bold]{escape(head.target.label)}[/bold]")
    console.print(f"  base  {base.id}  {base.started_at:%Y-%m-%d %H:%M %Z}")
    console.print(f"  head  {head.id}  {head.started_at:%Y-%m-%d %H:%M %Z}")
    for warning in diff.warnings:
        console.print(f"[yellow]Warning:[/yellow] {escape(warning)}")
    console.print()

    console.print(Text("Overall: ").append_text(_delta_text(diff.score)))
    for dim, change in diff.dimensions.items():
        console.print(Text(f"  {dim.question:<26}").append_text(_delta_text(change)))
    console.print(
        f"Findings: {len(diff.resolved_findings)} resolved, {len(diff.new_findings)} new, "
        f"{diff.unchanged_findings} unchanged"
    )

    prefix = f"{head.target.database}."
    if diff.tables_added or diff.tables_removed:
        console.print()
        for name in diff.tables_added:
            console.print(f"[green]+ table[/green] {escape(name.removeprefix(prefix))}")
        for name in diff.tables_removed:
            console.print(f"[red]- table[/red] {escape(name.removeprefix(prefix))}")

    if diff.tables_changed:
        console.print()
        tables = RichTable(title="Changed tables", box=box.SIMPLE_HEAD, pad_edge=False)
        tables.add_column("Table", overflow="fold")
        tables.add_column("Score", no_wrap=True)
        tables.add_column("Resolved", justify="right")
        tables.add_column("New", justify="right")
        for t in sorted(diff.tables_changed, key=lambda t: t.score.delta or 0.0):
            tables.add_row(
                t.table.removeprefix(prefix),
                _delta_text(t.score),
                str(t.resolved_findings),
                str(t.new_findings),
            )
        console.print(tables)

    for title, findings, style in (
        ("New findings", diff.new_findings, "red"),
        ("Resolved findings", diff.resolved_findings, "green"),
    ):
        if findings:
            console.print(f"\n[{style}]{title}[/{style}]")
            for f in findings:
                # Text, not markup: a table or column name may contain [brackets].
                line = Text(f"  {f.target.removeprefix(prefix)}: {f.message} ")
                console.print(line.append(f"({f.check_id})", style="dim"))


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
            _ago(run.started_at, self._now),
            *target,
            ", ".join(run.schemas) if run.schemas else "all",
            _score_text(run.score),
            str(run.tables),
            str(run.findings),
        ]


def diff_json(diff: RunDiff) -> str:
    data = diff.model_dump(mode="json")
    data["score"]["delta"] = diff.score.delta
    for dim, change in diff.dimensions.items():
        data["dimensions"][dim.value]["delta"] = change.delta
    return json.dumps(data, indent=2)
