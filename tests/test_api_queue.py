import json

import pytest
from fastapi.testclient import TestClient

from dualuse import evaluation
from dualuse.api import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(app)
    assert client.post("/reset", json={"mode": "rules"}).status_code == 200
    return client


def test_new_call_waits_as_unknown_and_shows_its_positions(client):
    created = client.post("/calls", json={}).json()
    assert created["tier"] == "unknown" and created["transcript"] == []
    state = client.get("/state").json()
    assert state["mode"] == "rules" and state["active_policy"] == "tiered"
    assert [call["call_id"] for call in state["waiting"]] == [created["call_id"]]
    assert state["waiting"][0]["fifo_position"] == 0 and state["waiting"][0]["tiered_position"] == 0


def test_a_new_call_is_labeled_live_unless_it_says_phone(client):
    assert client.post("/calls", json={}).json()["origin"] == "live"
    assert client.post("/calls", json={"origin": "phone"}).json()["origin"] == "phone"
    assert [call["origin"] for call in client.get("/state").json()["waiting"]] == ["live", "phone"]


@pytest.mark.parametrize("origin", ["simulated: team-written script", "PHONE", "", None])
def test_a_new_call_rejects_any_other_origin_label(client, origin):
    assert client.post("/calls", json={"origin": origin}).status_code == 422
    assert client.get("/state").json()["waiting"] == []


def test_saying_something_life_threatening_moves_the_call_to_the_tiered_head(client):
    first = client.post("/calls", json={"text": "is the 210 freeway open towards Pasadena"}).json()
    second = client.post("/calls", json={}).json()
    said = client.post(f"/calls/{second['call_id']}/say", json={"text": "my house is on fire and my kid is inside"}).json()
    assert said["tier"] == "immediate" and said["source"] == "rules"
    assert "fire" in " ".join(said["extraction"]["evidence"])
    waiting = {call["call_id"]: call for call in client.get("/state").json()["waiting"]}
    assert waiting[first["call_id"]]["fifo_position"] == 0 and waiting[first["call_id"]]["tiered_position"] == 1
    assert waiting[second["call_id"]]["fifo_position"] == 1 and waiting[second["call_id"]]["tiered_position"] == 0


def test_operator_free_reserves_then_confirms_the_head_with_a_summary(client):
    client.post("/calls", json={"text": "is the 210 freeway open towards Pasadena"})
    urgent = client.post("/calls", json={"text": "my house is on fire and my kid is inside"}).json()
    handoff = client.post("/operator/free").json()["handoff"]
    assert handoff["call_id"] == urgent["call_id"] and handoff["tier"] == "immediate"
    assert "IMMEDIATE" in handoff["summary"] and "on fire" in handoff["summary"]
    assert handoff["status"] == "connecting"
    assert client.get("/state").json()["handoffs"] == []
    confirmed = client.post(f"/handoffs/{handoff['transfer_id']}/confirm", json={"success": True})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "handed_off"
    state = client.get("/state").json()
    assert len(state["waiting"]) == 1 and state["handoffs"][0]["call_id"] == urgent["call_id"]


def test_the_operator_holding_a_typed_call_replies_through_the_desk(client):
    call = client.post("/calls", json={"text": "is the 210 freeway open towards Pasadena"}).json()
    handoff = client.post("/operator/free", json={"operator_id": "operator-2"}).json()["handoff"]
    path = f"/calls/{call['call_id']}/operator-message"
    assert client.post(path, json={"operator_id": "operator-2", "text": "Hello"}).status_code == 409  # not yet taken over
    client.post(f"/handoffs/{handoff['transfer_id']}/confirm", json={"success": True})
    assert client.post(path, json={"operator_id": "operator-1", "text": "Hello"}).status_code == 409
    assert client.post(path, json={"operator_id": "operator-2", "text": "   "}).status_code == 422
    replied = client.post(path, json={"operator_id": "operator-2", "text": "This is the 211 operator."})
    assert replied.status_code == 200
    assert {k: replied.json()["dialogue"][-1][k] for k in ("speaker", "text")} == {"speaker": "operator", "text": "This is the 211 operator."}
    assert client.post("/calls/no-such-call/operator-message", json={"operator_id": "operator-2", "text": "Hi"}).status_code == 404


def test_operator_free_with_an_empty_queue_hands_off_nobody(client):
    assert client.post("/operator/free").json() == {"handoff": None}


def test_caller_hangs_up_and_is_recorded_as_their_choice(client):
    call = client.post("/calls", json={}).json()
    departure = client.post(f"/calls/{call['call_id']}/hangup").json()
    assert departure["reason"] == "caller_hung_up"
    state = client.get("/state").json()
    assert state["waiting"] == [] and state["departed"][0]["call_id"] == call["call_id"]


def test_fifo_mode_is_the_degraded_order_and_model_mode_needs_a_key(client):
    assert client.post("/mode", json={"mode": "fifo"}).json()["active_policy"] == "fifo"
    assert client.post("/mode", json={"mode": "model"}).status_code == 409
    assert client.post("/mode", json={"mode": "oracle"}).status_code == 422


def test_fifo_mode_records_what_the_caller_said_without_classifying(client):
    client.post("/mode", json={"mode": "fifo"})
    call = client.post("/calls", json={"text": "my house is on fire and my kid is inside"}).json()
    assert call["tier"] == "unknown" and call["source"] == "none" and call["transcript"] == ["my house is on fire and my kid is inside"]


