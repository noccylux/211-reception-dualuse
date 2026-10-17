"""Tests must not touch the running desk or make paid model requests."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_database_directory = tempfile.TemporaryDirectory(prefix="211-tests-")
os.environ["DUALUSE_QUEUE_DB"] = str(Path(_database_directory.name) / "desk.sqlite3")


@pytest.fixture(autouse=True)
def isolated_desk(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    api = sys.modules.get("dualuse.api")
    if api:
        from dualuse.holdqueue import HoldQueue
        monkeypatch.setattr(api, "QUEUE", HoldQueue(1800, mode="rules"))
