from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import EntryPoint
from typing import ClassVar

import pytest
from pydantic import SecretStr

from quorlo import registry
from quorlo.connector import ConnectionConfig, Connector, ConnectorCapabilities
from quorlo.models import Database


class FakeConnector:
    name: ClassVar[str] = "fake"
    capabilities: ClassVar[ConnectorCapabilities] = ConnectorCapabilities()

    def __init__(self, config: ConnectionConfig) -> None:
        self.config = config

    def test_connection(self) -> None:
        pass

    def list_schemas(self) -> list[str]:
        return []

    def scan(self, schemas: Sequence[str] | None = None) -> Database:
        return Database(name="fake", platform="fake")

    def close(self) -> None:
        pass

    def __enter__(self) -> FakeConnector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class NotAConnector:
    name = "broken"


@pytest.fixture
def fake_entry_points(monkeypatch):
    eps = {
        "fake": EntryPoint("fake", f"{__name__}:FakeConnector", registry.ENTRY_POINT_GROUP),
        "broken": EntryPoint("broken", f"{__name__}:NotAConnector", registry.ENTRY_POINT_GROUP),
    }
    monkeypatch.setattr(registry, "_entry_points", lambda: eps)
    return eps


def test_fake_connector_satisfies_protocol():
    instance = FakeConnector(ConnectionConfig(dsn=SecretStr("x")))
    assert isinstance(instance, Connector)


def test_load_connector(fake_entry_points):
    assert registry.load_connector("fake") is FakeConnector


def test_load_unknown_connector_lists_installed(fake_entry_points):
    with pytest.raises(registry.ConnectorNotFoundError, match="broken, fake"):
        registry.load_connector("snowflake")


def test_load_invalid_connector(fake_entry_points):
    with pytest.raises(registry.InvalidConnectorError, match="missing: capabilities"):
        registry.load_connector("broken")


def test_available_connectors_reports_broken_plugins(fake_entry_points):
    infos = {i.name: i for i in registry.available_connectors()}
    assert infos["fake"].capabilities == ConnectorCapabilities()
    assert infos["fake"].error is None
    assert infos["broken"].capabilities is None
    assert "missing" in infos["broken"].error


def test_capabilities_default_to_metadata_only():
    caps = ConnectorCapabilities()
    assert not caps.reads_data
    assert not caps.metadata_write_back
    assert not caps.sample_values


def test_dsn_is_not_leaked_by_repr():
    config = ConnectionConfig(dsn=SecretStr("postgresql://u:hunter2@h/db"))
    assert "hunter2" not in repr(config)
    assert "hunter2" not in str(config)
    assert "hunter2" not in config.model_dump_json()
    assert config.read_only
    assert not config.allow_sample_values
