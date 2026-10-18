"""Automatic lookup of the place a caller stated: inside the service area, unverified, never over a person's choice."""
import asyncio

import httpx
import pytest

from crisisfusion_map import create_app
from crisisfusion_map.geocoding import Nominatim
from dualuse.profiles import PROFILES

LA = PROFILES["la-211"].map_area.spec()


@pytest.fixture(autouse=True)
def no_rate_limit_wait(monkeypatch):
    # The one-request-a-second wait is not under test here; it would only slow the suite.
    monkeypatch.setattr(Nominatim, "MIN_INTERVAL_S", 0)


def place(name, lat, lon, box=None):
    # Nominatim pads a single address node by about 5 m; streets and areas carry their real extent.
    box = box or [lat - 0.00005, lat + 0.00005, lon - 0.00005, lon + 0.00005]
    return {"display_name": name, "lat": str(lat), "lon": str(lon), "osm_type": "node", "boundingbox": [str(v) for v in box]}


TORRANCE_MAPLE = place("450, Maple Avenue, Torrance, Los Angeles County, California", 33.84403, -118.34001)
BREA_MAPLE = place("450, Maple Avenue, Brea, Orange County, California", 33.91008, -117.89233)  # in the search box, outside the county
USC = place("University of Southern California, West Jefferson Boulevard, Los Angeles", 34.02187, -118.28586,
            [34.0175, 34.0255, -118.2915, -118.2805])
OAK_PICO = place("Oak Street, Pico-Union, Los Angeles", 34.0345, -118.2793)
OAK_WEST_HOLLYWOOD = place("Oak Street, Los Angeles, 90069", 34.1041, -118.3755)


def geocoder(*responses):
    """A mock Nominatim answering each request with the next response; it records every request."""
    requests, answers = [], list(responses)

    def handler(request):
        requests.append(request)
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        return answer if isinstance(answer, httpx.Response) else httpx.Response(200, json=answer)
    return handler, requests


def map_app(handler):
    app = create_app(transport=httpx.MockTransport(handler), area=LA)
    app.state.geo.configure({"enabled": True})
    return app


def stated(app, label, revision=1, call_id="call-1", text="Private words: there is smoke next door"):
    app.state.store.upsert_call({"call_id": call_id, "revision": revision, "text": text, "language": "en",
                                 "location": {"label": label, "source": "caller_statement"}})


def locate(app):
    asyncio.run(app.state.geo.auto_locate_once())


def assessment(app, call_id="call-1"):
    return {a["call_id"]: a for a in app.state.geo.snapshot()["call_assessments"]}[call_id]


def test_stated_place_reaches_the_map_as_an_unverified_point_inside_the_area():
    handler, requests = geocoder([TORRANCE_MAPLE, BREA_MAPLE])
    app = map_app(handler)
    stated(app, "450 Maple Ave")
    locate(app)
    found = assessment(app)
    address = found["address"]
    assert address["status"] == "LOCATED_UNCONFIRMED" and address["verification"]["confirmed"] is False
    point = address["coordinates"]
    assert (point["lat"], point["lon"], point["source"]) == (33.84403, -118.34001, "automatic_lookup")
    assert point["accuracy_m"] is None  # an address point's uncertainty is unknown, not 5 m
    assert found["service_area"] == "inside"
    (request,) = requests
    assert request.url.host == "nominatim.openstreetmap.org"
    params = dict(request.url.params)
    assert params["q"] == "450 Maple Ave" and params["bounded"] == "1" and params["viewbox"]
    assert "Private" not in str(request.url)  # only the stated place leaves, never the call text
    app.state.store.close()


def test_each_place_is_sent_once_and_a_new_revision_keeps_its_point():
    handler, requests = geocoder([USC])
    app = map_app(handler)
    stated(app, "USC")
    stated(app, "USC", call_id="call-2", text="I am at USC and hungry")
    locate(app)
    stated(app, "USC", revision=2, text="Private words: there is smoke next door, and I am at USC")
    app.state.geo.apply_auto_lookups()  # the desk's map sync does this after each push
    locate(app)
    address = assessment(app)["address"]
    assert address["status"] == "LOCATED_UNCONFIRMED" and "stale_confirmation" not in address["flags"]
    assert address["coordinates"]["revision"] == 2
    # A campus or district is drawn with its extent: the point is only its centre.
    assert address["coordinates"]["accuracy_m"] > 400
    assert assessment(app, "call-2")["address"]["coordinates"]["source"] == "automatic_lookup"
    assert len(requests) == 1
    app.state.store.close()


def test_several_places_stay_candidates_for_a_person_and_none_is_drawn():
    handler, _ = geocoder([OAK_PICO, OAK_WEST_HOLLYWOOD])
    app = map_app(handler)
    stated(app, "12 Oak Street")
    locate(app)
    address = assessment(app)["address"]
    assert address["status"] == "ADDRESS_CANDIDATE" and address["coordinates"] is None
    candidates = app.state.geo.snapshot()["address_geocodes"]["call-1"]
    assert candidates["automatic"] is True and candidates["status"] == "multiple_matches"
    assert [m["label"] for m in candidates["matches"]] == [OAK_PICO["display_name"], OAK_WEST_HOLLYWOOD["display_name"]]
    app.state.store.close()


