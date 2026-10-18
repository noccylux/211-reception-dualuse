English · [中文](README.zh-CN.md)

# CrisisFusion map plugin 1.0.0

This is a standalone Python / ASGI plugin that can be moved to another host. It ships with its own web page, HTTP API, address detector, area matcher, LA County boundary and Leaflet static assets. **It does not require the scorer, the voice plugin or the original CrisisFusion main application.** It can run on its own or be mounted under an existing FastAPI / Starlette host and shown in an iframe.

It takes the full call text and a revision number from the host, keeps the address as spoken, the verification evidence and its source; it draws a different shape for each address status and colors it by sourced, currently valid area matches. It never computes or changes a call's priority. The host may additionally supply a scoring summary, which is shown for display only.

## Installation and standalone run

Requires Python 3.11 or later. Install it in your own project's virtual environment; an offline machine needs the dependency wheels prepared in advance.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m crisisfusion_map --host 127.0.0.1 --port 8812 --db work/map.sqlite3
```

If you were given a wheel, use `python -m pip install crisisfusion_map-1.0.0-py3-none-any.whl` and then run the same CLI. Open the [local map page](http://127.0.0.1:8812/) and first click "Enable map plugin". The "Connected call / standalone test" box at the top of the page lets you save a call's full text by hand. The plugin is off by default; loading the page, enabling the plugin or saving a call never requests official data, address services or device location on its own.

The default CLI database is `work/map.sqlite3`, relative to the current working directory. `create_app()` defaults to an in-memory database; a production host should name its own file explicitly. Only **a single process with a single worker** is supported; do not let several instances write the same SQLite file. Text, precise locations and verification records are stored in plain text; the host is responsible for file permissions, backups and retention. There are no automatic background downloads, tracking, paid API calls or external telemetry.

## Mounting under another host

```python
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI
from crisisfusion_map import create_app

map_app = create_app(db_path="work/map.sqlite3")

@asynccontextmanager
async def lifespan(host):
    # Starlette 不会自动启动挂载子应用的生命周期，宿主明确管理。
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(map_app.router.lifespan_context(map_app))
        yield

host = FastAPI(lifespan=lifespan)
host.mount("/plugins/map", map_app)

