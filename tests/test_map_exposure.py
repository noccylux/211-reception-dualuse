"""Pure map-association checks: no external requests, geolocation, or score changes."""
import copy
from datetime import datetime, timedelta, timezone

import pytest

from crisisfusion_map.exposure import assess_exposure, get_policy

AT = datetime(2026, 10, 17, 18, tzinfo=timezone.utc)
POINT = {'lat': 34.02, 'lon': -118.285, 'accuracy_m': 10}


def stamp(seconds=0):
    return (AT + timedelta(seconds=seconds)).isoformat()


def box(left=-118.30, bottom=34.00, right=-118.27, top=34.04):
    return [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]


def event(**changes):
    value = {'id': 'nws-fixture', 'provider': 'nws', 'title': 'Test warning', 'event_type': 'Flash Flood Warning',
             'geometry': {'type': 'Polygon', 'coordinates': [box()]},
             'severity': 'Severe', 'certainty': 'Likely', 'urgency': 'Immediate',
             'status': 'Actual', 'message_type': 'Alert', 'effective_at': stamp(-60), 'onset': stamp(-30),
             'expires_at': stamp(600), 'fetched_at': stamp(-5), 'source_url': 'https://api.weather.gov/alerts/fixture'}
    value.update(changes)
    return value


def providers(**changes):
    nws = {'id': 'nws', 'enabled': True, 'status': 'ok', 'stale': False, 'last_success_at': stamp(-5)}
    nws.update(changes)
    return [nws]


def assess(events=None, coordinates=None, provider_state=None, **changes):
    kwargs = {'at': AT, 'address_status': 'CONFIRMED'}
    kwargs.update(changes)
    return assess_exposure(POINT if coordinates is None else coordinates, [event()] if events is None else events,
                           providers() if provider_state is None else provider_state, **kwargs)


@pytest.mark.parametrize('severity,level', [('Extreme', 'CRITICAL'), ('Severe', 'HIGH'), ('Moderate', 'WATCH'), ('Minor', 'INFO')])
def test_explicit_cap_severity_mapping_retains_evidence(severity, level):
    result = assess([event(severity=severity)])
    assert result['level'] == level
    assert result['relation'] == 'WITHIN_REPORTED_ACCURACY'
    assert result['matches'][0]['source_kind'] == 'official_nws'
    assert 'OFFICIAL_SHOOTING_COVERAGE_UNAVAILABLE' in result['gaps']


@pytest.mark.parametrize('certainty', ['Possible', 'Unlikely'])
def test_lower_source_certainty_capped_without_erasing_original_severity(certainty):
    result = assess([event(severity='Extreme', certainty=certainty)])
    assert result['level'] == 'WATCH'
    assert result['matches'][0]['reported_level'] == 'CRITICAL'
    assert 'capped at WATCH' in result['matches'][0]['reason']


@pytest.mark.parametrize('changes', [{'severity': 'Unknown'}, {'certainty': 'Unknown'}, {'urgency': 'Unknown'},
                                    {'urgency': None}, {'status': None}, {'effective_at': 'not a date'},
                                    {'expires_at': None}, {'ends_at': 'not a date'}, {'source_url': 'javascript:alert(1)'}])
def test_missing_or_unknown_required_evidence_never_establishes_current_level(changes):
    result = assess([event(**changes)])
    assert result['level'] == 'UNKNOWN'
    assert not result['matches'][0]['eligible']


@pytest.mark.parametrize('changes,relation', [({'message_type': 'Cancel'}, 'CANCELLED'),
    ({'status': 'Test'}, 'STATUS_UNVERIFIED'), ({'expires_at': stamp()}, 'EXPIRED'),
    ({'ends_at': stamp(-1)}, 'EXPIRED'), ({'onset': stamp(10)}, 'FUTURE'),
    ({'effective_at': stamp(10)}, 'FUTURE'), ({'urgency': 'Past'}, 'EXPIRED')])
def test_cancel_test_expired_and_future_alerts_remain_context_only(changes, relation):
    result = assess([event(**changes)])
    assert result['level'] == 'UNKNOWN'
    assert result['matches'][0]['relation'] == relation


