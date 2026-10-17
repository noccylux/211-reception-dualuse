"""Observable reception behavior, persistence, and races during slow inference."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from dualuse.api import app
from dualuse.extract import Classification, Extraction
from dualuse.holdqueue import Conflict, HoldQueue
from dualuse.reception import ReceptionTurn, rules_turn, model_turn
from dualuse.triage import Tier


def result(tier=Tier.PRIORITY, location="12 Oak Street", question="Are you there now?"):
    x = Extraction(situation="Caller reports smoke", need="report smoke", location=location,
                   life_threat_now=tier == Tier.IMMEDIATE, needs_person_soon=tier == Tier.PRIORITY,
                   enough_information=True, evidence=["smoke"], missing=[], language="English",
                   incident_kind="fire", report_only=True)
    return ReceptionTurn(Classification(x, tier, "test"), "safety", question)


def test_multiple_turns_change_urgency_and_keep_the_agent_questions():
    q = HoldQueue(1800)
    first = q.add()
    second = q.add()
    seen = []
    def answer(dialogue, mode):
        seen.append(dialogue)
        return result(Tier.PRIORITY if len(seen) == 1 else Tier.IMMEDIATE)
    q.say(second.call_id, "I see smoke", responder=answer)
    q.say(second.call_id, "Someone is shouting for help", responder=answer)
    assert any(t["speaker"] == "assistant" and t["text"] == "Are you there now?" for t in seen[1])
    assert q.order("tiered")[0].call_id == second.call_id
    assert q.order("fifo")[0].call_id == first.call_id
    assert len([e for e in q.events if e["event"] == "tier_changed"]) == 2


def test_reservation_can_interrupt_inference_without_late_mutations():
    q = HoldQueue(1800)
    call = q.add()
    started, release = threading.Event(), threading.Event()
    def slow(dialogue, mode):
        started.set()
        assert release.wait(5)
        return result(Tier.IMMEDIATE)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(q.say, call.call_id, "smoke", responder=slow)
        assert started.wait(2)
        reserved = q.claim("alice")
        assert reserved.call_id == call.call_id
        assert not reserved.processing
        q.confirm(reserved.transfer_id, True)
        before = q.snapshot()
        release.set()
        with pytest.raises(Conflict, match="late response discarded"):
            future.result(3)
    assert q.snapshot() == before
    assert q.call(call.call_id).tier == Tier.UNKNOWN
    assert q.handoffs[0].transcript == ["smoke"]


def test_concurrent_operators_never_reserve_the_same_call():
    q = HoldQueue(1800)
    q.add()
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(q.claim, ["alice", "bob"]))
    assert sum(r is not None for r in results) == 1
    with pytest.raises(Conflict, match="already"):
        q.claim(next(r.operator_id for r in results if r))


def test_failed_transfer_preserves_arrival_and_blocks_stale_confirmation():
    q = HoldQueue(1800)
    call = q.add()
    arrival = call.arrival
    token = q.claim("alice").transfer_id
    q.confirm(token, False)
    assert call.status == "waiting" and call.arrival == arrival
    with pytest.raises(Conflict):
        q.confirm(token, True)
    assert q.claim("alice").transfer_id != token


def test_sqlite_restart_preserves_calls_reports_history_and_callback_tasks(tmp_path):
    path = tmp_path / "queue.sqlite3"
    q = HoldQueue(1800, db_path=path, mode="rules")
    a, b = q.add(), q.add()
    q.say(a.call_id, "smoke", responder=lambda *_: result(Tier.IMMEDIATE))
    q.say(b.call_id, "smoke", responder=lambda *_: result())
    q.hang_up(b.call_id, disconnected=True)
    q.confirm(q.claim("alice").transfer_id, True)
    restored = HoldQueue(1800, db_path=path)
    assert restored.snapshot() == q.snapshot()
    assert restored.clusters()[0]["count"] == 2
    assert restored.call(b.call_id).callback_status == "pending_review"
    assert restored.add().call_id not in (a.call_id, b.call_id)


def test_restart_recovers_pending_transfer_with_original_arrival(tmp_path):
    path = tmp_path / "queue.sqlite3"
    q = HoldQueue(1800, db_path=path)
    call = q.add()
    token = q.claim("alice").transfer_id
    restored = HoldQueue(1800, db_path=path)
    saved = restored.call(call.call_id)
    assert saved.status == "waiting" and saved.arrival == call.arrival
    assert saved.attention and not saved.transfer_id
    with pytest.raises(Conflict):
        restored.confirm(token, True)


def test_model_failure_is_visible_and_does_not_lose_or_silently_classify_text():
    q = HoldQueue(1800)
    call = q.add()
    def broken(*_):
        raise TimeoutError("test")
    with pytest.raises(TimeoutError):
        q.say(call.call_id, "I need help", responder=broken)
    assert call.transcript == ["I need help"]
    assert call.error and call.attention and not call.processing
    assert call.tier == Tier.UNKNOWN and call.source == "none"
    assert q.claim("alice").call_id == call.call_id


def test_silence_never_downgrades_danger_and_disconnect_creates_review_task():
    q = HoldQueue(1800)
    call = q.add()
    q.say(call.call_id, "smoke", responder=lambda *_: result(Tier.IMMEDIATE))
    q.silence(call.call_id)
    q.silence(call.call_id)
    assert call.tier == Tier.IMMEDIATE and call.status == "waiting" and call.attention
    q.hang_up(call.call_id, disconnected=True)
    assert call.callback_status == "pending_review"
    q.review_callback(call.call_id, "handled_by_operator")
    assert call.callback_status == "handled_by_operator"
    assert call.status == "disconnected"


def test_same_place_report_never_suppresses_new_danger():
    q = HoldQueue(1800)
    a, b = q.add(), q.add()
    q.say(a.call_id, "smoke", responder=lambda *_: result())
    q.say(b.call_id, "smoke", responder=lambda *_: result(Tier.IMMEDIATE))
    assert q.clusters()[0]["count"] == 2
    assert q.order("tiered")[0].call_id == b.call_id
    q.say(b.call_id, "I am outside now", responder=lambda *_: result(Tier.NORMAL))
    assert b.tier == Tier.IMMEDIATE and "Earlier" in b.attention


def test_reset_during_model_turn_cannot_resurrect_old_call():
    q = HoldQueue(1800)
    call = q.add()
    def reset_during_turn(*_):
        q.reset("rules")
        q.add()
        return result()
    with pytest.raises(Conflict):
        q.say(call.call_id, "smoke", responder=reset_during_turn)
    assert [c["call_id"] for c in q.snapshot()["calls"]] != [call.call_id]
    assert len(q.snapshot()["calls"]) == 1


def test_rules_interview_asks_different_questions_and_accepts_wait_request():
    q = HoldQueue(1800, mode="rules")
    call = q.add()
    q.say(call.call_id, "I see smoke")
    assert call.dialogue[-1]["topic"] == "safety"
    q.say(call.call_id, "I am safe at 12 Oak Street")
    assert call.extraction.location == "12 Oak Street"
    assert call.dialogue[-1]["topic"] != "safety"
    q.say(call.call_id, "I'll just wait for a person")
    assert call.dialogue[-1]["topic"] == "wait" and call.status == "waiting"


def test_api_exposes_lifecycle_and_rejects_invalid_operations():
    client = TestClient(app)
    call = client.post("/calls", json={}).json()
    cid = call["call_id"]
    assert "automated reception" in call["dialogue"][0]["text"]
    assert client.post(f"/calls/{cid}/say", json={"text": "  "}).status_code == 422
    assert client.post(f"/calls/{cid}/complete").status_code == 409
    reservation = client.post("/operator/free", json={"operator_id": "alice"}).json()["handoff"]
    assert reservation["status"] == "connecting"
    assert client.post(f"/calls/{cid}/say", json={"text": "hello"}).status_code == 409
    assert client.post(f"/calls/{cid}/disconnect").status_code == 200
    assert client.post(f"/handoffs/{reservation['transfer_id']}/confirm", json={"success": True}).status_code == 409
    assert client.get(f"/calls/{cid}").json()["callback_status"] == "pending_review"


def test_model_output_cannot_use_assistant_words_as_caller_evidence():
    class Block:
        type = "text"
        text = '{"extraction":{"situation":"smoke","need":"","location":null,"life_threat_now":true,"needs_person_soon":false,"enough_information":true,"evidence":["fire"],"missing":[],"language":"English"},"topic":"safety","question":"Are you safe?"}'
    class Response:
        stop_reason = "end_turn"
        content = [Block()]
    class Messages:
        def create(self, **kwargs):
            return Response()
    class Client:
        messages = Messages()
    with pytest.raises(ValueError, match="evidence"):
        model_turn([{"speaker": "assistant", "text": "Is there fire?"}, {"speaker": "caller", "text": "smoke"}], Client())