# 已经受宿主验证的通话事件可直接在服务端写入，不经过 HTTP。
map_app.state.store.upsert_call({
    "call_id": "call-123", "revision": 1,
    "text": "I am at 123 Main St, Los Angeles.",
    "language": "en", "input_mode": "host",
})
map_app.state.store.set_active_call("call-123", active=True)
```

(The two comments in the snippet say: Starlette does not start a mounted sub-application's lifespan on its own, so the host manages it explicitly; and call events the host has already validated can be written server-side without going through HTTP.)

Run `uvicorn your_module:host --host 127.0.0.1 --port 8000`. The page lives at `/plugins/map/`; static assets and the API resolve under the current prefix, with no dependency on the original site's navigation, DOM or voice globals. The host can embed it:

```html
<iframe src="/plugins/map/" title="通话地图" style="width:100%;height:1000px;border:0" allow="geolocation 'self'"></iframe>
```

Browser device location needs HTTPS or localhost, a Permissions-Policy that allows it on both the page and the host, and a click plus consent from the user. Do not open geolocation to untrusted cross-site iframes. The iframe does not read host memory and does not accept data from arbitrary sites via `postMessage`; the host updates it through the API or Python methods below.

A public domain needs an explicit `create_app(allowed_hosts=["console.example.com"])` plus authentication, authorization, HTTPS and access control at the host layer. The plugin only performs Host / same-origin / CSRF checks; **the CSRF token is readable by any same-origin page and is not user authentication**. Do not expose the development CLI directly to the public internet; a reverse proxy must set the trusted scheme/Host correctly and must not blindly trust external forwarded headers.

## Call input contract

`app.state.store.upsert_call(payload)` and `POST /api/geo/calls` take the same fields. Send the current **complete text snapshot** every time, not just the new sentences; the host is responsible for assembling voice fragments into the full text in order.

```json
{
  "call_id": "call-123",
  "revision": 1,
  "text": "I am at 123 Main St, Los Angeles.",
  "language": "en",
  "timestamp": "2026-10-17T18:00:00Z",
  "event_id": "voice-event-001",
  "input_mode": "browser_voice",
  "location": {"label": "123 Main St, Los Angeles"},
  "priority_assessment": {"category": "HIGH", "score": 82, "policy_version": "host-policy-v1"}
}
```

| Field | Constraint |
| --- | --- |
| `call_id` | Required, 1–128 characters, starts with a letter or digit; letters, digits, dots, underscores, colons and hyphens allowed |
| `revision` | Required integer from 1 to 2147483647; each new change must increase it, gaps are allowed |
| `text` | Required string, at most 100000 characters, may be empty; original whitespace and line breaks are kept intact |
| `language` | Defaults to `und`, at most 32 characters; the address rules mainly cover US addresses and some English, Spanish and Chinese phrasings |
| `timestamp` | Optional ISO 8601 time with time zone, kept as `source_timestamp`; the receive time is used when absent |
| `event_id` | Optional, 1–512 characters; a repeated ID must not carry different data |
| `input_mode` | Defaults to `host`; `browser_voice` marks an unverified transcript, `replay` / `simulated_voice` mark synthetic input |
| `location` | Optional object; only `label`, `lat`, `lon`, `source`, `accuracy_m` are supported; it is the reported incident location, not device GPS; lat and lon must be given together |
| `priority_assessment` | Optional; only `category`, a `score` from 0–100 and `policy_version` are accepted; the scorer is neither imported nor called |

The same current revision with all normalized input fields identical returns `duplicate: true` and adds no history. An already accepted `event_id` carrying exactly the same data still returns a duplicate success with `event_revision`, even when the call has since moved to a higher revision, and does not roll the current text back; this lets the host replay from a checkpoint. The same revision with different content, an old revision never received before, or the same `event_id` with different data all return 409. Even a higher revision with identical content is a new verification version: the old manual confirmation expires and the front end asks for a fresh review. The returned `upsert_result.call.revisions` holds the full history, up to 100 revisions per call and 1000 calls per database; reaching a limit is refused explicitly, never by silently dropping the original text. On a 409 or any other failure the host should keep its consumer cursor and the original event, resolve the version conflict or archive for capacity, and then retry; it must not skip the event.

`set_active_call(call_id, active=True)` only declares the call lifecycle as the host knows it and is not a location authorization. Call `active=False` when the call ends. All active flags are cleared on process restart so an old call is not still treated as in progress.

## HTTP usage and common endpoints

First `GET /api/geo/state` to obtain `csrf_token` and `store_id`. `store_id` is a UUID generated and persisted when the database is initialized: it survives restarts of the same database, and a new database gets a new ID. A host relay should bind its consumer cursor to `store_id` and, when it finds the same URL now serves a different database, replay history or re-initialize the cursor, so an old cursor does not skip events the new database has not received. Every write request needs the Origin of the actual page (scheme + host + port, **without the plugin path**) and `X-CrisisFusion-Geo`. CORS is not opened for cross-origin browser calls; for cross-service integration, call the Python methods from the protected host server, or have the host proxy same-origin. The example below targets the standalone port; when mounted, change only `base`:

```python
import httpx

origin = "http://127.0.0.1:8812"
base = origin  # 挂载例：origin + "/plugins/map"
with httpx.Client() as client:
    token = client.get(base + "/api/geo/state").json()["csrf_token"]
    client.headers.update({"Origin": origin, "X-CrisisFusion-Geo": token})
    client.post(base + "/api/geo/config", json={"enabled": True}).raise_for_status()
    client.post(base + "/api/geo/calls", json={
        "call_id": "call-123", "revision": 1,
        "text": "I am at 123 Main St, Los Angeles.", "language": "en"
    }).raise_for_status()
    client.post(base + "/api/geo/calls/call-123/active", json={"active": True}).raise_for_status()
