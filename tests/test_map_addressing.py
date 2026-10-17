"""Adversarial address formats and provenance; not an address-accuracy benchmark."""
import copy

import pytest

from crisisfusion_map.addressing import assess_address


def call(text="", location=None, **kwargs):
    return {"call_id": "test-address", "revision": 1, "text": text, "location": location or {}, **kwargs}


@pytest.mark.parametrize("text,quote", [
    ("I am at 123 Main St, Los Angeles.", "123 Main St"),
    ("Estoy en 123 South Figueroa Street, Los Angeles.", "123 South Figueroa Street"),
    ("我在 123 S Figueroa St，洛杉矶。", "123 S Figueroa St"),
    ("我在菲格罗亚街123号。", "菲格罗亚街123号"),
    ("My address is 915 W 30th Street Apt 4B.", "915 W 30th Street Apt 4B"),
])
def test_civic_formats_keep_original_quote_and_do_not_geocode(text, quote):
    result = assess_address(call(text))
    assert result["status"] == "ADDRESS_CANDIDATE"
    match = next(c for c in result["candidates"] if c["kind"] == "civic_address")
    assert match["quote"] == quote
    assert text[slice(*match["span"])] == match["quote"]
    assert match["revision"] == 1 and match["source"] == "transcript"
    assert result["coordinates"] is None
    assert result["measured_accuracy"]["value"] is None


@pytest.mark.parametrize("text", ["At Main St and 1st Ave.", "Estoy en Figueroa St y Jefferson Blvd.", "在 Figueroa St 与 Jefferson Blvd 交叉口。"])
def test_cross_streets_need_exact_location(text):
    result = assess_address(call(text))
    assert result["status"] == "ADDRESS_CANDIDATE"
    assert result["address_kind"] == "intersection"
    assert "building_number_or_exact_side" in result["missing_fields"]


@pytest.mark.parametrize("text", ["I am near USC.", "Estoy en Pasadena.", "我在南加州大学附近。", "I am at North Hall."])
def test_place_and_area_do_not_become_address(text):
    result = assess_address(call(text))
    assert result["status"] == "AREA_ONLY"
    assert result["coordinates"] is None


@pytest.mark.parametrize("text", ["Call me at 213 555 0199.", "There are 123 people and 4 fires.", "I can't breathe.", "Coordinates are 34.02, -118.28.", ""])
def test_unrecognized_reference_is_not_invented(text):
    result = assess_address(call(text))
    assert result["status"] == "NO_ADDRESS"
    assert result["coordinates"] is None


@pytest.mark.parametrize("label", ["unknown", "N/A", "未知", "不详", ""])
def test_placeholder_label_is_not_a_place(label):
    assert assess_address(call(location={"label": label}))["status"] == "NO_ADDRESS"


@pytest.mark.parametrize("text", ["I am not at 123 Main St.", "No estoy en 123 Main St.", "我不在123 Main St。", "I was at 123 Main St yesterday."])
def test_negated_or_historical_address_is_not_current(text):
    result = assess_address(call(text))
    assert result["status"] == "NO_ADDRESS"
    assert result["candidates"]
    assert any(c["negated"] or c["historical"] for c in result["candidates"])


def test_negation_does_not_leak_between_clauses():
    assert assess_address(call("I am not injured; I am at 123 Main St."))["status"] == "ADDRESS_CANDIDATE"


def test_multiple_addresses_are_not_chosen_by_last_mention():
    result = assess_address(call("I am at 123 Main St or 456 Oak Ave, not sure."))
    assert result["status"] == "CONFLICT"
    assert "multiple_specific_addresses" in result["flags"]


def test_same_address_with_suffix_direction_aliases_is_one_claim():
    result = assess_address(call("I am at 123 South Figueroa Street.", {"label": "123 S Figueroa St"}))
    assert result["status"] == "ADDRESS_CANDIDATE"


def test_changed_revision_keeps_original_sources_and_requires_review():
    source = call("I am at 456 Oak Ave.", revision=2, revisions=[
        {"revision": 1, "text": "I am at 123 Main St.", "timestamp": "2026-10-17T10:00:00Z"},
        {"revision": 2, "text": "I am at 456 Oak Ave.", "timestamp": "2026-10-17T10:01:00Z"}])
    original = copy.deepcopy(source)
    result = assess_address(source)
    assert result["status"] == "CONFLICT"
    assert "address_changed_between_revisions" in result["flags"]
    assert {c["revision"] for c in result["candidates"]} == {1, 2}
    assert source == original


def test_followup_without_address_retains_prior_reference():
    result = assess_address(call("I am still trapped.", revision=2, revisions=[{"revision": 1, "text": "I am at 123 Main St."}]))
    assert result["status"] == "ADDRESS_CANDIDATE"
    assert "address_from_prior_revision" in result["flags"]


def test_retracted_prior_address_is_a_conflict():
    result = assess_address(call("I am not at 123 Main St.", revision=2, revisions=[{"revision": 1, "text": "I am at 123 Main St."}]))
    assert result["status"] == "CONFLICT"
    assert "previous_address_retracted" in result["flags"]


