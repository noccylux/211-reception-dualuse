import pytest
from fastapi.testclient import TestClient

from dualuse import api
from dualuse.holdqueue import HoldQueue
from dualuse.mapview import MapSync, new_map_app


def map_calls(sync):
    return {c["call_id"]: c for c in sync.mounted.app.state.store.s["calls"].values()}


def test_sync_pushes_caller_words_location_and_tier_label_only_on_change():
    queue = HoldQueue(1800, mode="rules")
    sync = MapSync(queue.snapshot)
    call = queue.add()
    queue.say(call.call_id, "There is a fire at 123 Main St and I am trapped")
    sync.sync_once()
    sync.sync_once()
    pushed = map_calls(sync)[call.call_id]
    assert pushed["revision"] == 1
    assert "123 Main St" in pushed["text"] and pushed["input_mode"] == "host"
    assert pushed["priority_assessment"]["category"] == "IMMEDIATE"
    assert pushed["location"]["source"] == "caller_statement"

    queue.say(call.call_id, "my neighbor is outside")
    sync.sync_once()
    assert map_calls(sync)[call.call_id]["revision"] == 2


def test_injected_demo_callers_are_marked_synthetic_on_the_map():
    queue = HoldQueue(1800, mode="rules")
    sync = MapSync(queue.snapshot)
    queue.add(origin="simulated script")
    sync.sync_once()
    (assessment,) = sync.mounted.app.state.geo.snapshot()["call_assessments"]
    assert assessment["synthetic"] is True


def test_reset_replaces_the_map_so_reused_call_ids_start_fresh():
    queue = HoldQueue(1800, mode="rules")
    sync = MapSync(queue.snapshot)
    queue.say(queue.add().call_id, "fire at 5 Oak Ave")
    sync.sync_once()
    queue.reset("rules")
    sync.reset()
    assert map_calls(sync) == {}
    queue.say(queue.add().call_id, "is the library open")
    sync.sync_once()
    assert [c["revision"] for c in map_calls(sync).values()] == [1]


def test_mounted_map_serves_its_page_and_the_desk_calls():
    # The plugin accepts loopback hosts only.
    client = TestClient(api.app, base_url="http://127.0.0.1")
    assert client.post("/reset", json={"mode": "rules"}).status_code == 200
    created = client.post("/calls", json={"text": "smoke in the hallway at 200 N Spring St"}).json()
    api.MAP.sync_once()
    assert "CrisisFusion" in client.get("/plugins/map/").text
    geo = client.get("/plugins/map/api/geo/state").json()
    assert geo["enabled"] is True
    assert [c["call_id"] for c in geo["calls"]] == [created["call_id"]]
    state = client.get("/state").json()
    assert state["map"]["error"] is None and state["map"]["calls"] == 1


def test_public_map_url_host_is_accepted_for_reads_and_page_mutations(monkeypatch):
    # Behind a tunnel the browser sends the public Host and Origin, and uvicorn takes the scheme from the proxy.
    monkeypatch.setenv("DUALUSE_MAP_URL", "https://demo.example.org/")
    app = new_map_app("la-211")
    public = TestClient(app, base_url="https://demo.example.org")
    assert "CrisisFusion" in public.get("/").text
    token = public.get("/api/geo/state").json()["csrf_token"]
    mutation = public.post("/api/geo/config", json={"enabled": True},
                           headers={"Origin": "https://demo.example.org", "X-CrisisFusion-Geo": token})
    assert mutation.status_code == 200
    assert TestClient(app, base_url="http://127.0.0.1").get("/health").status_code == 200
    assert TestClient(app, base_url="https://other.example.org").get("/health").status_code == 403


def test_map_accepts_only_loopback_without_a_public_map_url(monkeypatch):
    monkeypatch.delenv("DUALUSE_MAP_URL", raising=False)
    app = new_map_app("la-211")
    assert TestClient(app, base_url="http://localhost").get("/health").status_code == 200
    assert TestClient(app, base_url="https://demo.example.org").get("/health").status_code == 403


@pytest.mark.parametrize("value", ["demo.example.org", "ftp://demo.example.org", "https://"])
def test_malformed_public_map_url_fails_loudly(monkeypatch, value):
    monkeypatch.setenv("DUALUSE_MAP_URL", value)
    with pytest.raises(ValueError, match="DUALUSE_MAP_URL"):
        new_map_app("la-211")
