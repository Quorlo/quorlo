"""The contract every connector satisfies.

`Connector` is a structural `Protocol`, not a base class: a connector package only has to
have the right shape, so it never depends on core's class hierarchy. Connectors are
discovered through the `quorlo.connectors` entry-point group (see `quorlo.registry`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from quorlo.models import Database


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


@runtime_checkable
class Connector(Protocol):
    name: ClassVar[str]
    capabilities: ClassVar[ConnectorCapabilities]

    def __init__(self, config: ConnectionConfig) -> None: ...

    def test_connection(self) -> None:
        """Raise `ConnectorError` if the platform cannot be reached with this config."""
        ...

    def list_schemas(self) -> list[str]: ...

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        """Read metadata for the given schemas (all non-system schemas when None)."""
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc_info: object) -> None: ...
