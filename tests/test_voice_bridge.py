"""The bridge drives the real desk API in-process; Retell is played by the test."""
import hashlib
import hmac
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from dualuse import api, reception
from dualuse.voice_bridge import ACK, DEMO_NOTICE, DESK_DOWN, HANDOFF, STILL_HERE, create_app, verify_signature

SECRET = "ws-secret"
KEY = "retell-key"


@pytest.fixture
def desk():
    return TestClient(api.app)


@pytest.fixture
def bridge():
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://desk")
    app = create_app(client, SECRET, KEY, end_grace_s=0.2, poll_s=0.05)
    with TestClient(app) as test_client:
        yield test_client


def connect(bridge, retell_id="retell-1"):
    ws = bridge.websocket_connect(f"/llm-websocket/{SECRET}/{retell_id}")
    return ws


def opened(ws):
    config = ws.receive_json()
    assert config["response_type"] == "config" and config["config"]["auto_reconnect"] is True
    welcome = ws.receive_json()
    assert welcome["response_type"] == "response" and welcome["response_id"] == 0
    return welcome


def only_call(desk):
    calls = desk.get("/state").json()["calls"]
    assert len(calls) == 1
    return calls[0]


def turn(response_id, *user_texts):
    transcript = []
    for text in user_texts:
        transcript += [{"role": "agent", "content": "..."}, {"role": "user", "content": text}]
    return {"interaction_type": "response_required", "response_id": response_id, "transcript": transcript}


def final_response(ws):
    while True:
        message = ws.receive_json()
        if message["response_type"] == "response" and message["content_complete"]:
            return message


def assistant_texts(call, start):
    return " ".join(t["text"] for t in call["dialogue"][start:] if t["speaker"] == "assistant")


def signed(body: bytes, key=KEY, at_ms=None):
    at = str(at_ms if at_ms is not None else int(time.time() * 1000))
    digest = hmac.new(key.encode(), body + at.encode(), hashlib.sha256).hexdigest()
    return {"X-Retell-Signature": f"v={at},d={digest}", "Content-Type": "application/json"}


def ended(retell_id, reason):
    return json.dumps({"event": "call_ended", "call": {"call_id": retell_id, "disconnection_reason": reason}}).encode()


def wait_for_status(desk, status):
    deadline = time.time() + 3
    while time.time() < deadline:
        if only_call(desk)["status"] == status:
            return
        time.sleep(0.02)
    raise AssertionError(f"desk call never reached {status}: {only_call(desk)['status']}")


def test_a_wrong_path_secret_is_refused(bridge, desk):
    with pytest.raises(WebSocketDisconnect):
        with bridge.websocket_connect("/llm-websocket/wrong/retell-1") as ws:
            ws.receive_json()
    assert desk.get("/state").json()["calls"] == []


def test_answering_a_call_joins_the_desk_queue_and_speaks_its_welcome(bridge, desk):
    with connect(bridge) as ws:
        welcome = opened(ws)
        call = only_call(desk)
        assert call["status"] == "waiting"
        assert welcome["content"] == DEMO_NOTICE + " " + assistant_texts(call, 0)
        assert welcome["content_complete"] is True


