import pytest


@pytest.fixture(autouse=True)
def isolated_run_store(tmp_path, monkeypatch):
    """Never let a test write to the developer's real run history."""
    path = tmp_path / "runs.db"
    monkeypatch.setenv("QUORLO_STORE", str(path))
    return path
