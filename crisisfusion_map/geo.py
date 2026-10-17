"""Optional LA County situational map. No location or feed changes call scoring.

Adapters return attributed observations, not independently authenticated facts.
Only fixed public endpoints are fetched; caller coordinates never go to feeds.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request

from .store import now
from .addressing import assess_address
from .exposure import assess_exposure, get_policy as exposure_policy
from .geocoding import lookup as lookup_address

ROOT = Path(__file__).resolve().parent
BOUNDARY = json.loads((ROOT / 'data/la_county.geojson').read_text(encoding='utf-8'))
BBOX = BOUNDARY['bbox']
MAX_BYTES = 4_000_000
REFRESH_SECONDS = 60


def date(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number between {low} and {high}')
    return float(value)


def text(value, limit=1000):
    return str(value or '')[:limit]


def link(value, hosts=None):
    try:
        p = urlsplit(value or '')
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        if hosts and p.hostname not in hosts:
            return None
        return value[:2000]
    except (TypeError, ValueError):
        return None


def in_ring(lon, lat, ring):
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if ((a[1] > lat) != (b[1] > lat)) and lon < (b[0]-a[0]) * (lat-a[1]) / (b[1]-a[1]) + a[0]:
            inside = not inside
    return inside


def in_county(lon, lat):
    for feature in BOUNDARY['features']:
        g = feature['geometry']
        for polygon in ([g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']):
            if in_ring(lon, lat, polygon[0]) and not any(in_ring(lon, lat, r) for r in polygon[1:]):
                return True
    return False


def geometry(value):
    """Discard invalid or excessive external geometry; preserve null explicitly."""
    if not isinstance(value, dict) or value.get('type') not in {'Point', 'Polygon', 'MultiPolygon'}:
        return None
    count = 0
    def walk(v, depth):
        nonlocal count
        if not isinstance(v, list) or not v:
            raise ValueError('Invalid geometry')
        if depth == 0:
            if len(v) < 2:
                raise ValueError('Invalid point')
            count += 1
            if count > 50000:
                raise ValueError('Geometry too large')
            return [number(v[0], -180, 180, 'lon'), number(v[1], -90, 90, 'lat')]
        return [walk(x, depth-1) for x in v]
    try:
        return {'type': value['type'], 'coordinates': walk(value.get('coordinates'), {'Point': 0, 'Polygon': 2, 'MultiPolygon': 3}[value['type']])}
    except (ValueError, TypeError, RecursionError):
        return None


async def fetch_document(client, url, params=None):
    async with client.stream('GET', url, params=params) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError('Provider response exceeded size limit')
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError('Invalid provider document')
    return data


async def fetch_json(client, url, params):
    data = await fetch_document(client, url, params)
    if not isinstance(data, dict) or not isinstance(data.get('features'), list) or len(data['features']) > 2000:
        raise ValueError('Invalid or oversized provider collection')
    return data


class NWSProvider:
    id = 'nws'
    title = 'NWS · LA County active alerts'
    source_url = 'https://www.weather.gov/documentation/services-web-api'
    freshness_seconds = 300
    coverage = 'Active county/zone alerts associated with CAC037; an alert may affect only part of the county.'

    async def fetch(self, client, at):
        # County UGC includes zone-based and county-based warnings. A CAZ-only
        # query would miss county-based products. This county query was checked
        # against the live endpoint; arbitrary redirects remain disabled.
        data = await fetch_json(client, 'https://api.weather.gov/alerts/active', {'zone': 'CAC037'})
        if data.get('pagination', {}).get('next'):
            raise ValueError('NWS result pagination exceeds supported coverage')
        events = []
        for feature in data['features']:
            p = feature.get('properties') or {}
            if p.get('status') != 'Actual' or p.get('messageType') not in ('Alert', 'Update'):
                continue
            expires = date(p.get('expires'))
            if expires is None:
                raise ValueError('NWS alert missing expiration')
            if expires <= at:
                continue
            source = link(p.get('@id') or feature.get('id'), {'api.weather.gov', 'alerts.weather.gov', 'www.weather.gov'})
            if not source:
                raise ValueError('NWS alert missing official source identifier')
            g = geometry(feature.get('geometry'))
            if g and g['type'] not in ('Polygon', 'MultiPolygon'):
                g = None
            zone_urls = p.get('affectedZones') or []
            supported_zones = (isinstance(zone_urls, list) and all(isinstance(z, str) and re.fullmatch(r'https://api\.weather\.gov/zones/(forecast|fire|county)/CA[ZC]\d{3}', z) for z in zone_urls))
            events.append({'id': text(p.get('id') or feature.get('id'), 300), 'provider': self.id,
                'title': text(p.get('headline') or p.get('event'), 500), 'event_type': text(p.get('event'), 100),
                'description': text(p.get('description'), 5000), 'instruction': text(p.get('instruction'), 3000),
                'severity': text(p.get('severity'), 50), 'certainty': text(p.get('certainty'), 50),
                'urgency': text(p.get('urgency'), 50), 'status': text(p.get('status'), 30),
                'message_type': text(p.get('messageType'), 30), 'effective_at': p.get('effective'), 'onset': p.get('onset'),
                'ends_at': p.get('ends'),
                'source_url': source, 'source_status': 'Official NWS publication · not independently verified',
                'occurred_at': p.get('onset') or p.get('effective'), 'updated_at': p.get('sent'), 'expires_at': p.get('expires'),
                'area_description': text(p.get('areaDesc'), 1500), 'geometry': g,
                'affected_zones': zone_urls if supported_zones else [],
                'geometry_note': 'Official alert polygon; may extend outside LA County' if g else 'No polygon supplied; county association only, not a county-wide hazard footprint',
                'fetched_at': at.isoformat()})
        return events


class USGSProvider:
    id = 'usgs'
    title = 'USGS · county epicentres, 7 days, M ≥ 2.5'
    source_url = 'https://earthquake.usgs.gov/fdsnws/event/1/'
    freshness_seconds = 900
    coverage = 'Earthquake epicentres inside the county boundary, last 7 days, magnitude ≥ 2.5. Not a shaking or damage footprint; excludes outside-county epicentres felt here.'

    async def fetch(self, client, at):
        data = await fetch_json(client, 'https://earthquake.usgs.gov/fdsnws/event/1/query', {
            'format': 'geojson', 'starttime': (at-timedelta(days=7)).isoformat(), 'endtime': at.isoformat(),
            'minlongitude': BBOX[0], 'minlatitude': BBOX[1], 'maxlongitude': BBOX[2], 'maxlatitude': BBOX[3],
            'minmagnitude': 2.5, 'eventtype': 'earthquake', 'orderby': 'time', 'limit': 1000})
        if len(data['features']) >= 1000:
            raise ValueError('USGS result reached query limit; coverage incomplete')
        events = []
        for feature in data['features']:
            p = feature.get('properties') or {}
            g = geometry(feature.get('geometry'))
            if not g or g['type'] != 'Point':
                raise ValueError('Invalid USGS epicentre geometry')
            lon, lat = g['coordinates']
            if not in_county(lon, lat):
                continue
            source = link(p.get('url'), {'earthquake.usgs.gov'})
            if not source:
                raise ValueError('USGS event missing official link')
            times = [datetime.fromtimestamp(number(p.get(k), 0, 100_000_000_000_000, k)/1000, timezone.utc).isoformat() for k in ('time', 'updated')]
            events.append({'id': text(feature.get('id'), 200), 'provider': self.id, 'title': text(p.get('title'), 500),
                'event_type': 'Earthquake', 'description': text(p.get('place'), 500), 'source_url': source,
                'source_status': 'USGS processing status: ' + text(p.get('status') or 'unknown', 50),
                'magnitude': p.get('mag'), 'occurred_at': times[0], 'updated_at': times[1], 'expires_at': None,
                'geometry': g, 'geometry_note': 'Epicentre only; not shaking, damage or safety radius', 'fetched_at': at.isoformat()})
        return events


# A new reviewed adapter implements id/title/source_url/coverage/freshness_seconds
# and async fetch(client, at). No downloaded code, arbitrary URL or API key input.
PROVIDERS = {p.id: p for p in (NWSProvider(), USGSProvider())}


class GeoManager:
    def __init__(self, engine, transport=None):
        self.engine, self.transport = engine, transport
        self.token = secrets.token_urlsafe(32)
        self.refresh_lock = asyncio.Lock()
        self.address_lock = asyncio.Lock()
        self.address_attempts = {}
        self.address_generations = {}
        self.address_epoch = 0

    def data(self):
        data = self.engine.s.setdefault('geo_plugin', {'enabled': False, 'providers': {
            key: {'enabled': True, 'status': 'not_loaded', 'last_attempt_at': None, 'last_success_at': None, 'error': None, 'events': []}
            for key in PROVIDERS}, 'caller_locations': {}, 'reports': {}})
        data.setdefault('address_records', {})
        data.setdefault('address_geocodes', {})
        return data

    def guard(self, request):
        if request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return
        # Root paths are not part of an Origin. Mounted apps retain their prefix
        # in base_url; compare the scheme and authority only.
        expected = f'{request.url.scheme}://{request.url.netloc}'
        supplied_token = request.headers.get('X-CrisisFusion-Geo', '')
        if request.headers.get('origin', '').rstrip('/') != expected or not supplied_token.isascii() or not secrets.compare_digest(supplied_token, self.token):
            raise HTTPException(403, 'Map mutations require this local page and its map token')

    def require_enabled(self):
        if not self.data()['enabled']:
            raise HTTPException(409, 'Enable the LA County map plugin first')

    def calls(self):
        return {c['call_id']: {'call_id': c['call_id'], 'revision':c.get('revision', 0), 'input_mode': c.get('input_mode'),
            'active': c['call_id'] in self.engine.s['active_calls'], 'reported_location': c.get('location')}
            for c in self.engine.s['calls'].values()}

    def address_call(self, call_id):
        if not isinstance(call_id, str) or call_id not in self.calls():
            raise ValueError('Choose an existing call')
        return self.engine.s['calls'][call_id]

    @staticmethod
    def check_address_revision(call, payload):
        if type(payload.get('revision')) is not int or payload['revision'] < 0:
            raise ValueError('Include the transcript revision displayed while reviewing this address')
        if payload['revision'] != call.get('revision', 0):
            raise HTTPException(409, 'The call changed since this address was reviewed. Reload and verify the current revision.')

    def snapshot(self):
        with self.engine.lock:
            data = self.data()
            at = datetime.now(timezone.utc)
            providers, events = [], []
            for key, adapter in PROVIDERS.items():
                cache = data['providers'][key]
                last = date(cache['last_success_at'])
                stale = not last or (at-last).total_seconds() > adapter.freshness_seconds or cache['status'] == 'error'
                providers.append({k: v for k, v in cache.items() if k != 'events'} | {'id': key, 'title': adapter.title, 'stale': stale, 'source_url': adapter.source_url, 'coverage': adapter.coverage})
                if data['enabled'] and cache['enabled']:
                    for event in cache['events']:
                        expiry = date(event.get('expires_at'))
                        events.append({**event, 'stale': stale, 'expired': bool(expiry and expiry <= at)})
            locations = []
            for loc in data['caller_locations'].values():
                locations.append({**loc, 'stale': (at-date(loc['captured_at'])).total_seconds() > 300})
            reports = [{**r, 'expired':bool(date(r.get('valid_until')) and date(r['valid_until']) <= at)} for r in data['reports'].values()]
            assessments = []
            if data['enabled']:
                for call_id in self.calls():
                    call = self.address_call(call_id)
                    address = assess_address(call, data['address_records'].get(call_id))
                    exposure = assess_exposure(address.get('coordinates'), events, providers, at=at,
                        address_status=address['status'], reports=reports)
                    assessments.append({'call_id':call_id, 'address':address, 'exposure':exposure,
                        'call_priority':call.get('priority_assessment'), 'synthetic':call.get('input_mode') in ('replay','simulated_voice')})
            return copy.deepcopy({'enabled': data['enabled'], 'csrf_token': self.token, 'store_id': self.engine.s['store_id'], 'scope': {'name': 'Los Angeles County', 'bbox': BBOX, 'boundary': BOUNDARY},
                'providers': providers, 'official_events': events, 'caller_locations': locations, 'reports': reports,
                'call_assessments':assessments, 'assessment_policy':exposure_policy(), 'address_geocodes':data['address_geocodes'],
                'calls': list(self.calls().values()), 'service_conditions': self.engine.s['settings'], 'refresh_min_seconds': REFRESH_SECONDS})

    def configure(self, payload):
        if set(payload)-{'enabled', 'providers'}:
            raise ValueError('Unknown map setting')
        if 'enabled' in payload and type(payload['enabled']) is not bool:
            raise ValueError('enabled must be boolean')
        selected = payload.get('providers', {})
        if not isinstance(selected, dict) or any(k not in PROVIDERS or type(v) is not bool for k, v in selected.items()):
            raise ValueError('Unknown provider or nonboolean setting')
        with self.engine.lock:
            data = self.data()
            if 'enabled' in payload:
                if data['enabled'] != payload['enabled']:
                    self.address_epoch += 1
                data['enabled'] = payload['enabled']
            for k, v in selected.items():
                data['providers'][k]['enabled'] = v
            self.engine._audit('geo_plugin_configured', configuration=payload)
            self.engine._save()
        return self.snapshot()

    async def refresh(self):
        async with self.refresh_lock:
            with self.engine.lock:
                self.require_enabled()
                data = self.data()
                if not self.engine.s['settings']['internet_available']:
                    raise HTTPException(409, 'Internet interruption is enabled; cached data only')
                at = datetime.now(timezone.utc)
                todo = []
                for key in PROVIDERS:
                    cache = data['providers'][key]
                    attempted = date(cache['last_attempt_at'])
                    if cache['enabled'] and (not attempted or (at-attempted).total_seconds() >= REFRESH_SECONDS):
                        cache['last_attempt_at'] = at.isoformat()
                        todo.append(key)
                self.engine._save()
            async with httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(15), follow_redirects=False,
                    headers={'User-Agent': 'CrisisFusion/0.4 (local research prototype)', 'Accept': 'application/geo+json,application/json'}) as client:
                async def load(key):
                    try:
                        values = await asyncio.wait_for(PROVIDERS[key].fetch(client, at), timeout=20)
                        return key, values, None
                    except Exception as failure:
                        reason = f'HTTP {failure.response.status_code}' if isinstance(failure, httpx.HTTPStatusError) else 'Network timeout or invalid provider data'
                        return key, None, reason
                results = await asyncio.gather(*(load(k) for k in todo))
            with self.engine.lock:
                # Reset or disable during an in-flight fetch must not restore old records.
                if self.data() is data and data['enabled']:
                    for key, values, error in results:
                        cache = data['providers'][key]
                        if not cache['enabled']:
                            continue
                        cache.update(status='error' if error else 'ok', error=error)
                        if error is None:
                            previous = {e['id']: e for e in cache['events']}
                            for event in values:
                                old = previous.get(event['id'], {})
                                if old.get('geometry_loaded_at') and old.get('updated_at') == event.get('updated_at'):
                                    for field in ('geometry', 'geometry_note', 'geometry_loaded_at'):
                                        event[field] = old[field]
                            cache.update(events=values, last_success_at=now())
                        self.engine._audit('geo_provider_refresh', provider=key, status=cache['status'], count=len(cache['events']))
                    self.engine._save()
            return self.snapshot()

    async def event_geometry(self, payload):
        """On-demand NWS zone lookup, never a county-wide invented footprint."""
        async with self.refresh_lock:
            with self.engine.lock:
                self.require_enabled()
                data = self.data()
                if not data['providers']['nws']['enabled'] or not self.engine.s['settings']['internet_available']:
                    raise HTTPException(409, 'NWS provider or internet is disabled')
                event = next((e for e in data['providers']['nws']['events'] if e['id'] == payload.get('event_id')), None)
                if event is None:
                    raise ValueError('Select an existing NWS alert')
                if event.get('geometry'):
                    return self.snapshot()
                zones = event.get('affected_zones', [])
                if not zones or len(zones) > 20:
                    raise ValueError('No supported zone list, or more than 20 zones; use the original alert source')
                attempted = date(event.get('geometry_attempt_at'))
                if attempted and (datetime.now(timezone.utc)-attempted).total_seconds() < 60:
                    raise HTTPException(429, 'Please wait 60 seconds before retrying zone geometry')
                event['geometry_attempt_at'] = now()
            semaphore = asyncio.Semaphore(4)
            async with httpx.AsyncClient(transport=self.transport, timeout=10, follow_redirects=False,
                    headers={'User-Agent':'CrisisFusion/0.4 (local research prototype)','Accept':'application/geo+json'}) as client:
                async def load(url):
                    # Revalidate persisted links; never fetch operator evidence links.
                    if not re.fullmatch(r'https://api\.weather\.gov/zones/(forecast|fire|county)/CA[ZC]\d{3}', url):
                        raise ValueError('Unsupported zone URL')
                    async with semaphore:
                        document = await fetch_document(client, url)
                    g = geometry(document.get('geometry'))
                    if not g or g['type'] not in ('Polygon', 'MultiPolygon'):
                        raise ValueError('Zone polygon unavailable')
                    return [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
                try:
                    polygons = await asyncio.wait_for(asyncio.gather(*(load(z) for z in zones)), 20)
                    combined = {'type':'MultiPolygon', 'coordinates':[p for group in polygons for p in group]}
                    if len(json.dumps(combined)) > MAX_BYTES:
                        raise ValueError('Combined zone geometry too large')
                except Exception:
                    raise HTTPException(502, 'Official zone polygons could not all be loaded; no partial or invented footprint was drawn') from None
            with self.engine.lock:
                if self.data() is not data or not data['enabled'] or not data['providers']['nws']['enabled']:
                    raise HTTPException(409, 'Map state changed during zone lookup; result discarded')
                event.update(geometry=combined, geometry_loaded_at=now(), geometry_note='Official NWS affected forecast/fire zone boundaries, not an observed disaster perimeter; may extend beyond LA County')
                self.engine._audit('geo_official_zones_loaded', event_id=event['id'], zone_count=len(zones))
                self.engine._save()
            return self.snapshot()

    def save_location(self, payload):
        if set(payload)-{'call_id', 'lat', 'lon', 'accuracy_m', 'captured_at', 'consent'} or payload.get('consent') is not True:
            raise ValueError('Explicit location consent and supported fields required')
        lat = number(payload.get('lat'), -90, 90, 'lat')
        lon = number(payload.get('lon'), -180, 180, 'lon')
        accuracy = number(payload.get('accuracy_m'), 0, 100000, 'accuracy_m')
        captured = date(payload.get('captured_at'))
        age = (datetime.now(timezone.utc)-captured).total_seconds() if captured else None
        if age is None or not -30 <= age <= 300:
            raise ValueError('Location must be captured within the last 5 minutes, with timezone')
        with self.engine.lock:
            self.require_enabled()
            call_id = payload.get('call_id')
            if not isinstance(call_id, str):
                raise ValueError('call_id required')
            if call_id not in self.engine.s['active_calls']:
                raise HTTPException(409, 'Location requires a call explicitly marked active by the host')
            self.data()['caller_locations'][call_id] = {'call_id': call_id, 'lat': lat, 'lon': lon, 'accuracy_m': accuracy,
                'captured_at': captured.isoformat(), 'saved_at': now(), 'inside_county': in_county(lon, lat),
                'source': 'browser_geolocation_client_reported', 'verification': 'Device location with user consent; not independently verified; not incident location'}
            # Do not duplicate precise coordinates in immutable audit history.
            self.engine._audit('geo_device_location_saved', call_id=call_id, consent=True, source='browser_geolocation_client_reported')
            self.engine._save()
        return self.snapshot()

    def delete_location(self, call_id):
        with self.engine.lock:
            self.data()['caller_locations'].pop(call_id, None)
            self.engine._audit('geo_device_location_removed', call_id=call_id)
            self.engine._save()
        return self.snapshot()

    def save_report(self, payload):
        if set(payload)-{'call_id', 'lat', 'lon', 'label', 'note', 'source_url', 'reviewed', 'hazard_type', 'zone_radius_m', 'zone_level', 'valid_minutes'}:
            raise ValueError('Unknown report field')
        lat = number(payload.get('lat'), -90, 90, 'lat')
        lon = number(payload.get('lon'), -180, 180, 'lon')
        label = text(payload.get('label'), 200).strip()
        note = text(payload.get('note'), 2000).strip()
        reviewed = payload.get('reviewed', False)
        if not label or len(note) < 10 or type(reviewed) is not bool:
            raise ValueError('Provide an event label, evidence/review note (10+ characters), and boolean reviewed flag')
        source = link(payload.get('source_url'))
        if payload.get('source_url') and not source:
            raise ValueError('Evidence link must be a valid HTTPS URL without credentials')
        hazard_type = payload.get('hazard_type', 'other')
        if hazard_type not in {'fire','earthquake','shooting','other'}:
            raise ValueError('Unsupported incident type')
        zone = {}
        if payload.get('zone_radius_m') not in (None, ''):
            radius = number(payload['zone_radius_m'], 10, 10000, 'zone_radius_m')
            minutes = number(payload.get('valid_minutes'), 1, 1440, 'valid_minutes')
            level = payload.get('zone_level')
            if not reviewed or not source or level not in {'INFO','WATCH','HIGH','CRITICAL'}:
                raise ValueError('An operator-defined area requires an evidence link, explicit review, and a display level')
            until = (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()
            zone = {'zone_radius_m':radius, 'zone_level':level, 'valid_until':until, 'zone_expires_at':until,
                'zone_source':'local_operator_defined_unverified', 'zone_note':'人工定义的核查范围，不是官方危险区或封控边界。'}
        with self.engine.lock:
            self.require_enabled()
            call_id = payload.get('call_id')
            if not isinstance(call_id, str) or call_id not in self.calls():
                raise ValueError('Choose an existing call')
            report_id = 'report-' + uuid.uuid4().hex[:12]
            record = {'id': report_id, 'call_id': call_id, 'lat': lat, 'lon': lon, 'label': label, 'note': note,
                'source_url': source, 'reviewed': reviewed, 'created_at': now(), 'inside_county': in_county(lon, lat),
                'verification': 'Local operator marked reviewed; not official verification' if reviewed else 'Caller report, unverified',
                'synthetic': self.calls()[call_id]['input_mode'] in ('replay', 'simulated_voice'), 'hazard_type':hazard_type, **zone}
            self.data()['reports'][report_id] = record
            self.engine._audit('geo_report_added', report_id=report_id, call_id=call_id, reviewed=reviewed, note=note, source_url=source)
            self.engine._save()
        return self.snapshot()

    async def geocode_address(self, payload):
        if set(payload)-{'call_id','address','consent','revision'} or payload.get('consent') is not True:
            raise ValueError('Explicit consent is required to send the entered address to the US Census Geocoder')
        address = payload.get('address')
        if not isinstance(address, str) or not 8 <= len(address.strip()) <= 300 or any(ord(c) < 32 for c in address):
            raise ValueError('Enter a single address of 8–300 characters, including city/state or ZIP')
        address = address.strip()
        # Bind consent to the state when this request arrives, before it can
        # wait behind another call's lookup. Deleting or superseding an address
        # must invalidate queued requests as well as requests already in flight.
        with self.engine.lock:
            self.require_enabled()
            data = self.data()
            call = self.address_call(payload.get('call_id'))
            self.check_address_revision(call, payload)
            call_id, revision = call['call_id'], call.get('revision', 0)
            generation = self.address_generations.get(call_id, 0)
            epoch = self.address_epoch

        def require_current_request():
            # Both callers hold engine.lock; the checks and ensuing writes are
            # atomic with address confirmation, deletion and engine reset.
            if (self.data() is not data or not data['enabled'] or self.address_epoch != epoch
                    or self.address_generations.get(call_id, 0) != generation or self.address_call(call_id).get('revision',0) != revision):
                raise HTTPException(409, 'Call or plugin changed during lookup; result discarded. Recheck the current address.')

        async with self.address_lock:
            with self.engine.lock:
                require_current_request()
                if not self.engine.s['settings']['internet_available']:
                    raise HTTPException(409, 'Internet is disabled; manual address confirmation remains available')
                attempted = self.address_attempts.get(call_id)
                at = datetime.now(timezone.utc)
                if attempted and (at-attempted).total_seconds() < 5:
                    raise HTTPException(429, 'Wait 5 seconds before another address lookup')
                self.address_attempts[call_id] = at
                self.engine._audit('geo_address_lookup_consent', call_id=call_id, revision=revision, provider='US Census Geocoder', consent=True)
                self.engine._save()
            try:
                async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False,
                        headers={'User-Agent':'CrisisFusion/0.5 (local research prototype)'}) as client:
                    result = await asyncio.wait_for(lookup_address(client, address), 20)
            except Exception:
                raise HTTPException(502, 'Address lookup unavailable; no verified location was created. Manual confirmation is still available.') from None
            result.update(call_id=call_id, query=address, fetched_at=now(), revision=revision)
            for match in result['matches']:
                match['inside_county'] = in_county(match['lon'], match['lat'])
            with self.engine.lock:
                require_current_request()
                data['address_geocodes'][call_id] = result
                current = data['address_records'].get(call_id)
                if not current or current.get('source') == 'census_geocoder_interpolated':
                    data['address_records'].pop(call_id, None)
                    if result['status'] == 'single_match':
                        data['address_records'][call_id] = {**result['matches'][0], 'confirmed':False, 'revision':revision,
                            'matched_address':result['matches'][0]['label'], 'confirmed_at':None, 'located_at':now()}
                self.engine._audit('geo_address_lookup_result', call_id=call_id, revision=revision, status=result['status'], match_count=len(result['matches']))
                self.engine._save()
            return {**self.snapshot(), 'geocode_result':result}

    def confirm_address(self, payload):
        if set(payload)-{'call_id','label','lat','lon','accuracy_m','reviewer','note','confirmed','revision'} or payload.get('confirmed') is not True:
            raise ValueError('Explicit address confirmation required')
        lat = number(payload.get('lat'), -90, 90, 'lat')
        lon = number(payload.get('lon'), -180, 180, 'lon')
        precision = payload.get('accuracy_m')
        if precision is not None:
            precision = number(precision, 1, 100000, 'accuracy_m')
        if not all(isinstance(payload.get(k), str) for k in ('label','reviewer','note')):
            raise ValueError('Address, reviewer and evidence note required')
        label, reviewer, note = (payload[k].strip() for k in ('label','reviewer','note'))
        if not 3 <= len(label) <= 500 or not 1 <= len(reviewer) <= 100 or not 10 <= len(note) <= 2000:
            raise ValueError('Provide address, reviewer and a 10–2000 character verification note')
        with self.engine.lock:
            self.require_enabled()
            call = self.address_call(payload.get('call_id'))
            self.check_address_revision(call, payload)
            call_id = call['call_id']
            self.address_generations[call_id] = self.address_generations.get(call_id, 0) + 1
            self.data()['address_records'][call_id] = {'label':label, 'lat':lat, 'lon':lon, 'accuracy_m':precision,
                'confirmed':True, 'reviewer':reviewer, 'note':note, 'confirmed_at':now(), 'source':'operator_confirmed', 'revision':call.get('revision',0)}
            self.engine._audit('geo_address_confirmed', call_id=call_id, revision=call.get('revision',0), reviewer=reviewer, note=note,
                clarification='Local operator attestation; no independent proof or scoring change')
            self.engine._save()
        return self.snapshot()

    def delete_address(self, call_id):
        with self.engine.lock:
            self.address_generations[call_id] = self.address_generations.get(call_id, 0) + 1
            self.data()['address_records'].pop(call_id, None)
            self.data()['address_geocodes'].pop(call_id, None)
            self.engine._audit('geo_address_confirmation_removed', call_id=call_id)
            self.engine._save()
        return self.snapshot()

    def delete_report(self, report_id):
        with self.engine.lock:
            self.data()['reports'].pop(report_id, None)
            self.engine._audit('geo_report_removed', report_id=report_id)
            self.engine._save()
        return self.snapshot()


def install_routes(app, manager):
    @app.get('/api/geo/state')
    def state():
        return manager.snapshot()

    @app.post('/api/geo/config')
    def config(payload: dict):
        return manager.configure(payload)

    @app.post('/api/geo/refresh')
    async def refresh():
        return await manager.refresh()

    @app.post('/api/geo/caller-location')
    def location(payload: dict):
        return manager.save_location(payload)

    @app.post('/api/geo/event-geometry')
    async def event_geometry(payload: dict):
        return await manager.event_geometry(payload)

    @app.delete('/api/geo/caller-location/{call_id}')
    def remove_location(call_id: str):
        return manager.delete_location(call_id)

    @app.post('/api/geo/reports')
    def report(payload: dict):
        return manager.save_report(payload)

    @app.post('/api/geo/address/geocode')
    async def geocode(payload: dict):
        return await manager.geocode_address(payload)

    @app.post('/api/geo/address/confirm')
    def confirm_address(payload: dict):
        return manager.confirm_address(payload)

    @app.delete('/api/geo/address/{call_id}')
    def delete_address(call_id: str):
        return manager.delete_address(call_id)

    @app.delete('/api/geo/reports/{report_id}')
    def remove_report(report_id: str):
        return manager.delete_report(report_id)
