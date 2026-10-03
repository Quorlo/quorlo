import os

import pytest

# Plain, uncoloured output in every test, whatever the environment says. Must happen at
# import, before quorlo's module-level consoles are created: they read these variables
# once. CI sets FORCE_COLOR, which otherwise splits asserted text with ANSI codes.
os.environ.pop("FORCE_COLOR", None)
os.environ["NO_COLOR"] = "1"


@pytest.fixture(autouse=True)
def isolated_run_store(tmp_path, monkeypatch):
    """Never let a test write to the developer's real run history."""
    path = tmp_path / "runs.db"
    monkeypatch.setenv("QUORLO_STORE", str(path))
    return path
