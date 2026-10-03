"""The contract every connector satisfies.

`Connector` is a structural `Protocol`, not a base class: a connector package only has to
have the right shape, so it never depends on core's class hierarchy. Connectors are
discovered through the `quorlo.connectors` entry-point group (see `quorlo.registry`).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from quorlo.models import Database, Schema


class ConnectorCapabilities(BaseModel):
    """What a connector is able to do. Everything that touches more than metadata defaults off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reads_data: bool = False
    metadata_write_back: bool = False
    sample_values: bool = False


class ConnectionConfig(BaseModel):
    """How to reach a platform.

    The DSN is a `SecretStr` so a password embedded in it never shows up in a repr,
    log line or traceback. Call `dsn.get_secret_value()` only where the driver needs it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr
    read_only: bool = True
    allow_sample_values: bool = False
    options: dict[str, Any] = Field(default_factory=dict)


class ConnectorError(Exception):
    """Base error for anything a connector raises on purpose."""


class DatabaseInfo(BaseModel):
    """What a connection points at, known before any table is fetched."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    platform: str
    location: str | None = Field(
        default=None, description="e.g. 'postgres://db.internal:5432/warehouse'. No credentials."
    )


@dataclass(frozen=True)
class FetchStats:
    """What a connector has fetched so far: the cost side of a scan."""

    queries: int = 0
    rows: int = 0
    seconds: float = 0.0

    def plus(self, rows: int, seconds: float) -> FetchStats:
        """These stats with one more query added."""
        return FetchStats(self.queries + 1, self.rows + rows, self.seconds + seconds)


@runtime_checkable
class Connector(Protocol):
    """Reads metadata from one platform. Plugins satisfy this shape; they don't inherit it.

    Fetching is batch-first and streams: `iter_schemas` yields one complete schema at a
    time, fetched with a fixed number of queries per schema however many tables it has,
    so memory stays bounded by the largest schema rather than the whole estate.
    """

    name: ClassVar[str]
    capabilities: ClassVar[ConnectorCapabilities]

    def __init__(self, config: ConnectionConfig) -> None: ...

    def test_connection(self) -> None:
        """Raise `ConnectorError` if the platform cannot be reached with this config."""
        ...

    def describe(self) -> DatabaseInfo:
        """The database this connection points at. Must not fetch any tables."""
        ...

    def list_schemas(self) -> list[str]:
        """Names of all non-system schemas."""
        ...

    def iter_schemas(self, schemas: Sequence[str] | None = None) -> Iterator[Schema]:
        """Yield the given schemas (all non-system ones when None), one complete schema at
        a time. Raise `ConnectorError` for a schema that does not exist."""
        ...

    @property
    def stats(self) -> FetchStats:
        """Queries issued and rows read so far on this connector."""
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc_info: object) -> None: ...


def read_database(connector: Connector, schemas: Sequence[str] | None = None) -> Database:
    """Collect a whole database in memory. Fine for tests and small estates; a scan streams."""
    info = connector.describe()
    return Database(
        name=info.name,
        platform=info.platform,
        location=info.location,
        schemas=tuple(connector.iter_schemas(schemas)),
    )
