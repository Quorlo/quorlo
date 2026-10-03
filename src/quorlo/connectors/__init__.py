"""Connectors: the plugin contract, discovery, and the built-in connectors.

Plugin authors import everything they need from here:

    from quorlo.connectors import Connector, ConnectionConfig, ConnectorError, ...

Built-in connectors live in subpackages (`quorlo.connectors.postgres`) and, like
third-party ones, are found through the `quorlo.connectors` entry-point group.
"""

from quorlo.connectors import registry
from quorlo.connectors.base import (
    ConnectionConfig,
    Connector,
    ConnectorCapabilities,
    ConnectorError,
    DatabaseInfo,
    FetchStats,
    read_database,
)
from quorlo.connectors.registry import (
    ConnectorInfo,
    ConnectorNotFoundError,
    InvalidConnectorError,
    available_connectors,
    load_connector,
)

__all__ = [
    "ConnectionConfig",
    "Connector",
    "ConnectorCapabilities",
    "ConnectorError",
    "ConnectorInfo",
    "ConnectorNotFoundError",
    "DatabaseInfo",
    "FetchStats",
    "InvalidConnectorError",
    "available_connectors",
    "load_connector",
    "read_database",
    "registry",
]
