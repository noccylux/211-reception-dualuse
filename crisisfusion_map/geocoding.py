"""Explicit-consent US Census address lookup; match != structure or caller proof.

https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html
Coordinates are TIGER address-range interpolation, never rooftop accuracy claims.
"""
from __future__ import annotations

import json
import math

URL = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
SOURCE = 'https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html'


async def lookup(client, address):
    async with client.stream('GET', URL, params={'address':address,'benchmark':'Public_AR_Current','format':'json'}) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 2_000_000:
                raise ValueError('Address response exceeded limit')
    data = json.loads(body)
    values = data.get('result', {}).get('addressMatches')
    if not isinstance(values, list) or len(values) > 20:
        raise ValueError('Invalid or excessive address matches')
    matches = []
    for item in values:
        xy = item.get('coordinates', {})
        lon, lat = xy.get('x'), xy.get('y')
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (lat, lon)) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError('Invalid geocoder coordinates')
        label = item.get('matchedAddress')
        if not isinstance(label, str) or not label.strip() or len(label) > 500:
            raise ValueError('Invalid matched address')
        matches.append({'label':label, 'lat':lat, 'lon':lon, 'source':'census_geocoder_interpolated',
            'accuracy_m':None, 'source_url':SOURCE, 'benchmark':'Public_AR_Current',
            'precision_note':'TIGER street-range interpolation; may match a range without an actual building. Not proof of caller presence.'})
    return {'status':'single_match' if len(matches)==1 else 'multiple_matches' if matches else 'no_match',
        'matches':matches, 'source_url':SOURCE, 'benchmark':'Public_AR_Current',
        'detail':'An address-range match does not prove the building exists or that the caller or incident is there; verify with the caller.'}