```

(The comment on `base` reads: mounted example, `origin + "/plugins/map"`.)

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Plugin version and liveness |
| `GET /api/geo/state` | Current map, data sources, call addresses and area assessments, token |
| `POST /api/geo/calls` | Full call snapshot; returns the map state and `upsert_result` |
| `POST /api/geo/calls/{call_id}/active` | `{"active":true}` / `false`; returns the map state and `activity_result` |
| `POST /api/geo/config` | `{"enabled":true,"providers":{"nws":true,"usgs":true}}`; fields may be omitted as needed |
| `POST /api/geo/refresh` | Explicit manual fetch of official sources; at least 60 seconds between fetches per source |
| `POST /api/geo/event-geometry` | `{"event_id":"existing NWS event ID"}`; fetches the official area on demand, arbitrary URLs are refused |
| `POST /api/geo/address/geocode` | `{call_id,revision,address,consent:true}`; sends only the entered address, keeps the query result and its accuracy limits |
| `POST /api/geo/address/confirm` | `{call_id,revision,label,lat,lon,reviewer,note,confirmed:true,accuracy_m?}`; note is at least 10 characters |
| `DELETE /api/geo/address/{call_id}` | Clears the manual confirmation and geocoding candidates, keeps the original text |
| `POST /api/geo/caller-location` | `{call_id,lat,lon,accuracy_m,captured_at,consent:true}`; accepts only calls the host marks active and browser fixes under 5 minutes old |
| `DELETE /api/geo/caller-location/{call_id}` | Deletes the precise device location; the audit log does not copy the coordinates |
| `POST /api/geo/reports` | Saves a local manual report; fields as in the example below |
| `DELETE /api/geo/reports/{report_id}` | Deletes a manual report |

Manual report example; without a radius only the report point is saved:

```json
{"call_id":"call-123","label":"来电报告的事件","lat":34.02,"lon":-118.285,
 "note":"操作员通过复述地址核查，范围由操作员记录，尚无官方警戒边界。",
 "source_url":"https://example.org/evidence","reviewed":true,"hazard_type":"shooting",
 "zone_radius_m":200,"zone_level":"HIGH","valid_minutes":30}
