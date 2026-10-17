"""Observable reception behavior, persistence, and races during slow inference."""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

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
    def answer(dialogue, mode, facts):
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
    def slow(dialogue, mode, facts):
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
        text = '{"extraction":{"situation":"smoke","need":"","location":null,"life_threat_now":true,"needs_person_soon":false,"enough_information":true,"evidence":["fire"],"missing":[],"language":"English"},"topic":"safety","reply":"Are you safe?","language_code":"en","distress":"worried"}'
    class Response:
        stop_reason = "end_turn"
        content = [Block()]
    class Messages:
        def create(self, **kwargs):
            return Response()
    class Client:
        messages = Messages()
    turn = model_turn([{"speaker": "assistant", "text": "Is there fire?"}, {"speaker": "caller", "text": "smoke"}], client=Client())
    assert turn.classification.extraction.evidence == []
    assert "fire" in turn.review


class FakeClient:
    """Returns one structured interview, shaped like a Messages API response."""

    def __init__(self, payload):
        self.payload = payload
        self.messages = self
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        block = SimpleNamespace(type="text", text=json.dumps(self.payload))
        return SimpleNamespace(stop_reason="end_turn", content=[block])


def interview(evidence, life=True, location=None, reply="Where are you right now?", topic="location",
              language_code="en", distress="worried"):
    extraction = {"situation": "caller reports danger", "need": "", "location": location,
                  "life_threat_now": life, "needs_person_soon": False, "enough_information": True,
                  "evidence": evidence, "missing": [], "language": "English", "incident_kind": "medical",
                  "report_only": False, "safety": "danger" if life else "unknown"}
    return {"extraction": extraction, "topic": topic, "reply": reply, "language_code": language_code,
            "distress": distress}


def caller(*texts):
    return [{"speaker": "caller", "text": text} for text in texts]


def test_evidence_matches_despite_apostrophe_and_case_differences():
    turn = model_turn(caller("my son’s not breathing"), client=FakeClient(interview(["My son's not breathing"])))
    assert turn.classification.tier == Tier.IMMEDIATE
    assert turn.classification.extraction.evidence == ["My son's not breathing"] and not turn.review


def test_unverifiable_quotes_are_dropped_and_flagged_without_losing_the_turn():
    turn = model_turn(caller("he's not breathing please help"), client=FakeClient(interview(["not breathing", "he is turning blue"])))
    assert turn.classification.tier == Tier.IMMEDIATE
    assert turn.classification.extraction.evidence == ["not breathing"]
    assert "he is turning blue" in turn.review


def test_a_quote_may_span_two_caller_turns():
    turn = model_turn(caller("My dad just", "collapsed and is not breathing"), client=FakeClient(interview(["My dad just collapsed"])))
    assert turn.classification.extraction.evidence == ["My dad just collapsed"] and not turn.review


def test_a_location_assembled_from_two_answers_is_kept():
    turn = model_turn(caller("There is a fire in my building", "Oak Street", "number 12"),
                      client=FakeClient(interview(["fire in my building"], location="12 Oak Street")))
    assert turn.classification.extraction.location == "12 Oak Street" and not turn.review


def test_an_invented_location_is_dropped_and_flagged():
    turn = model_turn(caller("There is a fire in my building"), client=FakeClient(interview(["fire in my building"], location="12 Oak Street")))
    assert turn.classification.extraction.location is None
    assert "12 Oak Street" in turn.review
    assert turn.classification.tier == Tier.IMMEDIATE


def test_a_life_threat_without_a_verified_quote_stays_immediate_for_review():
    turn = model_turn(caller("please hurry"), client=FakeClient(interview(["he is dying"])))
    assert turn.classification.tier == Tier.IMMEDIATE
    assert turn.classification.extraction.evidence == [] and turn.review


@pytest.mark.parametrize("reply", ["", "   ", "Where are you? " + "x" * 1300])
def test_an_empty_or_oversized_reply_falls_back_to_a_localized_question(reply):
    turn = model_turn(caller("mi vecino no respira"),
                      client=FakeClient(interview(["no respira"], reply=reply, language_code="es-MX")))
    assert turn.classification.tier == Tier.IMMEDIATE
    assert turn.reply.startswith("¿") and turn.reply.endswith("?") and turn.language == "es-MX"


