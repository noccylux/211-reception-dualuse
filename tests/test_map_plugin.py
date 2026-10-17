import asyncio
import copy
import importlib
import importlib.resources
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from crisisfusion_map import create_app, StateStore


def stamp(delta=0):
    return (datetime.now(timezone.utc)+timedelta(seconds=delta)).isoformat()


def payload(**changes):
    return {"call_id":"call-1","revision":1,"text":"  I am at 123 Main St, Los Angeles.\nPrivate transcript.  ","language":"en","input_mode":"browser_voice",**changes}


def fixture(provider=None,db_path=":memory:",mount=""):
    requests=[]
    def default(request):
        requests.append(request)
        return httpx.Response(200,json={"result":{"addressMatches":[{"matchedAddress":"123 MAIN ST, LOS ANGELES, CA","coordinates":{"x":-118.285,"y":34.02}}]}})
    app=create_app(db_path=db_path,transport=httpx.MockTransport(provider or default))
    app.state.store.upsert_call(payload())
    parent=app
    if mount:
        parent=FastAPI()
        parent.mount(mount,app)
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=parent),base_url="http://127.0.0.1:8812"+mount+"/",headers={"Origin":"http://127.0.0.1:8812","X-CrisisFusion-Geo":app.state.geo.token})
    return app,client,requests


def confirm(**changes):
    return {"call_id":"call-1","revision":1,"label":"123 Main St, Los Angeles","lat":34.02,"lon":-118.285,"confirmed":True,"reviewer":"Tester","note":"Caller read back the address and coordinates were reviewed.",**changes}


def test_independent_import_has_no_server_database_or_peer_import_side_effects(tmp_path):
    code="import sys,crisisfusion_map; assert not any(n in sys.modules for n in ('crisisfusion_map.api','crisisfusion_map.geo','crisisfusion_voice','crisisfusion_scorer','app.core')); assert crisisfusion_map.__version__=='1.0.0'"
    # Vendored, not pip-installed: import it from the repository root.
    root=str(Path(__file__).resolve().parents[1])
    subprocess.run([sys.executable,"-c",code],check=True,cwd=tmp_path,env={**os.environ,"PYTHONPATH":root})
    assert list(tmp_path.iterdir())==[]


def test_full_snapshot_preserves_raw_text_and_idempotent_revision():
    store=StateStore()
    call=payload(timestamp=stamp(),event_id="event-1")
    first=store.upsert_call(call)
    assert first["call"]["text"]==call["text"]
    assert first["call"]["revisions"][0]["text"]==call["text"]
    assert first["call"]["source_timestamp"]==call["timestamp"]
    assert store.upsert_call(copy.deepcopy(call))["duplicate"] is True
    assert len(store.s["calls"]["call-1"]["revisions"])==1
    with pytest.raises(HTTPException) as failure:
        store.upsert_call({**call,"text":"different"})
    assert failure.value.status_code==409
    with pytest.raises(HTTPException):
        store.upsert_call({**call,"revision":2,"text":"changed","event_id":"event-1"})
    store.upsert_call({**call,"revision":2,"text":"changed","event_id":"event-2"})
    replay=store.upsert_call(call)
    assert replay["duplicate"] and replay["event_revision"]==1
    assert replay["call"]["revision"]==2 and replay["call"]["text"]=="changed"
    with pytest.raises(HTTPException):
        store.upsert_call({**call,"event_id":"never-seen"})
    store.close()


def test_voice_sized_event_identifier_is_accepted_and_idempotent():
    store=StateStore()
    event_id="voice-session-"+"s"*24+":"+"i"*200
    assert len(event_id)==239
    event=payload(event_id=event_id)
    assert store.upsert_call(event)["duplicate"] is False
    assert store.upsert_call(event)["duplicate"] is True
    assert store.s["calls"]["call-1"]["event_id"]==event_id
    with pytest.raises(ValueError):
        store.upsert_call(payload(event_id="i"*513))
    store.close()


