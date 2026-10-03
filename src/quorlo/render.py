"""Turn a ScanReport into terminal output or JSON."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.readiness import Dimension, ScanReport


def _score_text(score: float | None) -> Text:
    if score is None:
        return Text("n/a", style="dim")
    style = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "red"
    return Text(f"{score:.0%}", style=style)


def render_report(report: ScanReport, console: Console, details: bool = False) -> None:
    dims = [d for d in Dimension if d in report.dimensions]

    summary = RichTable(title=f"AI readiness: {report.database} ({report.platform})")
    summary.add_column("Table")
    summary.add_column("Kind", style="dim")
    summary.add_column("Score", justify="right")
    for dim in dims:
        summary.add_column(dim.value.title(), justify="right")
    summary.add_column("Findings", justify="right")

    for t in sorted(report.tables, key=lambda t: (t.score is None, t.score or 0.0)):
        summary.add_row(
            t.table,
            t.kind.value,
            _score_text(t.score),
            *(_score_text(t.dimensions.get(d)) for d in dims),
            str(len(t.findings)),
        )
    console.print(summary)

    overall = Text("Overall: ").append_text(_score_text(report.score))
    overall.append(f" across {len(report.tables)} tables, {len(report.findings)} findings")
    console.print(overall)
    for dim in dims:
        line = Text(f"  {dim.question:<26}").append_text(_score_text(report.dimensions[dim]))
        console.print(line)
    unscored = [d for d in Dimension if d not in report.dimensions]
    if unscored:
        names = ", ".join(d.value for d in unscored)
        console.print(f"  [dim]Not scored yet (no checks): {names}[/dim]")

    if details and report.findings:
        console.print()
        findings = RichTable(title=f"Findings in {report.database}")
        # Fold rather than truncate: a target cut to "retail_…" is useless.
        findings.add_column("Target", overflow="fold")
        findings.add_column("Check", style="dim", overflow="fold")
        findings.add_column("Severity")
        findings.add_column("Problem")
        prefix = f"{report.database}."
        for f in report.findings:
            target = f.target.removeprefix(prefix)
            findings.add_row(target, f.check_id, f.severity.value, f.message)
        console.print(findings)


def report_json(report: ScanReport) -> str:
    data = report.model_dump(mode="json")
    data["findings_count"] = len(report.findings)
    return json.dumps(data, indent=2)