def confirmation(**overrides):
    return {"label": "123 Main St", "lat": 34.02, "lon": -118.28, "confirmed": True,
            "reviewer": "Operator A", "confirmed_at": "2026-10-17T10:00:00Z", "revision": 1,
            "source": "operator_confirmed", **overrides}


def test_current_operator_confirmation_is_attestation_without_accuracy_claim():
    result = assess_address(call("123 Main St or 456 Oak Ave"), confirmation())
    assert result["status"] == "HUMAN_CONFIRMED"
    assert result["verification"]["scope"] == "local_operator_attestation_only"
    assert "conflict_resolved_by_operator" in result["flags"]
    assert result["measured_accuracy"] == {"value": None, "unit": None, "validation": "not_measured"}


def test_stale_confirmation_is_unconfirmed_and_coordinate_marked_stale():
    result = assess_address(call("still here", revision=2), confirmation())
    assert result["status"] == "LOCATED_UNCONFIRMED"
    assert "stale_confirmation" in result["flags"]
    assert result["coordinates"]["stale"]
    assert not result["verification"]["confirmed"]


def test_geocoder_point_is_never_human_confirmed():
    result = assess_address(call("123 Main St"), confirmation(confirmed=False, source="census_geocoder_interpolated"))
    assert result["status"] == "LOCATED_UNCONFIRMED"
    assert result["coordinates"]["source"] == "census_geocoder_interpolated"


def test_confirmation_requires_operator_and_point():
    result = assess_address(call("123 Main St"), confirmation(reviewer=""))
    assert result["status"] == "LOCATED_UNCONFIRMED"
    assert "incomplete_confirmation" in result["flags"]


@pytest.mark.parametrize("point", [{"lat": True, "lon": -118}, {"lat": 91, "lon": -118}, {"lat": 34, "lon": float("nan")}, {"lat": 34}])
def test_invalid_explicit_coordinates_are_never_map_points(point):
    assert assess_address(call(location=point))["coordinates"] is None


def test_explicit_reported_point_is_separate_from_address_completeness():
    result = assess_address(call(location={"lat": 34.02, "lon": -118.28, "source": "caller_reported"}))
    assert result["status"] == "LOCATED_UNCONFIRMED"
    assert result["completeness"] == "none"
    assert result["coordinate_role"] == "reported_incident"


def test_device_location_is_not_incident_address():
    result = assess_address(call(location={"lat": 34.02, "lon": -118.28, "source": "browser_geolocation_client_reported"}))
    assert result["status"] == "NO_ADDRESS"
    assert result["coordinates"] is None
    assert "device_coordinates_excluded" in result["flags"]


def test_browser_asr_and_nearby_address_keep_uncertainty():
    result = assess_address(call("I may be near 123 Main St.", input_mode="browser_voice"))
    assert result["status"] == "ADDRESS_CANDIDATE"
    assert "asr_transcription_unverified" in result["flags"]
    assert "approximate_location" in result["flags"]


@pytest.mark.parametrize("text", ["I was at 123 Main St.", "I am at 123 Main St yesterday.", "我以前在菲格罗亚街123号。", "我不在菲格罗亚街123号。", "I am nowhere near 123 Main St."])
def test_additional_temporal_and_negative_context(text):
    result = assess_address(call(text))
    assert result["status"] == "NO_ADDRESS"
    assert result["candidates"]


def test_intersection_order_and_abbreviation_do_not_create_false_conflict():
    result = assess_address(call("I am at Main Street and 1st Avenue.", {"label": "1st Ave & Main St"}))
    assert result["status"] == "ADDRESS_CANDIDATE"


def test_stale_point_differing_from_current_address_requires_resolution():
    result = assess_address(call("456 Oak Ave", revision=2), confirmation())
    assert result["status"] == "CONFLICT"
    assert "current_address_differs_from_stale_point" in result["flags"]
    assert result["coordinates"]["stale"]


@pytest.mark.parametrize("text,quote", [
    ("我在123 Main St附近。", "123 Main St"),
    ("Estoy en 123 César Chávez Ave, Los Angeles, CA.", "123 César Chávez Ave"),
    ("Estoy en 456 Peña Road.", "456 Peña Road."),
])
def test_chinese_adjacent_context_and_accented_street_names(text, quote):
    result = assess_address(call(text))
    assert result["status"] == "ADDRESS_CANDIDATE"
    assert result["candidates"][0]["quote"] == quote
    if "附近" in text:
        assert "approximate_location" in result["flags"]


def test_chinese_adjacent_cross_streets():
    result = assess_address(call("我在Main St和1st Ave交叉口。"))
    assert result["status"] == "ADDRESS_CANDIDATE"
    assert result["address_kind"] == "intersection"
    assert result["display_label"] == "Main St和1st Ave"


@pytest.mark.parametrize("text", [
    "123 cafés open today.", "123 niños are safe.", "我有123位家人在附近。",
    "There are 123 Main Streetlights broken.", "Reference ABC123 Main Staging area.",
])
def test_expanded_character_support_does_not_match_suffix_prefixes_or_counts(text):
    result = assess_address(call(text))
    assert result["status"] == "NO_ADDRESS"
    assert result["coordinates"] is None