def test_packaged_plugin_manifest_matches_public_interface():
    resource=importlib.resources.files("crisisfusion_map").joinpath("plugin.json")
    manifest=json.loads(resource.read_text(encoding="utf-8"))
    assert manifest["python_package"]=="crisisfusion_map"
    assert manifest["factory"]=="crisisfusion_map:create_app"


@pytest.mark.parametrize("hosts",["localhost",b"localhost",{"localhost":True}])
def test_allowed_hosts_rejects_non_collections(hosts):
    with pytest.raises(ValueError):
        create_app(allowed_hosts=hosts)


def test_store_identity_survives_restart_and_differs_for_new_database(tmp_path):
    from uuid import UUID
    first=create_app(tmp_path/"one.sqlite3")
    store_id=first.state.geo.snapshot()["store_id"]
    assert str(UUID(store_id))==store_id
    first.state.store.close()
    reopened=create_app(tmp_path/"one.sqlite3")
    second=create_app(tmp_path/"two.sqlite3")
    assert reopened.state.geo.snapshot()["store_id"]==store_id
    assert second.state.geo.snapshot()["store_id"]!=store_id
    reopened.state.store.close();second.state.store.close()


@pytest.mark.parametrize("changes",[{"revision":True},{"revision":0},{"revision":1.5},{"call_id":"../bad"},{"timestamp":"yesterday"},{"timestamp":"2026-01-01T12:00:00"},{"location":{"lat":34}},{"location":{"lat":True,"lon":0}},{"location":{"label":"x","extra":"bad"}},{"priority_assessment":{"category":"P1","score":float("nan")}},{"text":None}])
def test_bad_host_payload_rejected(changes):
    store=StateStore()
    with pytest.raises(ValueError):
        store.upsert_call(payload(**changes))
    assert not store.s["calls"]
    store.close()


def test_persistence_retains_call_and_confirmation_but_not_activity(tmp_path):
    path=tmp_path/"map.sqlite3"
    app=create_app(path)
    app.state.store.upsert_call(payload())
    app.state.store.set_active_call("call-1")
    app.state.geo.configure({"enabled":True})
    app.state.geo.confirm_address(confirm())
    app.state.store.close()
    restored=create_app(path)
    state=restored.state.geo.snapshot()
    assert state["enabled"]
    assert state["calls"][0]["active"] is False
    assert state["call_assessments"][0]["address"]["status"]=="HUMAN_CONFIRMED"
    restored.state.store.close()


@pytest.mark.parametrize("mount",["","/plugins/map"])
def test_standalone_and_mount_prefix_ui_assets_and_mutation(mount):
    async def run():
        app,client,requests=fixture(mount=mount)
        async with client:
            page=await client.get("")
            assert page.status_code==200
            assert 'href="static/' in page.text
            js=await client.get("static/geo.js")
            assert js.status_code==200
            assert "new URL('api/geo/'+path,document.baseURI)" in js.text
            assert "crisisFusionVoiceCall" not in js.text and "window.showScore" not in js.text
            assert (await client.get("static/vendor/leaflet/leaflet.js")).status_code==200
            assert (await client.get("static/vendor/leaflet/LICENSE")).status_code==200
            state=(await client.get("api/geo/state")).json()
            assert state["enabled"] is False and not requests
            assert (await client.post("api/geo/config",json={"enabled":True})).status_code==200
            result=await client.post("api/geo/calls",json=payload(revision=2,text="Address changed to 456 Sunset Blvd, Los Angeles."))
            assert result.status_code==200,result.text
            assert result.json()["calls"][0]["revision"]==2
            assert not requests
        app.state.store.close()
    asyncio.run(run())


