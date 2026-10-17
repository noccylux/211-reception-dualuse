"""Explicit-consent address lookup; match != structure or caller proof.

The service area picks the geocoder: the US Census Geocoder covers US addresses
only, so areas elsewhere use OpenStreetMap Nominatim behind the same consent
button. Coordinates are interpolated or gazetteer points, never rooftop accuracy claims.
"""
from __future__ import annotations

import asyncio
import json
import math
import time


async def read_json(client, url, params):
    async with client.stream('GET', url, params=params) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 2_000_000:
                raise ValueError('Address response exceeded limit')
    return json.loads(body)


def checked_point(lat, lon):
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (lat, lon)) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid geocoder coordinates')
    return lat, lon


def checked_label(label):
    if not isinstance(label, str) or not label.strip() or len(label) > 500:
        raise ValueError('Invalid matched address')
    return label


def result(matches, source):
    return {'status':'single_match' if len(matches)==1 else 'multiple_matches' if matches else 'no_match',
        'matches':matches, 'source_url':source,
        'detail':'An address match does not prove the building exists or that the caller or incident is there; verify with the caller.'}


class Census:
    NAME = 'US Census Geocoder'
    NOTE = 'US addresses only. Results may be interpolated along the street and are not a measured position or accuracy.'
    SOURCE_ID = 'census_geocoder_interpolated'
    URL = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
    SOURCE = 'https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html'

    @classmethod
    async def lookup(cls, client, address, bbox=None):
        data = await read_json(client, cls.URL, {'address':address,'benchmark':'Public_AR_Current','format':'json'})
        values = data.get('result', {}).get('addressMatches')
        if not isinstance(values, list) or len(values) > 20:
            raise ValueError('Invalid or excessive address matches')
        matches = []
        for item in values:
            xy = item.get('coordinates', {})
            lat, lon = checked_point(xy.get('y'), xy.get('x'))
            matches.append({'label':checked_label(item.get('matchedAddress')), 'lat':lat, 'lon':lon, 'source':cls.SOURCE_ID,
                'accuracy_m':None, 'source_url':cls.SOURCE, 'benchmark':'Public_AR_Current',
                'precision_note':'TIGER street-range interpolation; may match a range without an actual building. Not proof of caller presence.'})
        return {**result(matches, cls.SOURCE), 'benchmark':'Public_AR_Current'}


class Nominatim:
    NAME = 'OpenStreetMap Nominatim geocoder'
    NOTE = 'World-wide OpenStreetMap gazetteer; at most one request per second. A match is an OSM point, not a measured position or accuracy.'
    SOURCE_ID = 'nominatim_osm'
    URL = 'https://nominatim.openstreetmap.org/search'
    SOURCE = 'https://operations.osmfoundation.org/policies/nominatim/'
    MIN_INTERVAL_S = 1.0  # Nominatim usage policy: an absolute maximum of 1 request per second
    _lock = asyncio.Lock()
    _last = 0.0

    @classmethod
    async def lookup(cls, client, address, bbox=None):
        async with cls._lock:
            wait = cls._last + cls.MIN_INTERVAL_S - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            cls._last = time.monotonic()
            params = {'q':address, 'format':'jsonv2', 'limit':5}
            if bbox:
                params['viewbox'] = ','.join(str(v) for v in bbox)  # prefer, not restrict: out-of-area matches stay visible
            values = await read_json(client, cls.URL, params)
        if not isinstance(values, list) or len(values) > 20:
            raise ValueError('Invalid or excessive address matches')
        matches = []
        for item in values:
            try:
                lat, lon = checked_point(float(item.get('lat')), float(item.get('lon')))
            except (TypeError, ValueError):
                raise ValueError('Invalid geocoder coordinates') from None
            matches.append({'label':checked_label(item.get('display_name')), 'lat':lat, 'lon':lon, 'source':cls.SOURCE_ID,
                'accuracy_m':None, 'source_url':cls.SOURCE, 'osm_type':str(item.get('osm_type', ''))[:20],
                'precision_note':'OpenStreetMap gazetteer point (© OpenStreetMap contributors, ODbL); may be a street or area centre. Not proof of caller presence.'})
        return result(matches, cls.SOURCE)


GEOCODERS = {'census': Census, 'nominatim': Nominatim}
