"""Conservative, read-only map association; never changes call priority.

Coordinates are an event-address candidate selected for one call, not device GPS.
Colours are prototype attention labels, not official emergency levels. Polygon
distances use a local equirectangular projection suitable for LA County, with a
25 m boundary guard. They are not a survey or a probability of address accuracy.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from itertools import islice
from urllib.parse import urlsplit

POLICY_VERSION = 'map-association-2026-10-17-v1'
LEVELS = {
    'UNKNOWN': {'label': '未知 / 待核实', 'colour': '#64748b', 'rank': 0},
    'INFO': {'label': '仅信息', 'colour': '#2563eb', 'rank': 1},
    'WATCH': {'label': '关注', 'colour': '#eab308', 'rank': 2},
    'HIGH': {'label': '高关注', 'colour': '#f97316', 'rank': 3},
    'CRITICAL': {'label': '最高关注', 'colour': '#dc2626', 'rank': 4},
}
CAP_LEVELS = {'Extreme': 'CRITICAL', 'Severe': 'HIGH', 'Moderate': 'WATCH', 'Minor': 'INFO'}
BOUNDARY_GUARD_M = 25
MAX_EVENTS = 2000
MAX_REPORTS = 500
MAX_VERTICES = 100000  # Total geometry work per assessment, not per event.
POLICY = {
    'version': POLICY_VERSION, 'levels': LEVELS, 'boundary_guard_m': BOUNDARY_GUARD_M,
    'nws_freshness_seconds': 300, 'cap_severity_levels': CAP_LEVELS,
    'meaning': 'Product map-attention labels; neither official emergency levels nor call-priority scores.',
    'rules': [
        'Address verification, coordinate precision, and hazard association are independent.',
        'Only Actual, current, fresh NWS polygon alerts with known CAP fields can contribute official levels.',
        'Immediate/Expected urgency and Observed/Likely certainty retain the mapped CAP severity.',
        'Possible/Unlikely certainty is capped at WATCH; the original severity is retained in each match.',
        'Future, expired, cancelled, stale, or unknown data cannot establish a current official level.',
        'A point or its reported accuracy circle near a boundary is a possible overlap, not confirmed exposure.',
        'USGS epicentres do not supply shaking or damage areas; no impact radius is inferred.',
        'Operator circles remain unverified local areas, even when a report has been reviewed.',
        'No matched alert never means safe. Official shooting coverage is unavailable.',
        'This module never changes, closes, or downgrades call needs or their priority.',
    ],
    'sources': [
        'https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.pdf',
        'https://www.weather.gov/documentation/services-web-alerts',
        'https://www.weather.gov/safety/wildfire-ww',
        'https://earthquake.usgs.gov/data/shakemap/',
        'https://www.w3.org/TR/geolocation/',
    ],
}


def get_policy():
    return copy.deepcopy(POLICY)


def _date(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _num(value, low, high):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and low <= value <= high)


def _link(value):
    try:
        p = urlsplit(value or '')
        return value[:2000] if p.scheme == 'https' and p.hostname and not p.username and not p.password and p.port in (None, 443) else None
    except (TypeError, ValueError):
        return None


def _point(value):
    if not isinstance(value, dict) or not _num(value.get('lat'), -90, 90) or not _num(value.get('lon'), -180, 180):
        return None
    accuracy = value.get('accuracy_m')
    if accuracy is not None and not _num(accuracy, 0, 100000):
        return None
    return float(value['lon']), float(value['lat']), accuracy


def _xy(lon, lat, origin):
    return (math.radians(lon-origin[0]) * 6371008.8 * math.cos(math.radians(origin[1])),
            math.radians(lat-origin[1]) * 6371008.8)


def _inside(ring):
    inside = False
    for a, b in zip(ring, ring[1:]):
        if (a[1] > 0) != (b[1] > 0) and 0 < a[0] + (b[0]-a[0]) * -a[1] / (b[1]-a[1]):
            inside = not inside
    return inside


def _edge_distance(ring):
    best = math.inf
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        dx, dy = bx-ax, by-ay
        length = dx*dx + dy*dy
        t = max(0, min(1, -(ax*dx+ay*dy)/length)) if length else 0
        best = min(best, math.hypot(ax+t*dx, ay+t*dy))
    return best


def _polygon_relation(point, geometry, budget):
    """Return None for outside, INVALID for unsupported/malformed geometry."""
    if not isinstance(geometry, dict) or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
        return 'INVALID'
    polys = [geometry.get('coordinates')] if geometry['type'] == 'Polygon' else geometry.get('coordinates')
    if not isinstance(polys, list) or not polys or len(polys) > 2000:
        return 'INVALID'
    hit, closest = False, math.inf
    for polygon in polys:
        if not isinstance(polygon, list) or not polygon or len(polygon) > 2000:
            return 'INVALID'
        rings = []
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                return 'INVALID'
            if len(ring) > budget[0]:
                budget[0] = 0
                return 'INVALID'
            budget[0] -= len(ring)
            if any(not isinstance(p, (list, tuple)) or len(p) < 2 or not _num(p[0], -180, 180) or not _num(p[1], -90, 90) for p in ring):
                return 'INVALID'
            if ring[0][:2] != ring[-1][:2]:
                return 'INVALID'
            xy = [_xy(p[0], p[1], point) for p in ring]
            if abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(xy, xy[1:]))) < 0.01:
                return 'INVALID'
            rings.append(xy)
            closest = min(closest, _edge_distance(xy))
        hit = hit or (_inside(rings[0]) and not any(_inside(r) for r in rings[1:]))
    if closest <= (point[2] or 0) + BOUNDARY_GUARD_M:
        return 'POSSIBLE_BOUNDARY_OVERLAP'
    if hit:
        return 'POINT_INSIDE' if point[2] is None else 'WITHIN_REPORTED_ACCURACY'
    return None


def _hazard(event):
    name = str(event.get('event_type') or event.get('title') or '').lower()
    if 'red flag' in name or 'fire weather' in name:
        return 'FIRE_WEATHER'
    if 'earthquake' in name:
        return 'EARTHQUAKE'
    if 'fire' in name:
        return 'FIRE'
    if 'shoot' in name:
        return 'SHOOTING'
    return 'WEATHER'


def _provider_map(providers):
    if isinstance(providers, dict):
        return {str(k): v for k, v in islice(providers.items(), 20) if isinstance(v, dict)}
    if isinstance(providers, list):
        return {str(v.get('id')): v for v in providers[:20] if isinstance(v, dict)}
    return {}


def _fresh(event, provider, at):
    fetched = _date(provider.get('last_success_at')) or _date(event.get('fetched_at'))
    event_time = _date(event.get('fetched_at'))
    event_recent = 'fetched_at' not in event or (event_time is not None and 0 <= (at-event_time).total_seconds() <= 300)
    return (bool(provider) and provider.get('enabled') is True and provider.get('status') == 'ok'
            and not provider.get('stale') and not event.get('stale') and fetched is not None
            and event_recent and 0 <= (at-fetched).total_seconds() <= 300)


def assess_exposure(coordinates, events, providers, *, at=None, address_status=None, reports=None):
    """Associate an explicitly selected event-address point with evidence areas.

    All results are conditional on that address candidate; no identity, GPS,
    address truth, real-world danger, or absence of danger is inferred here.
    """
    at = datetime.now(timezone.utc) if at is None else _date(at)
    if at is None:
        raise ValueError('at must be a timezone-aware timestamp')
    gaps = ['OFFICIAL_SHOOTING_COVERAGE_UNAVAILABLE', 'NO_MATCH_DOES_NOT_MEAN_SAFE']
    matches, eligible = [], []
    point = _point(coordinates)
    address_conflict = address_status in ('CONFLICT', 'conflict', 'stale', 'STALE') or (isinstance(coordinates, dict) and bool(coordinates.get('stale')))
    address_confirmed = address_status in ('confirmed', 'CONFIRMED', 'human_confirmed', 'HUMAN_CONFIRMED', 'verified', 'VERIFIED') and not address_conflict
    if point is None:
        gaps.append('EVENT_ADDRESS_COORDINATES_MISSING_OR_INVALID')
    elif point[2] is None:
        gaps.append('ADDRESS_COORDINATE_PRECISION_UNKNOWN')
    if not address_confirmed:
        gaps.append('ADDRESS_NOT_CONFIRMED_ASSOCIATION_IS_CONDITIONAL')
    if address_conflict:
        gaps.append('ADDRESS_CHANGED_OR_CONFLICT_RECONFIRM_BEFORE_CURRENT_CLASSIFICATION')
    providers = _provider_map(providers)
    nws = providers.get('nws', {})
    if not _fresh({}, nws, at):
        gaps.append('NWS_COVERAGE_UNAVAILABLE_OR_STALE')
    if not isinstance(events, list):
        events = []
    if len(events) > MAX_EVENTS:
        gaps.append('EVENT_LIMIT_REACHED_COVERAGE_INCOMPLETE')
    budget = [MAX_VERTICES]
    for event in events[:MAX_EVENTS]:
        if not isinstance(event, dict):
            continue
        if event.get('provider') == 'usgs':
            gaps.append('EARTHQUAKE_LOCAL_INTENSITY_NOT_AVAILABLE_FROM_EPICENTRES')
            continue
        if event.get('provider') != 'nws' or point is None:
            continue
        relation = _polygon_relation(point, event.get('geometry'), budget)
        if relation is None:
            continue
        stale = not _fresh(event, nws, at)
        severity = CAP_LEVELS.get(event.get('severity'), 'UNKNOWN')
        match = {'event_id': str(event.get('id', ''))[:300], 'title': str(event.get('title', ''))[:500],
                 'hazard_type': _hazard(event), 'level': 'UNKNOWN', 'reported_level': severity,
                 'relation': relation, 'source_url': _link(event.get('source_url')),
                 'source_kind': 'official_nws', 'stale': stale, 'reason': '', 'eligible': False}
        reasons = []
        if relation == 'INVALID':
            match['relation'] = 'AREA_UNAVAILABLE'
            reasons.append('No valid loaded polygon; county association is not a hazard footprint.')
            gaps.append('NWS_ALERT_AREA_UNAVAILABLE')
        elif relation == 'POINT_INSIDE':
            reasons.append('Point is inside the published area; address precision is unknown.')
        elif relation == 'POSSIBLE_BOUNDARY_OVERLAP':
            reasons.append('Point/accuracy circle is near a boundary; possible overlap only (25 m guard).')
        else:
            reasons.append('Reported address accuracy circle is within the published area under the local approximation.')
        status = event.get('status', event.get('alert_status'))
        kind = event.get('message_type', event.get('messageType'))
        start_values = [event.get('effective_at', event.get('effective')), event.get('onset_at', event.get('onset', event.get('occurred_at')))]
        starts = [_date(v) for v in start_values if v is not None]
        expiry = _date(event.get('expires_at', event.get('expires')))
        ends = _date(event.get('ends_at', event.get('ends')))
        urgency, certainty = event.get('urgency'), event.get('certainty')
        valid = relation != 'INVALID'
        if not match['source_url']:
            valid = False
            reasons.append('Official source link unavailable; attribution must be checked.')
            gaps.append('NWS_SOURCE_LINK_UNAVAILABLE')
        if status != 'Actual' or kind not in ('Alert', 'Update'):
            valid = False
            match['relation'] = 'CANCELLED' if kind == 'Cancel' else 'STATUS_UNVERIFIED'
            reasons.append('Not a current Actual alert/update.')
            gaps.append('NWS_STATUS_NOT_CURRENT_OR_UNVERIFIED')
        if not starts or any(s is None for s in starts) or expiry is None or (event.get('ends_at', event.get('ends')) is not None and ends is None):
            valid = False
            reasons.append('Missing or invalid effective/onset/expiry time.')
            gaps.append('NWS_VALIDITY_TIME_UNKNOWN')
        elif any(s > at for s in starts):
            valid = False
            match['relation'] = 'FUTURE'
            reasons.append('Future effective/onset time; excluded from current level.')
        elif expiry <= at or (ends and ends <= at) or event.get('expired') or urgency == 'Past':
            valid = False
            match['relation'] = 'EXPIRED'
            reasons.append('Expired/ended/past alert; excluded from current level.')
        if stale:
            valid = False
            reasons.append('Feed unavailable or older than 300 seconds; current status unverified.')
            gaps.append('NWS_COVERAGE_UNAVAILABLE_OR_STALE')
        if severity == 'UNKNOWN' or urgency not in ('Immediate', 'Expected') or certainty not in ('Observed', 'Likely', 'Possible', 'Unlikely'):
            valid = False
            reasons.append('CAP severity, urgency, or certainty does not support a current classification.')
            gaps.append('NWS_CAP_FIELDS_UNKNOWN_OR_NOT_CURRENT')
        if match['hazard_type'] == 'FIRE_WEATHER':
            reasons.append('Fire-weather conditions; this does not establish an active fire here.')
        if valid:
            level = severity
            if certainty in ('Possible', 'Unlikely') and LEVELS[level]['rank'] > LEVELS['WATCH']['rank']:
                level = 'WATCH'
                reasons.append('Source certainty is '+certainty+'; product display is capped at WATCH, original severity retained.')
            match.update(level=level, eligible=True)
            eligible.append(match)
        match['reason'] = ' '.join(reasons)
        matches.append(match)
    if budget[0] <= 0:
        gaps.append('GEOMETRY_WORK_LIMIT_REACHED_COVERAGE_INCOMPLETE')
    if not isinstance(reports, list):
        reports = []
    if len(reports) > MAX_REPORTS:
        gaps.append('REPORT_LIMIT_REACHED_COVERAGE_INCOMPLETE')
    for report in reports[:MAX_REPORTS]:
        if not isinstance(report, dict):
            continue
        if report.get('synthetic'):
            gaps.append('SYNTHETIC_LOCAL_AREAS_EXCLUDED_FROM_CURRENT_LEVELS')
            continue
        if point is None or report.get('zone_radius_m') is None:
            continue
        centre = _point(report)
        radius = report.get('zone_radius_m')
        if centre is None or not _num(radius, 1, 50000):
            gaps.append('LOCAL_AREA_GEOMETRY_INVALID')
            continue
        distance = math.hypot(*_xy(centre[0], centre[1], point))
        if distance > radius + (point[2] or 0) + BOUNDARY_GUARD_M:
            continue
        relation = 'MANUAL_AREA_POTENTIAL'
        if abs(distance-radius) <= (point[2] or 0) + BOUNDARY_GUARD_M:
            relation = 'MANUAL_BOUNDARY_POSSIBLE'
        elif point[2] is None:
            relation = 'MANUAL_POINT_INSIDE'
        until, created = _date(report.get('valid_until')), _date(report.get('created_at'))
        valid = until is not None and created is not None and created <= at < until and not report.get('stale') and not report.get('expired')
        level = str(report.get('zone_level', 'UNKNOWN')).upper()
        level = level if level in LEVELS else 'UNKNOWN'
        match = {'event_id': str(report.get('id', ''))[:300], 'title': str(report.get('label', 'Local report'))[:500],
                 'hazard_type': str(report.get('hazard_type', 'other')).upper(),
                 'level': level if valid else 'UNKNOWN', 'reported_level': level,
                 'relation': relation if valid else 'MANUAL_EXPIRED_OR_UNDATED',
                 'source_url': _link(report.get('source_url')), 'source_kind': 'local_operator',
                 'stale': not valid, 'eligible': valid and level != 'UNKNOWN',
                 'reason': 'Operator-assigned circle and level; potential association only, not an official hazard footprint. Human review does not make it official.'}
        if not valid:
            match['reason'] += ' Expired, stale, future, or missing validity times; excluded from current level.'
        matches.append(match)
        gaps.append('LOCAL_AREA_UNVERIFIED_OPERATOR_ASSUMPTION')
        if match['eligible']:
            eligible.append(match)
    for match in matches:
        match['address_conditional'] = not address_confirmed
        if not address_confirmed:
            match['reason'] += ' Address candidate only; caller presence at this point has not been verified.'
        if address_conflict:
            match['eligible'] = False
            match['reason'] += ' Address has changed, is stale, or conflicts; excluded from current summary pending reconfirmation.'
    if address_conflict:
        eligible = []
    selected = max(eligible, key=lambda m: LEVELS[m['level']]['rank']) if eligible else None
    level = selected['level'] if selected else 'UNKNOWN'
    relation = selected['relation'] if selected else ('UNLOCATED' if point is None else 'NO_CURRENT_SUPPORTED_MATCH')
    if selected and not address_confirmed:
        relation = 'CANDIDATE_' + relation
    if address_conflict:
        relation = 'ADDRESS_REQUIRES_RECONFIRMATION'
    return {'level': level, 'label': '位置需重新核实' if address_conflict else LEVELS[level]['label'], 'colour': LEVELS[level]['colour'],
            'relation': relation, 'matches': matches, 'gaps': list(dict.fromkeys(gaps)),
            'as_of': at.isoformat(), 'policy_version': POLICY_VERSION}
