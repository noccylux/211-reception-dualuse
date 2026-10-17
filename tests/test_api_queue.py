import pytest
from fastapi.testclient import TestClient

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
