import os

import pytest

# Plain, unstyled output in every test, whatever the environment says, so asserted text is
# never split by ANSI codes. Must happen at import: Quorlo's consoles and Typer's error
# console read these once. Typer forces styling when GITHUB_ACTIONS is set (as in CI) and
# offers _TYPER_FORCE_DISABLE_TERMINAL to turn that off.
os.environ.pop("FORCE_COLOR", None)
os.environ["NO_COLOR"] = "1"
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"


@pytest.fixture(autouse=True)
def isolated_run_store(tmp_path, monkeypatch):
    """Never let a test write to the developer's real run history."""
    path = tmp_path / "runs.db"
    monkeypatch.setenv("QUORLO_STORE", str(path))
    return path
