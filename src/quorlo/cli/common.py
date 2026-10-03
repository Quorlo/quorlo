"""What every command shares: consoles, common options and error handling."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape

from quorlo.history import (
    SqliteRunStore,
    StoreError,
    default_store_path,
)

console = Console()


err_console = Console(stderr=True)


class OutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"


StoreOption = Annotated[
    Path | None,
    typer.Option(
        "--store",
        envvar="QUORLO_STORE",
        help="Run history file. Default: quorlo.db in your user data directory.",
        show_default=False,
    ),
]


FormatOption = Annotated[OutputFormat, typer.Option("--format", "-f")]


def fail(message: str) -> NoReturn:
    err_console.print(f"[red]Error:[/red] {escape(message)}")
    raise typer.Exit(code=2)


@contextmanager
def open_store(path: Path | None) -> Iterator[SqliteRunStore]:
    """The run history, with any store error inside the block reported cleanly."""
    try:
        with SqliteRunStore(path or default_store_path()) as store:
            yield store
    except StoreError as exc:
        fail(str(exc))
