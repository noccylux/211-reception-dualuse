"""The incident map follows the active line profile: its boundary, geocoder and feeds."""
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from crisisfusion_map import create_app
from dualuse import api
from dualuse.holdqueue import HoldQueue
from dualuse.mapview import MapSync
from dualuse.profiles import PROFILES

DATA = Path(__file__).resolve().parents[1] / "crisisfusion_map" / "data"
PEOPLES_SQUARE = {"label": "People's Square, Huangpu, Shanghai", "lat": 31.2304, "lon": 121.4737}
BEIJING = {"label": "Tiananmen, Dongcheng, Beijing", "lat": 39.9042, "lon": 116.4074}
LA_CITY_HALL = {"label": "200 N Spring St, Los Angeles", "lat": 34.0537, "lon": -118.2427}


def assessments(sync):
    return {a["call_id"]: a for a in sync.mounted.app.state.geo.snapshot()["call_assessments"]}


def test_each_profile_names_its_own_recorded_boundary_geocoder_and_feeds():
    la, cn = PROFILES["la-211"].map_area, PROFILES["cn-12345"].map_area
    # Census matches only a US number, street and city; callers name landmarks and streets, so both lines use
    # OpenStreetMap. NWS covers US weather only.
    assert (la.boundary, la.geocoder, la.feeds) == ("la_county.geojson", "nominatim", ("nws", "usgs"))
    assert (cn.boundary, cn.geocoder, cn.feeds) == ("shanghai.geojson", "nominatim", ("usgs",))
    sources = json.loads((DATA / "geo_sources.json").read_text(encoding="utf-8"))
    assert (DATA / la.boundary).is_file()
    digest = hashlib.sha256((DATA / cn.boundary).read_bytes()).hexdigest()
    assert digest == sources["shanghai"]["sha256"]
    assert sources["shanghai"]["boundary_source"].startswith("https://www.openstreetmap.org/relation/")
    assert sources["shanghai"]["downloaded_at_utc"]


def test_profile_switch_replaces_the_map_scope_and_draws_only_that_lines_calls():
    queue = HoldQueue(1800, mode="rules")
    sync = MapSync(queue.snapshot)
    queue.add(origin="replay", location=LA_CITY_HALL)
    sync.sync_once()
    assert sync.mounted.app.state.geo.snapshot()["scope"]["name"] == "Los Angeles County"
    queue.profile = "cn-12345"
    shanghai = queue.add(origin="replay", location=PEOPLES_SQUARE)
    sync.sync_once()
    scope = sync.mounted.app.state.geo.snapshot()["scope"]
    assert scope["name"] == "Shanghai Municipality (example city)" and scope["geocoder"]["id"] == "nominatim"
    assert [p["id"] for p in sync.mounted.app.state.geo.snapshot()["providers"]] == ["usgs"]
    assert list(assessments(sync)) == [shanghai.call_id]
    assert sync.status["other_lines"] == 1 and sync.status["area"] == "Shanghai Municipality (example city)"


def test_a_call_located_outside_the_active_area_is_flagged_for_transfer():
    queue = HoldQueue(1800, mode="rules", profile="cn-12345")
    sync = MapSync(queue.snapshot)
    inside = queue.add(origin="replay", location=PEOPLES_SQUARE)
    outside = queue.add(origin="replay", location=BEIJING)
    spoken = queue.add()  # no coordinates: no area judgement, never a guessed point
    sync.sync_once()
    found = assessments(sync)
    assert found[inside.call_id]["service_area"] == "inside"
    assert found[outside.call_id]["service_area"] == "outside"
    assert found[spoken.call_id]["service_area"] is None


def test_test_data_coordinates_land_on_the_map_directly_and_stay_labeled_replay():
    client = TestClient(api.app, base_url="http://127.0.0.1")
    client.post("/reset", json={"mode": "rules"})
    client.post("/profile", json={"profile": "la-211"})
    created = client.post("/calls", json={"text": "smoke in the lobby", "origin": "replay", "location": LA_CITY_HALL})
    assert created.status_code == 201, created.text
    assert created.json()["origin"] == "replay" and created.json()["location"] == LA_CITY_HALL
    api.MAP.sync_once()
    (found,) = client.get("/plugins/map/api/geo/state").json()["call_assessments"]
    point = found["address"]["coordinates"]
    assert (point["lat"], point["lon"], point["source"]) == (34.0537, -118.2427, "test_data_replay")
    assert found["synthetic"] is True and found["service_area"] == "inside"


def test_only_replayed_calls_may_carry_coordinates():
    client = TestClient(api.app, base_url="http://127.0.0.1")
    assert client.post("/calls", json={"text": "hello", "location": LA_CITY_HALL}).status_code == 422
    bad = {**LA_CITY_HALL, "lat": 123}
    assert client.post("/calls", json={"origin": "replay", "location": bad}).status_code == 422


def test_china_area_geocodes_through_nominatim_not_census():
    requests = []

    def nominatim(request):
        requests.append(request)
        return httpx.Response(200, json=[{"lat": "31.2304", "lon": "121.4737", "display_name": "人民广场, 黄浦区, 上海市",
                                          "osm_type": "node"}])

    async def run():
        app = create_app(transport=httpx.MockTransport(nominatim), area=PROFILES["cn-12345"].map_area.spec())
        app.state.store.upsert_call({"call_id": "call-1", "revision": 1, "text": "上海市黄浦区人民大道200号着火了", "language": "zh"})
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8812/",
                                   headers={"Origin": "http://127.0.0.1:8812", "X-CrisisFusion-Geo": app.state.geo.token})
        async with client:
            await client.post("api/geo/config", json={"enabled": True})
            result = await client.post("api/geo/address/geocode", json={"call_id": "call-1", "revision": 1,
                                                                        "address": "上海市黄浦区人民大道200号", "consent": True})
            assert result.status_code == 200, result.text
        (match,) = result.json()["geocode_result"]["matches"]
        assert match["source"] == "nominatim_osm" and match["inside_county"] is True
        assert requests[0].url.host == "nominatim.openstreetmap.org"
        assert "着火" not in str(requests[0].url)  # only the address, never the call text
        app.state.store.close()

    asyncio.run(run())
