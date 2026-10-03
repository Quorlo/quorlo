"""Connector discovery through the `quorlo.connectors` entry-point group.

A connector package registers itself in its own pyproject.toml:

    [project.entry-points."quorlo.connectors"]
    mysql = "quorlo_mysql:MySQLConnector"

The built-in Postgres connector registers the same way, so core always goes through
the plugin path.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points

from quorlo.connector import Connector, ConnectorCapabilities, ConnectorError

ENTRY_POINT_GROUP = "quorlo.connectors"

_REQUIRED_MEMBERS = (
    "name",
    "capabilities",
    "test_connection",
    "describe",
    "list_schemas",
    "iter_schemas",
    "stats",
    "close",
)


class ConnectorNotFoundError(ConnectorError):
    def __init__(self, name: str, installed: list[str]) -> None:
        listed = ", ".join(sorted(installed)) or "none"
        super().__init__(f"No connector named {name!r}. Installed connectors: {listed}.")
        self.name = name
        self.installed = installed


class InvalidConnectorError(ConnectorError):
    pass


@dataclass(frozen=True)
class ConnectorInfo:
    name: str
    package: str | None
    version: str | None
    capabilities: ConnectorCapabilities | None
    error: str | None = None


def _entry_points() -> dict[str, EntryPoint]:
    return {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}


def _validate(name: str, obj: object) -> type[Connector]:
    if not isinstance(obj, type):
        raise InvalidConnectorError(f"Connector {name!r} must point to a class, got {obj!r}.")
    missing = [m for m in _REQUIRED_MEMBERS if not hasattr(obj, m)]
    if missing:
        raise InvalidConnectorError(
            f"Connector {name!r} ({obj.__qualname__}) is missing: {', '.join(missing)}."
        )
    if not isinstance(obj.capabilities, ConnectorCapabilities):
        raise InvalidConnectorError(
            f"Connector {name!r} capabilities must be ConnectorCapabilities."
        )
    return obj  # type: ignore[return-value]


def load_connector(name: str) -> type[Connector]:
    eps = _entry_points()
    if name not in eps:
        raise ConnectorNotFoundError(name, list(eps))
    return _validate(name, eps[name].load())


def available_connectors() -> list[ConnectorInfo]:
    """Describe every installed connector. A broken plugin is reported, not raised."""
    infos = []
    for name, ep in sorted(_entry_points().items()):
        dist = ep.dist
        package = dist.name if dist else None
        version = dist.version if dist else None
        try:
            cls = _validate(name, ep.load())
        except Exception as exc:  # a broken third-party plugin must not break listing
            infos.append(ConnectorInfo(name, package, version, None, error=str(exc)))
            continue
        infos.append(ConnectorInfo(name, package, version, cls.capabilities))
    return infos