def test_a_building_and_its_street_address_count_as_one_place():
    building = place("Olin Hall of Engineering, 3650, McClintock Avenue, Los Angeles", 34.02069, -118.28951)
    handler, _ = geocoder([building, place("3650, McClintock Avenue, Los Angeles", 34.02104, -118.28953)])
    app = map_app(handler)
    stated(app, "3650 McClintock Ave")
    locate(app)
    assert assessment(app)["address"]["display_label"] == building["display_name"]
    app.state.store.close()


def test_a_wordy_place_falls_back_to_the_place_recognized_inside_it():
    handler, requests = geocoder([], [USC])
    app = map_app(handler)
    stated(app, "Gateway apartment near USC, Los Angeles, ZIP 90007")
    locate(app)
    assert [dict(r.url.params)["q"] for r in requests] == ["Gateway apartment near USC, Los Angeles, ZIP 90007", "USC"]
    address = assessment(app)["address"]
    assert address["status"] == "LOCATED_UNCONFIRMED" and address["coordinates"]["lat"] == 34.02187
    lookup = app.state.geo.snapshot()["address_geocodes"]["call-1"]
    assert (lookup["place"], lookup["query"]) == ("Gateway apartment near USC, Los Angeles, ZIP 90007", "USC")
    app.state.store.close()


def test_a_whole_city_is_not_a_location():
    los_angeles = place("Los Angeles, Los Angeles County, California", 34.0537, -118.2428, [33.7037, 34.3373, -118.6682, -118.1553])
    handler, _ = geocoder([los_angeles])
    app = map_app(handler)
    stated(app, "Los Angeles")
    locate(app)
    assert assessment(app)["address"]["coordinates"] is None
    assert app.state.geo.snapshot()["address_geocodes"]["call-1"]["status"] == "no_match"
    app.state.store.close()


def test_a_place_found_only_outside_the_area_gets_no_point():
    handler, _ = geocoder([BREA_MAPLE])
    app = map_app(handler)
    stated(app, "450 Maple Ave")
    locate(app)
    assert assessment(app)["address"]["coordinates"] is None
    assert app.state.geo.snapshot()["address_geocodes"]["call-1"]["status"] == "no_match"
    app.state.store.close()


def test_a_person_s_confirmation_and_clearing_are_never_overridden():
    handler, requests = geocoder([USC], [TORRANCE_MAPLE])
    app = map_app(handler)
    geo = app.state.geo
    stated(app, "USC")
    locate(app)
    geo.confirm_address({"call_id": "call-1", "revision": 1, "label": "Leavey Library, USC", "lat": 34.0219, "lon": -118.2829,
                         "reviewer": "Operator 7", "note": "Caller read back the building name.", "confirmed": True})
    geo.apply_auto_lookups()
    assert assessment(app)["address"]["status"] == "HUMAN_CONFIRMED"
    geo.delete_address("call-1")
    locate(app)
    assert assessment(app)["address"]["coordinates"] is None  # cleared stays cleared for this place
    stated(app, "450 Maple Ave", revision=2)
    locate(app)
    assert assessment(app)["address"]["coordinates"]["lat"] == 33.84403  # a new stated place is looked up
    assert len(requests) == 2
    app.state.store.close()


def test_a_changed_place_drops_the_old_point_until_the_new_place_is_found():
    handler, _ = geocoder([USC], [TORRANCE_MAPLE])
    app = map_app(handler)
    stated(app, "USC")
    locate(app)
    stated(app, "450 Maple Ave", revision=2)
    app.state.geo.apply_auto_lookups()
    assert assessment(app)["address"]["coordinates"] is None
    locate(app)
    assert assessment(app)["address"]["coordinates"]["lat"] == 33.84403
    app.state.store.close()


def test_a_failed_lookup_is_shown_and_retried_later():
    handler, requests = geocoder(httpx.Response(503, json={}), [USC])
    app = map_app(handler)
    stated(app, "USC")
    locate(app)
    failed = app.state.geo.snapshot()["address_geocodes"]["call-1"]
    assert failed["status"] == "lookup_failed" and "HTTP 503" in failed["detail"]
    assert assessment(app)["address"]["coordinates"] is None
    locate(app)
    assert len(requests) == 1  # not retried before the retry time
    app.state.geo.auto_retry_at["USC"] = 0
    locate(app)
    assert assessment(app)["address"]["coordinates"]["source"] == "automatic_lookup"
    app.state.store.close()


def test_nothing_is_sent_while_the_map_is_off_or_offline_or_without_a_usable_place():
    handler, requests = geocoder([USC])
    app = map_app(handler)
    stated(app, "USC")
    app.state.geo.configure({"enabled": False})
    locate(app)
    app.state.geo.configure({"enabled": True})
    app.state.store.s["settings"]["internet_available"] = False
    locate(app)
    app.state.store.s["settings"]["internet_available"] = True
    app.state.store.upsert_call({"call_id": "call-1", "revision": 2, "text": "room 1", "location": {"label": "1"}})
    app.state.store.upsert_call({"call_id": "call-2", "revision": 1, "text": "test data",
                                 "location": {"label": "200 N Spring St", "lat": 34.0537, "lon": -118.2427, "source": "test_data_replay"}})
    locate(app)
    assert requests == []
    app.state.store.close()
