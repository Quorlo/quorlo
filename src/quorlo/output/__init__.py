"""Everything Quorlo prints: terminal views and JSON. Views render; they never compute."""

from quorlo.output.diff import DiffView, diff_json
from quorlo.output.findings import FindingsView, findings_json
from quorlo.output.next_steps import NextSteps
from quorlo.output.report import ReportView, name_prefix, report_json
from quorlo.output.runs import RunsView, change_line
from quorlo.output.stats import stats_lines

__all__ = [
    "DiffView",
    "FindingsView",
    "NextSteps",
    "ReportView",
    "RunsView",
    "change_line",
    "diff_json",
    "findings_json",
    "name_prefix",
    "report_json",
    "stats_lines",
]