def test_bad_host_origin_and_token_rejected():
    async def run():
        app,client,_=fixture()
        async with client:
            assert (await client.get("health",headers={"Host":"evil.example"})).status_code==403
            for headers in ({"Origin":"https://evil.example"},{"X-CrisisFusion-Geo":"wrong"},{"Origin":"http://127.0.0.1:8812/plugins/map"}):
                assert (await client.post("api/geo/config",json={"enabled":True},headers=headers)).status_code==403
            assert (await client.post("api/geo/config",json={"enabled":True},headers={"X-CrisisFusion-Geo":b"invalid-\xff"})).status_code==403
            client.headers.pop("Origin")
            assert (await client.post("api/geo/config",json={"enabled":True})).status_code==403
        app.state.store.close()
    asyncio.run(run())


def test_chunked_body_limit_enforced_without_content_length():
    async def run():
        app,client,_=fixture()
        async def body():
            for _ in range(11):
                yield b"x"*100000
        async with client:
            result=await client.post("api/geo/calls",content=body(),headers={"Content-Type":"application/json"})
            assert result.status_code==413
        app.state.store.close()
    asyncio.run(run())


def test_explicit_hosts_for_mounted_authenticated_host():
    async def run():
        app=create_app(allowed_hosts=["console.example"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://console.example",headers={"Origin":"https://console.example","X-CrisisFusion-Geo":app.state.geo.token}) as client:
            assert (await client.get("health")).status_code==200
            assert (await client.post("api/geo/config",json={"enabled":True})).status_code==200
        app.state.store.close()
    asyncio.run(run())


def test_gps_requires_active_host_call_and_explicit_fresh_consent():
    async def run():
        app,client,_=fixture()
        gps={"call_id":"call-1","lat":34.02,"lon":-118.285,"accuracy_m":20,"captured_at":stamp(),"consent":True}
        async with client:
            await client.post("api/geo/config",json={"enabled":True})
            assert (await client.post("api/geo/caller-location",json=gps)).status_code==409
            assert (await client.post("api/geo/calls/call-1/active",json={"active":True})).status_code==200
            assert (await client.post("api/geo/caller-location",json={**gps,"consent":False})).status_code==400
            assert (await client.post("api/geo/caller-location",json={**gps,"captured_at":stamp(-600)})).status_code==400
            result=await client.post("api/geo/caller-location",json=gps)
            assert result.status_code==200
            state=result.json()
            assert len(state["caller_locations"])==1
            assert state["call_assessments"][0]["address"]["coordinates"] is None
            assert "lat" not in json.dumps(app.state.store.s["audit"])
            await client.post("api/geo/calls/call-1/active",json={"active":False})
            assert (await client.post("api/geo/caller-location",json=gps)).status_code==409
            deleted=await client.delete("api/geo/caller-location/call-1")
            assert deleted.json()["caller_locations"]==[]
        app.state.store.close()
    asyncio.run(run())


def test_geocoder_consent_privacy_and_confirmed_revision_invalidation():
    async def run():
        app,client,requests=fixture()
        async with client:
            await client.post("api/geo/config",json={"enabled":True})
            query={"call_id":"call-1","revision":1,"address":"123 Main St, Los Angeles"}
            assert (await client.post("api/geo/address/geocode",json=query)).status_code==400
            assert not requests
            result=await client.post("api/geo/address/geocode",json={**query,"consent":True})
            assert result.status_code==200,result.text
            assert requests[0].url.host=="geocoding.geo.census.gov"
            assert dict(requests[0].url.params)=={"address":query["address"],"benchmark":"Public_AR_Current","format":"json"}
            assert "Private transcript" not in str(requests[0].url)
            address=result.json()["call_assessments"][0]["address"]
            assert address["status"]=="LOCATED_UNCONFIRMED"
            assert address["measured_accuracy"]["value"] is None
            result=await client.post("api/geo/address/confirm",json=confirm())
            assert result.json()["call_assessments"][0]["address"]["status"]=="HUMAN_CONFIRMED"
            await client.post("api/geo/calls",json=payload(revision=2,text="The event is at 456 Sunset Blvd, Los Angeles."))
            assert (await client.post("api/geo/address/confirm",json=confirm())).status_code==409
            state=(await client.get("api/geo/state")).json()
            assert state["call_assessments"][0]["address"]["status"]!="HUMAN_CONFIRMED"
            assert state["call_assessments"][0]["exposure"]["level"]=="UNKNOWN"
        app.state.store.close()
    asyncio.run(run())


@pytest.mark.parametrize("change",["revision","delete","disable","confirm"])
def test_late_geocoder_cannot_restore_stale_address(change):
    async def run():
        started=asyncio.Event();release=asyncio.Event()
        async def provider(request):
            started.set();await release.wait()
            return httpx.Response(200,json={"result":{"addressMatches":[{"matchedAddress":"123 MAIN ST","coordinates":{"x":-118.285,"y":34.02}}]}})
        app,client,_=fixture(provider)
        app.state.geo.configure({"enabled":True})
        async with client:
            pending=asyncio.create_task(client.post("api/geo/address/geocode",json={"call_id":"call-1","revision":1,"address":"123 Main St, Los Angeles","consent":True}))
            await asyncio.wait_for(started.wait(),2)
            if change=="revision":
                app.state.store.upsert_call(payload(revision=2,text="456 Sunset Blvd, Los Angeles"))
            elif change=="delete":
                await client.delete("api/geo/address/call-1")
            elif change=="confirm":
                await client.post("api/geo/address/confirm",json=confirm())
            else:
                await client.post("api/geo/config",json={"enabled":False})
                await client.post("api/geo/config",json={"enabled":True})
            release.set()
            result=await pending
            assert result.status_code==409,result.text
            records=app.state.geo.data()["address_records"]
            assert records.get("call-1",{}).get("source")!="census_geocoder_interpolated"
        app.state.store.close()
    asyncio.run(run())


def test_official_provider_feed_and_manual_zone_are_separate_and_scoring_unchanged():
    async def run():
        def provider(request):
            if request.url.host=="api.weather.gov":
                props={"id":"urn:test","@id":"https://api.weather.gov/alerts/urn:test","status":"Actual","messageType":"Alert","event":"Red Flag Warning","headline":"Mock weather only","expires":stamp(3600),"effective":stamp(-10),"sent":stamp(-10),"severity":"Severe","certainty":"Likely","urgency":"Immediate","areaDesc":"Mock area"}
                return httpx.Response(200,json={"type":"FeatureCollection","features":[{"type":"Feature","id":props["@id"],"properties":props,"geometry":{"type":"Polygon","coordinates":[[[-118.4,33.9],[-118.1,33.9],[-118.1,34.2],[-118.4,34.2],[-118.4,33.9]]]}}]})
            assert request.url.host=="earthquake.usgs.gov"
            return httpx.Response(200,json={"type":"FeatureCollection","features":[]})
        app,client,_=fixture(provider)
        app.state.store.upsert_call(payload(revision=2,priority_assessment={"category":"P1","score":82}))
        before=copy.deepcopy(app.state.store.s["calls"])
        async with client:
            await client.post("api/geo/config",json={"enabled":True})
            await client.post("api/geo/address/confirm",json=confirm(revision=2))
            state=(await client.post("api/geo/refresh",json={})).json()
            assessment=state["call_assessments"][0]
            assert assessment["exposure"]["level"]=="HIGH"
            assert assessment["exposure"]["matches"][0]["hazard_type"]=="FIRE_WEATHER"
            assert assessment["call_priority"]["score"]==82
            report={"call_id":"call-1","lat":34.02,"lon":-118.285,"label":"Operator shooting perimeter","note":"Operator-defined circle with reviewed evidence","reviewed":True,"source_url":"https://example.org/evidence","hazard_type":"shooting","zone_radius_m":200,"zone_level":"CRITICAL","valid_minutes":5}
            state=(await client.post("api/geo/reports",json=report)).json()
            assert state["reports"][0]["zone_source"]=="local_operator_defined_unverified"
            assert app.state.store.s["calls"]==before
        app.state.store.close()
    asyncio.run(run())