def test_a_reply_that_sends_the_caller_to_911_is_kept():
    reply = "That sounds frightening. Please call 911 now. Where is he?"
    turn = model_turn(caller("my neighbor is not breathing"), client=FakeClient(interview(["not breathing"], reply=reply)))
    assert turn.reply == reply


def test_the_model_sees_playbooks_real_turns_and_the_desk_facts():
    client = FakeClient(interview(["on fire"]))
    dialogue = [{"speaker": "assistant", "text": "Welcome to the queue.", "topic": "welcome"},
                {"speaker": "caller", "text": "hello"},
                {"speaker": "assistant", "text": "What is happening?", "topic": "situation"},
                {"speaker": "caller", "text": "my house is on fire"}]
    model_turn(dialogue, "Callers ahead of this caller: 3.", client=client)
    request = client.requests[0]
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Calming" in request["system"][0]["text"] and "Life safety" in request["system"][0]["text"]
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user", "system"]
    assert request["messages"][0]["content"] == "hello"
    assert "Callers ahead of this caller: 3." in request["messages"][-1]["content"]


def test_the_agent_reply_is_spoken_and_the_callers_language_is_kept():
    q = HoldQueue(1800)
    call = q.add()
    payload = interview(["没有呼吸"], reply="这听起来很可怕。请立即拨打 911。他在哪里？", language_code="zh-CN", distress="distressed")
    q.say(call.call_id, "我邻居倒在地上，没有呼吸", responder=lambda d, m, f: model_turn(d, f, client=FakeClient(payload)))
    assert call.dialogue[-1]["text"] == payload["reply"]
    assert call.language == "zh" and call.distress == "distressed"
    assert any("拨打" in t["text"] and t["topic"] == "status" for t in call.dialogue)


def test_the_desk_gives_the_model_the_callers_place_and_the_profile_number():
    q = HoldQueue(1800, mode="rules")
    ahead = q.add()
    q.say(ahead.call_id, "My house is on fire")
    call = q.add()
    seen = {}

    def record(dialogue, mode, facts):
        seen["facts"] = facts
        return result(Tier.PRIORITY)

    q.say(call.call_id, "I need help", responder=record)
    assert "911" in seen["facts"] and "Callers ahead of this caller: 1" in seen["facts"]


def test_an_interview_review_note_reaches_the_operator():
    q = HoldQueue(1800)
    call = q.add()
    q.say(call.call_id, "please hurry", responder=lambda d, m, f: model_turn(d, f, client=FakeClient(interview(["he is dying"]))))
    assert call.tier == Tier.IMMEDIATE and "he is dying" in call.attention


def test_an_immediate_report_tells_the_caller_to_call_911():
    q = HoldQueue(1800, mode="rules")
    call = q.add()
    q.say(call.call_id, "My neighbor collapsed on the sidewalk and he is not breathing")
    replies = [t["text"] for t in call.dialogue[1:] if t["speaker"] == "assistant"]
    assert call.tier == Tier.IMMEDIATE and any("911" in reply for reply in replies)


def test_the_welcome_names_the_emergency_number_and_counts_only_callers_ahead():
    q = HoldQueue(1800, mode="rules")
    routine = q.add()
    q.say(routine.call_id, "Where can I renew my CalFresh card")
    newcomer = q.add()
    welcome = newcomer.dialogue[0]["text"]
    assert "911" in welcome
    assert re.search(r"ahead of you: (\d+)", welcome).group(1) == "0"


def slow(turn):
    started, release = threading.Event(), threading.Event()

    def responder(dialogue, mode, facts):
        started.set()
        assert release.wait(5)
        return turn

    return responder, started, release


def routine_call(q):
    call = q.add()
    q.say(call.call_id, "Where do I apply for FEMA assistance?", responder=lambda *_: result(Tier.NORMAL))
    assert call.tier == Tier.NORMAL
    return call


def interrupt(q, call, action):
    responder, started, release = slow(result(Tier.IMMEDIATE))
    with ThreadPoolExecutor() as pool:
        future = pool.submit(q.say, call.call_id, "My neighbor is trapped upstairs", responder=responder)
        assert started.wait(2)
        action()
        release.set()
        with pytest.raises(Conflict):
            future.result(3)