@pytest.mark.parametrize('state', [providers(stale=True), providers(status='error'), providers(enabled=False),
                                  providers(last_success_at=stamp(-301)), providers(last_success_at=stamp(1)), []])
def test_stale_or_disabled_feed_is_not_current_exposure(state):
    result = assess(provider_state=state)
    assert result['level'] == 'UNKNOWN'
    assert result['matches'][0]['stale']


def test_event_old_cache_cannot_borrow_fresh_provider_time():
    assert assess([event(fetched_at=stamp(-301))])['level'] == 'UNKNOWN'


def test_red_flag_is_fire_weather_not_confirmed_active_fire():
    match = assess([event(event_type='Red Flag Warning')])['matches'][0]
    assert match['hazard_type'] == 'FIRE_WEATHER'
    assert 'does not establish an active fire' in match['reason']


def test_polygon_hole_excludes_point_and_hole_edge_can_overlap():
    geometry = {'type': 'Polygon', 'coordinates': [box(), box(-118.29, 34.015, -118.28, 34.025)]}
    result = assess([event(geometry=geometry)])
    assert result['level'] == 'UNKNOWN' and result['matches'] == []
    result = assess([event(geometry=geometry)], {'lat': 34.02, 'lon': -118.2801, 'accuracy_m': 20})
    assert result['relation'] == 'POSSIBLE_BOUNDARY_OVERLAP'


def test_outside_centre_with_overlapping_accuracy_circle_is_possible_match():
    result = assess(coordinates={'lat': 34.02, 'lon': -118.2704, 'accuracy_m': 50},
                    events=[event(geometry={'type': 'Polygon', 'coordinates': [box(right=-118.271)]})])
    assert result['relation'] == 'POSSIBLE_BOUNDARY_OVERLAP'
    assert result['level'] == 'HIGH'


def test_guard_catches_exact_boundary_and_unknown_precision_not_zero_error():
    boundary = assess(coordinates={'lat': 34.02, 'lon': -118.27})
    assert boundary['relation'] == 'POSSIBLE_BOUNDARY_OVERLAP'
    inside = assess(coordinates={'lat': 34.02, 'lon': -118.285})
    assert inside['relation'] == 'POINT_INSIDE'
    assert 'ADDRESS_COORDINATE_PRECISION_UNKNOWN' in inside['gaps']


def test_multipolygon_matches_nonfirst_part():
    geometry = {'type': 'MultiPolygon', 'coordinates': [[box(-118.8, 34.4, -118.7, 34.5)], [box()]]}
    assert assess([event(geometry=geometry)])['level'] == 'HIGH'


@pytest.mark.parametrize('geometry', [None, {'type': 'Point', 'coordinates': [-118.285, 34.02]},
    {'type': 'Polygon', 'coordinates': []}, {'type': 'Polygon', 'coordinates': [[[0, 0], [0, 1], [1, 0]]]},
    {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 1], [2, 2], [0, 0]]]}])
def test_missing_or_malformed_area_not_countywide_impact(geometry):
    result = assess([event(geometry=geometry)])
    assert result['level'] == 'UNKNOWN'
    assert result['matches'][0]['relation'] == 'AREA_UNAVAILABLE'
    assert 'NWS_ALERT_AREA_UNAVAILABLE' in result['gaps']


def test_usgs_epicentre_magnitude_never_generates_local_impact_radius():
    quake = {'id': 'quake', 'provider': 'usgs', 'magnitude': 9.9, 'geometry': {'type': 'Point', 'coordinates': [-118.285, 34.02]}}
    result = assess([quake])
    assert result['level'] == 'UNKNOWN' and result['matches'] == []
    assert 'EARTHQUAKE_LOCAL_INTENSITY_NOT_AVAILABLE_FROM_EPICENTRES' in result['gaps']


def test_all_matching_regions_preserved_highest_supported_current_level_only():
    result = assess([event(id='low', severity='Minor'), event(id='high', severity='Extreme'),
                     event(id='future', severity='Extreme', onset=stamp(600)), event(id='stale', stale=True)])
    assert result['level'] == 'CRITICAL'
    assert {m['event_id'] for m in result['matches']} == {'low', 'high', 'future', 'stale'}
    assert sum(m['eligible'] for m in result['matches']) == 2