```

(In the example, `label` is "Incident reported by caller" and `note` says the operator verified the address by reading it back, the extent was recorded by the operator, and there is no official alert boundary yet.)

A manual zone radius is 10–10000 m and valid for 1–1440 minutes; a zone requires an HTTPS evidence link, a verification note and `reviewed:true`. The level must be one of `INFO/WATCH/HIGH/CRITICAL`. The plugin does not fetch the evidence link and does not certify it as official; the circle is always marked operator-defined and unofficial. Do not use the example evidence URL for real verification.

## How to read the map

| Dimension | Representation and rule |
| --- | --- |
| No coordinates | Stays in the per-call list; no fake position at the county center |
| Hollow diamond | Candidate coordinates not yet confirmed, including optional Census interpolation results |
| Solid circle | Manually confirmed for the current revision, with reviewer and evidence kept; it does not mean the system proved the real on-site location |
| Cross | Conflicting addresses, needs manual review |
| Gray / blue / yellow / orange / red | UNKNOWN / INFO / WATCH / HIGH / CRITICAL, this prototype's area attention level, independent of the call score |
| Blue device dot with accuracy circle | This page's device location, authorized once by the user for an active call; a separate layer that cannot locate the remote phone |
| Dashed manual circle | Unofficial operator-assumed extent; once expired it no longer contributes to the current area level |

A current NWS Actual Alert/Update needs a valid time window, area geometry, a cache fetched successfully within the last 5 minutes and usable CAP fields; Severity maps Minor→INFO, Moderate→WATCH, Severe→HIGH, Extreme→CRITICAL. Urgency accepts only Immediate / Expected; Certainty of Possible / Unlikely caps the level at WATCH, Observed / Likely keeps the mapped level. Cancelled, expired, not yet effective, missing fields or a stale cache yield no current valid level. This follows the [CAP 1.2 field specification](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.pdf); **the color grading is this product's prototype rule, not an official unified emergency classification**.

Point inside polygon, accuracy circle fully contained, and possible overlap near the boundary are each stated separately. A 25 m prototype boundary guard distance is used; unknown coordinate accuracy does not mean the coordinates are exact. With several valid matches the highest background level wins. Unconfirmed coordinates give only a conditional match; a conflicting or outdated manual confirmation makes the current summary return UNKNOWN. No match / gray never means safe. Synthetic manual zones do not enter the current area level.

**There is no measured address accuracy, and no invented percentage is reported.** The unit tests for the address rules are functional checks, not an overall accuracy evaluation on real calls. Census uses TIGER street-range interpolation; a range may include unbuilt house numbers, and a successful match does not prove the caller is there, see the [Census geocoder documentation](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html). A query sends the address currently in the input box only with an explicit `consent:true`; the full call text is never sent to the geocoding service.

Official coverage is limited to NWS and USGS. An NWS Red Flag Warning is a [fire-weather condition](https://www.weather.gov/safety/wildfire-ww), not a fire perimeter. USGS provides only epicenters of M≥2.5 events within LA County in the last 7 days; an epicenter cannot tell local shaking intensity or the damage extent, and it misses shaking felt locally from epicenters outside the county; see the [USGS note on magnitude and intensity](https://www.usgs.gov/programs/earthquake-hazards/earthquake-magnitude-energy-release-and-shaking-intensity). Full official fire perimeters, evacuation zones, ShakeMap or real-time shooting alert areas are not connected. Every source link, fetch time, expiry and cache failure is displayed.

## Network and data licenses

NWS / USGS are requested only on manual refresh, from fixed official HTTPS endpoints; area loading accepts only NWS's fixed CA zone URLs; Census is called only on an explicit address query. The base map is off by default; when ticked, the browser requests OpenStreetMap tiles for the current view, and the third party sees the network IP and the map view; call text and custom markers are not sent. There is no pre-download or offline tile scraping.

The LA County boundary and its source record are stored in the package's `data/`. Leaflet 1.9.4 JS, CSS and its BSD license are in `static/vendor/leaflet/`; the map keeps the LA County / OSM attribution. `plugin.json` is the machine-readable declaration for host integration. The network source rules and fetch-time constraints are kept; when an official data service changes, re-validate the adapter.

## Automatic lookup (host-driven; added in this repository)

The plugin makes no automatic requests unless its host calls `await app.state.geo.auto_locate_once()`. The 211 desk calls it once a second.

* Each call sends at most one new place to the area's geocoder: a call's `location.label`, never its `text`, with the search bounded to the service area. Each place's result is cached, so a place is sent once.
* Only matches inside the service area and narrower than 20 km count, so a whole city such as Los Angeles locates nothing. Matches within 150 m of the first are one place.
* A single match becomes an unconfirmed point (`source: automatic_lookup`, hollow diamond). For a street or area match, its extent is recorded as the uncertainty. Several matches stay candidates in the review form.
* If the whole label finds nothing, the places recognized inside it are tried, most specific first; for example "Gateway apartment near USC" falls back to "USC".
* An operator's lookup, confirmation or clear is never replaced. A failed lookup is shown on the call card and retried after 60 s.
* `app.state.geo.apply_auto_lookups()` re-applies cached results to new revisions without a request.

## Calls in progress (added in this repository)

Calls the host marks active with `set_active_call` are listed newest first in a strip above the map, each with "Show on map" when it has a point. Their cards come first with an "In progress" tag, and their markers carry a teal ring and sit on top. The 211 desk marks a call active while its caller can still speak.

## Verification

```powershell
python -m pip install ".[test]"
python -m pytest -q
```

The tests cover address candidates/conflicts, polygons and boundaries, caching and validity windows, Census receiving only an explicit address, revision idempotence and outdated confirmations, discarding late query results, device authorization, standalone import, SQLite restart and the ASGI mount prefix. All network access is mocked; no real GPS, microphone or external paid service is called. Real on-site recognition accuracy, complete hazard coverage and large-scale multi-tenant deployment are outside the scope of this verification.