def test_unknown_call_is_a_404(client):
    assert client.post("/calls/nope/say", json={"text": "hello"}).status_code == 404
    assert client.post("/calls/nope/hangup").status_code == 404


def test_state_lists_clusters_and_invariants(client):
    for text in ["smoke in Altadena near Lake Avenue", "smell smoke in Altadena too", "freeway question from Pasadena"]:
        client.post("/calls", json={"text": text})
    state = client.get("/state").json()
    assert isinstance(state["clusters"], list)
    assert any("never ends a call" in line for line in state["invariants"])
    assert state["model_available"] is False


def test_simulate_runs_the_three_policies_on_a_labeled_scenario(client):
    body = {
        "duration_s": 3600,
        "arrivals_per_hour": 60,
        "operators": 3,
        "tier_mix": {"immediate": 0.05, "priority": 0.25, "normal": 0.7},
        "mean_service_s": 300,
        "mean_patience_s": 900,
        "decision_delay_s": 45,
        "miss_rate": 0.05,
        "false_alarm_rate": 0.1,
        "seed": 3,
        "max_normal_wait_s": 1800,
    }
    result = client.post("/simulate", json=body).json()
    assert result["label"] == "simulated"
    assert set(result["results"]) == {"fifo", "rules", "model"}
    assert result["results"]["fifo"]["by_true_tier"]["immediate"]["calls"] >= 0
    assert result["spec"]["operators"] == 3


SCENARIO = {
    "duration_s": 3600, "arrivals_per_hour": 60, "operators": 3,
    "tier_mix": {"immediate": 0.05, "priority": 0.25, "normal": 0.7},
    "mean_service_s": 300, "mean_patience_s": 900, "decision_delay_s": 45,
    "miss_rate": 0.05, "false_alarm_rate": 0.1, "seed": 3, "max_normal_wait_s": 1800,
}


def test_simulate_adds_policies_at_rates_measured_on_recorded_messages(client, evaluation_file):
    evaluation_file()
    result = client.post("/simulate", json={**SCENARIO, "measured_text": "english"}).json()
    assert set(result["results"]) == {"fifo", "rules", "model", "rules_measured", "model_measured"}
    # The fixture's one needs-a-person message (also the subset) was NORMAL, its routine message PRIORITY.
    assert result["measured"]["rates"]["model"]["assigned_mix"]["immediate"]["normal"] == 1.0
    assert result["results"]["model_measured"]["assigned_share"]["normal"] == pytest.approx(
        sum(result["results"]["fifo"]["by_true_tier"][t]["calls"] for t in ("immediate", "priority"))
        / sum(result["results"]["fifo"]["by_true_tier"][t]["calls"] for t in ("immediate", "priority", "normal")))
    assert result["measured"]["label"] == "Recorded SMS (test fixture), proxy labels"
    original = client.post("/simulate", json={**SCENARIO, "measured_text": "original"}).json()
    assert original["results"]["rules_measured"]["assigned_share"]["unknown"] == 1.0  # every original was UNKNOWN
    assert original["results"]["rules_measured"]["misses"] == 0


def test_simulate_without_an_evaluation_runs_the_assumed_policies_only(client):
    result = client.post("/simulate", json=SCENARIO).json()
    assert set(result["results"]) == {"fifo", "rules", "model"} and result["measured"] is None


def test_the_evaluation_endpoint_serves_summaries_without_message_rows(client, evaluation_file):
    assert client.get("/evaluation").json() == {"available": False}
    evaluation_file()
    body = client.get("/evaluation").json()
    assert body["available"] and "rows" not in body
    assert body["summaries"]["fifo"]["english"]["by_construction"]
    assert body["assigned_mix"]["original"]["model"]["normal"] == {"immediate": 0.0, "priority": 0.0, "unknown": 1.0, "normal": 0.0}


def test_a_malformed_evaluation_file_fails_loudly(client, evaluation_file):
    evaluation_file().write_text("{not json", encoding="utf-8")
    response = client.post("/simulate", json=SCENARIO)
    assert response.status_code == 500 and "malformed" in response.text
    evaluation.RESULTS.write_text(json.dumps({"label": "x", "generated_at": "x", "summaries": {}}), encoding="utf-8")
    response = client.post("/simulate", json=SCENARIO)
    assert response.status_code == 500 and "lacks measured rates" in response.text


def test_simulate_rejects_a_tier_mix_that_does_not_sum_to_one(client):
    body = {
        "duration_s": 3600,
        "arrivals_per_hour": 60,
        "operators": 3,
        "tier_mix": {"immediate": 0.5, "priority": 0.5, "normal": 0.5},
        "mean_service_s": 300,
        "mean_patience_s": 900,
        "decision_delay_s": 45,
        "miss_rate": 0.05,
        "false_alarm_rate": 0.1,
        "seed": 3,
        "max_normal_wait_s": 1800,
    }
    response = client.post("/simulate", json=body)
    assert response.status_code == 422 and "tier_mix" in response.text


def test_samples_are_labeled_by_origin(client):
    samples = client.get("/samples").json()
    assert samples and all(sample["text"] and sample["origin"] for sample in samples)
