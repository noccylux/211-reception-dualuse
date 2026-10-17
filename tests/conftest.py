"""Tests must not touch the running desk or make paid model requests."""
import json
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
    from dualuse import evaluation
    # The workstation's own evaluation output must not change test results; tests write their own.
    monkeypatch.setattr(evaluation, "RESULTS", Path(_database_directory.name) / "no-evaluation.json")
    api = sys.modules.get("dualuse.api")
    if api:
        from dualuse.holdqueue import HoldQueue
        monkeypatch.setattr(api, "QUEUE", HoldQueue(1800, mode="rules"))


@pytest.fixture
def evaluation_file(monkeypatch, tmp_path):
    """Points the app at a small evaluation result: per text column, the tiers of one needs-a-person
    and one routine message, as the evaluation script would save them."""
    from dualuse import evaluation
    path = tmp_path / "eval_messages.json"
    monkeypatch.setattr(evaluation, "RESULTS", path)

    def write(english=("normal", "priority"), original=("unknown", "unknown")):
        def rows(tiers):
            return [{"label": label, "tier": tier, "sampled": True, "subset": label == "needs", "review": "", "error": ""}
                    for label, tier in zip(("needs", "routine"), tiers)]

        texts = {"english": rows(english), "original": rows(original)}
        summaries = {method: {text: evaluation.summarize(r) for text, r in texts.items()} for method in ("rules", "model")}
        summaries["fifo"] = {text: evaluation.fifo_summary(r) for text, r in texts.items()}
        path.write_text(json.dumps({"label": "Recorded SMS (test fixture), proxy labels", "generated_at": "Sat 2026-10-17 14:00 PT",
                                    "summaries": summaries, "rows": [{"id": "1"}]}), encoding="utf-8")
        return path

    return write