def test_a_reservation_during_a_turn_flags_the_message_and_raises_normal_to_unknown():
    q = HoldQueue(1800)
    call = routine_call(q)
    interrupt(q, call, lambda: q.confirm(q.claim("alice").transfer_id, False))
    assert call.status == "waiting" and call.tier == Tier.UNKNOWN and call.attention


def test_a_hang_up_during_a_turn_creates_a_callback_task():
    q = HoldQueue(1800)
    call = routine_call(q)
    interrupt(q, call, lambda: q.hang_up(call.call_id))
    assert call.callback_status == "pending_review"


def test_a_mode_change_during_a_turn_raises_normal_to_unknown():
    q = HoldQueue(1800)
    call = routine_call(q)

    def switch():
        q.mode = "rules"

    interrupt(q, call, switch)
    assert call.tier == Tier.UNKNOWN and call.attention


def test_a_restart_during_a_turn_raises_normal_to_unknown(tmp_path):
    path = tmp_path / "queue.sqlite3"
    q = HoldQueue(1800, db_path=path, mode="rules")
    call = routine_call(q)
    seen = {}

    def restart_mid_turn(dialogue, mode, facts):
        seen["desk"] = HoldQueue(1800, db_path=path)
        return result(Tier.NORMAL)

    q.say(call.call_id, "My neighbor is trapped upstairs", responder=restart_mid_turn)
    restored = seen["desk"].call(call.call_id)
    assert restored.tier == Tier.UNKNOWN and restored.attention


def test_a_priority_caller_who_hangs_up_gets_a_callback_task():
    q = HoldQueue(1800)
    call = q.add()
    q.say(call.call_id, "my oxygen runs out tonight", responder=lambda *_: result(Tier.PRIORITY))
    q.hang_up(call.call_id)
    assert call.callback_status == "pending_review"


def test_the_china_profile_welcomes_in_mandarin_with_local_numbers():
    q = HoldQueue(1800, mode="rules", profile="cn-12345")
    welcome = q.add().dialogue[0]["text"]
    assert "排队" in welcome and all(number in welcome for number in ("110", "119", "120"))


def test_a_mandarin_caller_hears_the_desk_lines_in_mandarin_with_the_profile_number():
    q = HoldQueue(1800)
    call = q.add()
    turn = result(Tier.IMMEDIATE)
    q.say(call.call_id, "我邻居倒在地上，没有呼吸了", responder=lambda *_: ReceptionTurn(turn.classification, "location", "请问在哪里？", language="zh-CN"))
    emergency = next(t["text"] for t in call.dialogue if "911" in t["text"] and t["topic"] == "status")
    assert call.language == "zh" and "拨打" in emergency


def test_switching_the_profile_keeps_waiting_calls_on_their_own_profile():
    q = HoldQueue(1800)
    early = q.add()
    q.profile = "cn-12345"
    late = q.add()
    assert (early.profile, late.profile) == ("la-211", "cn-12345")
    with pytest.raises(ValueError):
        q.profile = "mars-1"


def test_restart_restores_the_profile_and_each_callers_language(tmp_path):
    path = tmp_path / "queue.sqlite3"
    q = HoldQueue(1800, db_path=path, profile="cn-12345")
    call = q.add()
    q.say(call.call_id, "需要帮助", responder=lambda *_: ReceptionTurn(result(Tier.PRIORITY).classification, "need", "需要什么？", language="zh"))
    restored = HoldQueue(1800, db_path=path)
    assert restored.profile == "cn-12345" and restored.call(call.call_id).language == "zh"


def test_api_switches_profiles_and_rejects_unknown_ones():
    client = TestClient(app)
    state = client.post("/profile", json={"profile": "cn-12345"}).json()
    assert state["profile"] == "cn-12345" and {p["key"] for p in state["profiles"]} == {"la-211", "cn-12345"}
    assert client.post("/profile", json={"profile": "mars-1"}).status_code == 422


def test_offline_mode_flags_a_language_it_cannot_read_and_answers_in_it():
    q = HoldQueue(1800, mode="rules")
    call = q.add()
    q.say(call.call_id, "我们被困在楼里了")
    assert call.tier == Tier.UNKNOWN and "Chinese" in call.attention and "offline" in call.attention
    assert call.language == "zh" and call.dialogue[-1]["text"].endswith("？")
