"""Where a scan's time went."""

from __future__ import annotations

from rich.text import Text

from quorlo.output.format import count
from quorlo.stats import Phase, ScanStats


def stats_lines(stats: ScanStats) -> list[Text]:
    """'Scanned 2 schemas, 8 tables, 39 columns in 0.42s', then the time per phase."""
    size = (
        f"Scanned {count(stats.schemas, 'schema')}, {count(stats.tables, 'table')}, "
        f"{count(stats.columns, 'column')} in {stats.seconds:.2f}s"
    )
    phases = []
    for phase in Phase:
        part = f"{phase.value} {stats.phases.get(phase, 0.0):.2f}s"
        if phase is Phase.FETCH:
            part += f" ({count(stats.queries, 'query', 'queries')})"
        phases.append(part)
    return [Text(size, style="dim"), Text("  " + " · ".join(phases), style="dim")]
