"""Turn a ScanReport into terminal output or JSON."""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.models import TableKind
from quorlo.readiness import Dimension, ScanReport


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


def render_report(report: ScanReport, console: Console, details: bool = False) -> None:
    dims = [d for d in Dimension if d in report.dimensions]
    prefix = _name_prefix(report)
    scope = prefix.rstrip(".")

    summary = RichTable(
        title=f"AI readiness: {scope} ({report.platform})", box=box.SIMPLE_HEAD, pad_edge=False
    )
    # Fold rather than truncate: a name cut to "quorlo_demo.retai…" is useless.
    summary.add_column("Table", overflow="fold")
    summary.add_column("Score", justify="right", no_wrap=True)
    for dim in dims:
        summary.add_column(_HEADERS[dim], justify="right", no_wrap=True)
    summary.add_column("Findings", justify="right", no_wrap=True)

    for t in sorted(report.tables, key=lambda t: (t.score is None, t.score or 0.0)):
        name = Text(t.table.removeprefix(prefix))
        if t.kind is not TableKind.TABLE:
            name.append(f" ({t.kind.value.replace('_', ' ')})", style="dim")
        summary.add_row(
            name,
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
        findings = RichTable(title=f"Findings in {scope}")
        # Fold rather than truncate: a target cut to "retail_…" is useless.
        findings.add_column("Target", overflow="fold")
        findings.add_column("Check", style="dim", overflow="fold")
        findings.add_column("Severity")
        findings.add_column("Problem")
        for f in report.findings:
            target = f.target.removeprefix(prefix)
            findings.add_row(target, f.check_id, f.severity.value, f.message)
        console.print(findings)


def report_json(report: ScanReport) -> str:
    data = report.model_dump(mode="json")
    data["findings_count"] = len(report.findings)
    return json.dumps(data, indent=2)
