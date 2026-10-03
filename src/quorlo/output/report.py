"""A scan report: per-table summary and overall scores, as a table or JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable

from rich import box
from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from quorlo.models import TableKind
from quorlo.output.format import score_text
from quorlo.readiness import Dimension, Finding, ScanReport, TableReadiness
from quorlo.stats import ScanStats

HEADERS = {
    Dimension.MEANING: "Meaning",
    Dimension.CERTIFICATION: "Certified",
    Dimension.TRUST: "Trust",
    Dimension.LINEAGE: "Lineage",
    Dimension.GOVERNANCE: "Governed",
}


def name_prefix(report: ScanReport) -> str:
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
        self._prefix = name_prefix(report)
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
            table.add_column(HEADERS[dim], justify="right", no_wrap=True)
        table.add_column("Findings", justify="right", no_wrap=True)
        for t in sorted(self._report.tables, key=lambda t: (t.score is None, t.score or 0.0)):
            table.add_row(
                self._table_name(t),
                score_text(t.score),
                *(score_text(t.dimensions.get(d)) for d in self._dimensions),
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
        overall = Text("Overall: ").append_text(score_text(report.score))
        overall.append(f" across {len(report.tables)} tables, {report.finding_count} findings")
        yield overall
        for dim in self._dimensions:
            yield Text(f"  {dim.question:<26}").append_text(score_text(report.dimensions[dim]))
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
