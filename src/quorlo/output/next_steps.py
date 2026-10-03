"""What to run after a scan, so the way from a score to a fix is one copy-paste away."""

from __future__ import annotations

from collections.abc import Iterator

from rich.text import Text

from quorlo.readiness import ScanReport, TableReadiness


class NextSteps:
    """Hint lines for the end of `quorlo scan`."""

    def __init__(self, report: ScanReport, saved: bool, store_flag: str = "") -> None:
        self._report = report
        self._saved = saved
        # Set when the run went to a store given with --store: the hint must point there too.
        self._store_flag = f" --store {store_flag}" if store_flag else ""

    def lines(self) -> Iterator[Text]:
        worst = self._worst_table()
        if worst is None:
            return
        if not self._saved:
            yield Text(
                "Findings were not saved (--no-save). Scan without it to see them with "
                "quorlo findings.",
                style="dim",
            )
            return
        commands = [
            (f"quorlo findings{self._store_flag}", "what to fix, worst table first"),
            (
                f"quorlo findings --table {self._short_name(worst)}{self._store_flag}",
                "start with the lowest-scoring table",
            ),
        ]
        width = max(len(command) for command, _ in commands)
        for i, (command, why) in enumerate(commands):
            line = Text("Next: " if i == 0 else "      ", style="bold")
            line.append(f"{command:<{width}}  ")
            yield line.append(why, style="dim")

    def _worst_table(self) -> TableReadiness | None:
        candidates = [t for t in self._report.tables if t.finding_count and t.score is not None]
        return min(candidates, key=lambda t: (t.score, -t.finding_count), default=None)

    def _short_name(self, table: TableReadiness) -> str:
        """The bare table name if it is unique in the report, else schema.table."""
        bare = table.table.rsplit(".", 1)[-1]
        same = [t for t in self._report.tables if t.table.rsplit(".", 1)[-1] == bare]
        return bare if len(same) == 1 else table.table.split(".", 1)[-1]
