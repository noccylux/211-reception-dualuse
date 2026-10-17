from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dualuse import api
from dualuse.holdqueue import HoldQueue
from dualuse.live_surge import Caller, arrival_offsets, load_messages, plan_surge, start_surge

FIXTURES = Path(__file__).parent / "fixtures"


def test_messages_come_from_direct_test_rows_and_are_labeled_recorded():
    callers = load_messages(FIXTURES / "munro_sample.csv", 3, seed=1)
    assert len(callers) == 3
    assert all(c.origin.startswith("recorded") and "Munro" in c.origin for c in callers)
    texts = {c.lines[0] for c in callers}
    assert "UN reports roads closed near Leogane" not in texts and "Training row that must never be used" not in texts


def test_a_missing_dataset_is_an_error_not_a_synthetic_substitute():
    with pytest.raises(FileNotFoundError):
        load_messages(FIXTURES / "missing.csv", 3, seed=1)


def test_a_seeded_mixed_plan_is_deterministic_and_uses_both_sources():
    first = plan_surge(8, "mixed", seed=4, messages_path=FIXTURES / "munro_sample.csv")
    assert first == plan_surge(8, "mixed", seed=4, messages_path=FIXTURES / "munro_sample.csv")
    assert {c.origin.split(":")[0] for c in first} == {"simulated", "recorded"}


def test_the_austin_pattern_compresses_real_gaps_into_the_span():
    assert arrival_offsets(4, 30, "austin", seed=1, austin_path=FIXTURES / "austin_day.json") == [0, 5, 15, 30]
    assert arrival_offsets(3, 20, "even", seed=1) == [0, 10, 20]


def test_injected_callers_are_labeled_and_scripts_continue_after_each_reply():
    queue = HoldQueue(1800, mode="rules")
    callers = [Caller(("I see smoke at 12 Oak Street", "Someone is shouting for help inside"), "simulated: team-written script"),
               Caller(("We need water and food",), "recorded: Munro disaster message 11")]
    start_surge(queue, callers, [0, 0], sleep=lambda seconds: None, workers=2).join(10)
    calls = queue.snapshot()["calls"]
    assert sorted(c["origin"] for c in calls) == sorted(c.origin for c in callers)
    scripted = next(c for c in calls if c["origin"].startswith("simulated"))
    speakers = [t["speaker"] for t in scripted["dialogue"]]
    assert [t["text"] for t in scripted["dialogue"] if t["speaker"] == "caller"] == list(callers[0].lines)
    assert speakers[speakers.index("caller") + 1] == "assistant"


def test_the_api_injects_a_scripted_surge_in_rules_mode(monkeypatch):
    queue = HoldQueue(1800, mode="rules")
    monkeypatch.setattr(api, "QUEUE", queue)
    client = TestClient(api.app)
    response = client.post("/demo/surge", json={"count": 5, "source": "scripts", "pattern": "even", "span_s": 0, "seed": 1})
    assert response.status_code == 200 and response.json()["planned"] == 5
    api.SURGE["thread"].join(10)
    status = client.get("/demo/surge").json()
    assert status["joined"] == 5 and status["errors"] == []
    assert len(queue.snapshot()["calls"]) == 5


def test_a_second_surge_is_refused_while_one_runs_and_reset_stops_it(monkeypatch):
    queue = HoldQueue(1800, mode="rules")
    monkeypatch.setattr(api, "QUEUE", queue)
    client = TestClient(api.app)
    body = {"count": 6, "source": "scripts", "pattern": "even", "span_s": 3, "seed": 1}
    assert client.post("/demo/surge", json=body).status_code == 200
    assert client.post("/demo/surge", json=body).status_code == 409
    assert client.post("/reset", json={"mode": "rules"}).status_code == 200
    api.SURGE["thread"].join(10)
    assert queue.snapshot()["calls"] == []