def test_no_records_or_no_location_never_means_safe():
    assert assess([])['level'] == 'UNKNOWN'
    unlocated = assess_exposure(None, [event()], providers(), at=AT)
    assert unlocated['relation'] == 'UNLOCATED' and unlocated['level'] == 'UNKNOWN'
    assert 'NO_MATCH_DOES_NOT_MEAN_SAFE' in unlocated['gaps']


def report(**changes):
    value = {'id': 'local', 'label': 'Operator gunfire report', 'lat': 34.02, 'lon': -118.285,
             'zone_radius_m': 200, 'hazard_type': 'shooting', 'zone_level': 'CRITICAL',
             'valid_until': stamp(600), 'created_at': stamp(-20), 'reviewed': True,
             'source_url': 'https://lasd.org/'}
    value.update(changes)
    return value


def test_reviewed_local_shooting_circle_never_becomes_official():
    result = assess([], reports=[report()])
    assert result['level'] == 'CRITICAL'
    assert result['relation'] == 'MANUAL_AREA_POTENTIAL'
    match = result['matches'][0]
    assert match['source_kind'] == 'local_operator'
    assert 'not an official hazard footprint' in match['reason']
    assert 'LOCAL_AREA_UNVERIFIED_OPERATOR_ASSUMPTION' in result['gaps']


@pytest.mark.parametrize('changes', [{'valid_until': stamp(-1)}, {'valid_until': None}, {'created_at': stamp(1)}, {'expired': True}])
def test_expired_or_undated_manual_areas_do_not_establish_current_level(changes):
    result = assess([], reports=[report(**changes)])
    assert result['level'] == 'UNKNOWN'
    assert result['matches'][0]['relation'] == 'MANUAL_EXPIRED_OR_UNDATED'


def test_candidate_address_exposure_is_explicitly_conditional():
    result = assess(address_status='CANDIDATE')
    assert result['level'] == 'HIGH'
    assert result['relation'].startswith('CANDIDATE_')
    assert result['matches'][0]['address_conditional']


def test_human_confirmed_status_is_not_mislabeled_as_candidate():
    result = assess(address_status='HUMAN_CONFIRMED')
    assert result['relation'] == 'WITHIN_REPORTED_ACCURACY'
    assert not result['matches'][0]['address_conditional']


def test_synthetic_local_area_cannot_make_a_real_address_red():
    result = assess([], reports=[report(synthetic=True)])
    assert result['level'] == 'UNKNOWN' and result['matches'] == []
    assert 'SYNTHETIC_LOCAL_AREAS_EXCLUDED_FROM_CURRENT_LEVELS' in result['gaps']


@pytest.mark.parametrize('changes', [{'address_status': 'CONFLICT'}, {'coordinates': {**POINT, 'stale': True}}])
def test_changed_or_conflicting_address_requires_reconfirmation(changes):
    result = assess(**changes)
    assert result['level'] == 'UNKNOWN'
    assert result['relation'] == 'ADDRESS_REQUIRES_RECONFIRMATION'
    assert result['matches'][0]['reported_level'] == 'HIGH'
    assert not result['matches'][0]['eligible']


def test_policy_and_inputs_are_not_mutated():
    value, state = [event()], providers()
    before = copy.deepcopy((value, state))
    assess(value, provider_state=state)
    assert before == (value, state)
    policy = get_policy()
    policy['levels']['HIGH']['rank'] = 999
    assert get_policy()['levels']['HIGH']['rank'] == 3


def test_bounded_collections_report_incomplete_coverage():
    result = assess([{'provider': 'other'}] * 2001, reports=[{}] * 501)
    assert 'EVENT_LIMIT_REACHED_COVERAGE_INCOMPLETE' in result['gaps']
    assert 'REPORT_LIMIT_REACHED_COVERAGE_INCOMPLETE' in result['gaps']


@pytest.mark.parametrize('coordinates', [{'lat': True, 'lon': -118}, {'lat': float('nan'), 'lon': -118},
    {'lat': 34, 'lon': -118, 'accuracy_m': -1}, {'lat': 34, 'lon': -118, 'accuracy_m': True}])
def test_bad_coordinates_never_classify(coordinates):
    result = assess(coordinates=coordinates)
    assert result['level'] == 'UNKNOWN' and result['relation'] == 'UNLOCATED'

