"""`quorlo version` and `quorlo connectors`."""

from __future__ import annotations

from rich.table import Table as RichTable

import quorlo
from quorlo.cli.common import (
    console,
)
from quorlo.connectors import registry


def version() -> None:
    """Show the Quorlo version."""
    console.print(f"quorlo {quorlo.__version__}")


def connectors() -> None:
    """List installed connectors and what they are allowed to do."""
    infos = registry.available_connectors()
    if not infos:
        console.print("No connectors installed.")
        return
    table = RichTable()
    for col in ("Name", "Package", "Version", "Reads data", "Write-back", "Sample values"):
        table.add_column(col)
    for info in infos:
        if info.capabilities is None:
            table.add_row(
                info.name, info.package or "", info.version or "", f"[red]{info.error}[/red]"
            )
            continue
        caps = info.capabilities
        table.add_row(
            info.name,
            info.package or "",
            info.version or "",
            *(
                "yes" if v else "no"
                for v in (caps.reads_data, caps.metadata_write_back, caps.sample_values)
            ),
        )
    console.print(table)