def test_a_caller_turn_reaches_the_desk_and_the_desk_reply_is_spoken(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        before = len(only_call(desk)["dialogue"])
        ws.send_json(turn(1, "my house is on fire and my kid is inside"))
        ack = ws.receive_json()
        assert ack == {"response_type": "response", "response_id": 1, "content": ACK, "content_complete": False}
        reply = final_response(ws)
        call = only_call(desk)
        assert call["transcript"] == ["my house is on fire and my kid is inside"]
        assert call["tier"] == "immediate"
        assert reply["response_id"] == 1
        assert reply["content"] == assistant_texts(call, before + 1)
        assert reply["content"]


def test_only_new_caller_turns_are_forwarded(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        ws.send_json(turn(1, "I need food for my family"))
        final_response(ws)
        ws.send_json(turn(2, "I need food for my family", "we are at 12 Oak Street"))
        assert final_response(ws)["response_id"] == 2
        assert only_call(desk)["transcript"] == ["I need food for my family", "we are at 12 Oak Street"]


def test_speech_during_a_running_turn_is_sent_after_it_and_only_the_latest_reply_is_spoken(bridge, desk, monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def slow_turn(dialogue, facts="", client=None):
        started.set()
        assert release.wait(5)
        return reception.rules_turn(dialogue)

    monkeypatch.setattr(reception, "model_turn", slow_turn)
    api.QUEUE.mode = "model"
    with connect(bridge) as ws:
        opened(ws)
        ws.send_json(turn(1, "I see smoke"))
        assert ws.receive_json()["content"] == ACK
        assert started.wait(3)
        ws.send_json(turn(2, "I see smoke", "at 12 Oak Street"))
        assert ws.receive_json() == {"response_type": "response", "response_id": 2, "content": ACK, "content_complete": False}
        release.set()
        reply = final_response(ws)
        call = only_call(desk)
        assert reply["response_id"] == 2
        assert call["transcript"] == ["I see smoke", "at 12 Oak Street"]
        last_caller = max(i for i, t in enumerate(call["dialogue"]) if t["speaker"] == "caller")
        assert reply["content"] == assistant_texts(call, last_caller + 1)
        assert call["error"] == ""


def test_a_desk_reply_identical_to_the_previous_one_is_replaced_by_a_short_notice(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        ws.send_json(turn(1, "I need food. That's all"))
        first = final_response(ws)["content"]
        ws.send_json(turn(2, "I need food. That's all", "nothing else"))
        second = final_response(ws)
        ws.send_json(turn(3, "I need food. That's all", "nothing else", "ok that's all"))
        third = final_response(ws)
        replies = [t["text"] for t in only_call(desk)["dialogue"] if t["speaker"] == "assistant"][-3:]
        assert replies[0] == replies[1] == replies[2] == first  # precondition: the desk repeats itself
        assert second["content"] == third["content"] == STILL_HERE


def test_a_silence_reminder_is_recorded_and_the_check_in_is_spoken(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        ws.send_json({"interaction_type": "reminder_required", "response_id": 1, "transcript": []})
        reply = final_response(ws)
        call = only_call(desk)
        assert call["silence_count"] == 1
        assert reply["response_id"] == 1 and reply["content"] == call["dialogue"][-1]["text"]


@pytest.mark.parametrize("event", [turn(1, "I need food"), {"interaction_type": "reminder_required", "response_id": 1, "transcript": []}])
def test_a_desk_failure_is_spoken_instead_of_leaving_the_caller_in_silence(bridge, desk, event):
    with connect(bridge) as ws:
        opened(ws)
        assert desk.post("/reset", json={"mode": "rules"}).status_code == 200  # the desk call disappears
        ws.send_json(event)
        reply = final_response(ws)
        assert reply["response_id"] == 1 and reply["content"] == DESK_DOWN


def test_ping_pong_is_echoed(bridge):
    with connect(bridge) as ws:
        opened(ws)
        ws.send_json({"interaction_type": "ping_pong", "timestamp": 1703302407333})
        assert ws.receive_json() == {"response_type": "ping_pong", "timestamp": 1703302407333}


def test_an_operator_reservation_interrupts_the_caller_once(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        assert desk.post("/operator/free", json={"operator_id": "operator-1"}).json()["handoff"]
        interrupt = ws.receive_json()
        assert interrupt["response_type"] == "agent_interrupt" and interrupt["content"] == HANDOFF
        ws.send_json(turn(1, "hello?"))
        reply = final_response(ws)
        assert reply["content"] == HANDOFF
        assert only_call(desk)["transcript"] == []


@pytest.mark.parametrize("reason, status", [("user_hangup", "hung_up"), ("error_llm_websocket_open", "disconnected")])
def test_a_signed_call_ended_webhook_ends_the_desk_call(bridge, desk, reason, status):
    with connect(bridge) as ws:
        opened(ws)
        body = ended("retell-1", reason)
        assert bridge.post("/retell-webhook", content=body, headers=signed(body)).status_code == 200
        assert only_call(desk)["status"] == status


def test_an_unsigned_webhook_is_rejected(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
        body = ended("retell-1", "user_hangup")
        assert bridge.post("/retell-webhook", content=body, headers=signed(body, key="other")).status_code == 401
        assert only_call(desk)["status"] == "waiting"


def test_a_closed_socket_without_a_webhook_is_recorded_as_a_disconnect(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
    wait_for_status(desk, "disconnected")


def test_a_reconnect_keeps_the_same_desk_call(bridge, desk):
    with connect(bridge) as ws:
        opened(ws)
    with connect(bridge) as ws:
        assert ws.receive_json()["response_type"] == "config"
        assert ws.receive_json()["content"] == ""
        time.sleep(0.4)
        assert only_call(desk)["status"] == "waiting"


def test_signatures_outside_five_minutes_are_rejected():
    body = b"{}"
    now = int(time.time() * 1000)
    assert verify_signature(body, signed(body, at_ms=now)["X-Retell-Signature"], KEY, now)
    stale = signed(body, at_ms=now - 301_000)["X-Retell-Signature"]
    assert not verify_signature(body, stale, KEY, now)
    assert not verify_signature(body, None, KEY, now)
