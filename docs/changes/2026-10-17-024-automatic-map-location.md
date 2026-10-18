# Automatic map location of the place a caller states

* Type: implementation
* Scope: `crisisfusion_map/` (`geo.py`, `geocoding.py`, `addressing.py`, `static/geo.js`, `plugin.json`, README), `dualuse/mapview.py`, `dualuse/api.py`, `dualuse/profiles.py`, `dualuse/ui.py`, `tests/test_map_autolocate.py`, `tests/test_mapview.py`, `tests/test_map_scope.py`
* Related: [map plugin](2026-10-17-011-map-plugin.md), [profile map and shadow scorer](2026-10-17-014-profile-map-and-shadow-scorer.md)

## Context

* On Sat 2026-10-17 the user reported that the desk recognizes addresses in calls, but the map cannot match them to a place.
* Live desk on port 8000, read with GET requests only, before 17:30 PT: none of the 42 calls on the map had coordinates, and no operator lookup was stored. The desk had extracted places such as `12 Oak Street`, `450 Maple Ave`, `USC`, `Pasadena` and `Los Angeles West 24th Street`.
* Two causes:
  * A call got coordinates only after an operator ticked consent, pressed the lookup button and confirmed. Nothing matched automatically.
  * The LA profile used the US Census geocoder, which matches only a number, street and city. Through the plugin's own adapter, `USC`, `Pasadena, CA` and `West 24th Street, Los Angeles, CA` returned no match. `12 Oak Street, Los Angeles, CA` returned one wrong match outside the county, in La Selva Beach. OpenStreetMap Nominatim, searched only inside LA County, matched USC, University Gateway, Pasadena, Altadena, 450 Maple Ave (Torrance) and 1200 Wilshire Blvd.

## Decision

* The user chose automatic location over keeping the button (asked at about 17:30 PT). This reverses "lookups run only on button press" for the stated place; official feeds and operator lookups still need a button.
* `GeoManager.auto_locate_once()` looks up one new place per call. It sends only the call's `location.label`, which is the place the desk extracted, never the call text. The search is bounded to the service area, and each place is sent once.
* How results are used:
  * A single match inside the area becomes an unconfirmed point (`automatic_lookup`, hollow diamond). A street or area match records its extent as the uncertainty circle, for example USC ±692 m and Pasadena ±9.7 km. An address point's uncertainty stays unknown.
  * Several matches stay candidates in the review form, without a marker. `12 Oak Street` matches four Oak Streets in LA, so the operator has to ask for the city or cross street.
  * Matches outside the area, or wider than 20 km (a whole city such as Los Angeles), are dropped.
  * When the whole label finds nothing, the places the plugin recognizes inside it are tried, most specific first. `Gateway apartment near USC, Los Angeles, ZIP 90007` falls back to `USC`.
  * An operator's lookup, confirmation or clear is never overwritten. A failed lookup is shown on the call card and retried after 60 s.
* Both line profiles now use Nominatim. The locator runs in the API's event loop, so it shares Nominatim's one-request-a-second limit with operator lookups. Locator failures appear in `/state` as `map.locate_error` and in the UI.
* Rejected:
  * Keeping the consent button and fixing only the lookup: every call would still need a manual lookup before it reaches the map.
  * A city-centre point without an extent circle: it would look like a precise location.

## Verification

* New tests, all with a mocked Nominatim: 11 in `tests/test_map_autolocate.py` and 2 in `tests/test_mapview.py`. They fail on main (`GeoManager` has no `auto_locate_once`). `tests/test_map_scope.py` now expects Nominatim for `la-211`.
* Full suite, on the branch fast-forwarded to main `0b17c61`: `bash scripts/uv-run.sh python -m pytest tests -q` in WSL, **483 passed in 83.22 s**. After rebasing onto main `3179f4c` (records 023 and 025): **493 passed in 84.66 s**.
* Live check against real Nominatim at about 17:47 PT: a test API on port 8093 ran with a snapshot of the live desk queue (`.tmp/voice-main.sqlite3`). Of 15 calls with a stated place, 8 got a marker: USC four times (including `Gateway apartment near USC, …` and `USC, near the Dorchester building`), Pasadena twice, 450 Maple Ave in Torrance, and `Los Angeles West`.
* Not located:
  * Several candidates: `12 Oak Street` twice (4 candidates), `Los Angeles West 24th Street` (5) and `洛杉矶 Main Street 125 号` (5).
  * No match: `阿尔塔迪纳`, `near the 29th Street` and `28 West Street, Los Angeles`.
* Browser check on port 8093:
  * The map draws the markers and extent circles. A card reads "Automatic lookup of “USC” (from “Gateway apartment near USC, Los Angeles, ZIP 90007”): one place in the service area; check it with the caller."
  * The review form lists the four Oak Street candidates.
  * The map page logged no console errors, and the desk UI's Incident map page shows the new disclosure with no error.
* Known wrong match: `Los Angeles West` matched an OpenStreetMap point named "West" on 9th Street in Hollywood. It is drawn as unverified. Chinese place names that OpenStreetMap does not carry, such as `阿尔塔迪纳`, find nothing.
* Deployment, Sat 2026-10-17 about 18:00 PT, at the user's request:
  * Committed as `79f5368`, fast-forwarded `main` and pushed. `origin/main` moved `667f8f2..79f5368`, which also published the unpushed team commits `a909348`, `0b17c61`, `19c7d91` and `3179f4c`.
  * Restarted API port 8000 and UI port 8501 from the main checkout, each with the old process's working directory, environment and command line. The API kept `DUALUSE_QUEUE_DB=.tmp/voice-main.sqlite3` and `DUALUSE_MAP_URL`; the UI kept `DUALUSE_MAP_URL`. Logs append to `.tmp/public-map-demo/`. This also deployed record 025 (short welcome, fixed intake), which was committed but not yet running.
  * Local checks: API `/health` returned ok, and the stored desk came back (67 calls, 10 waiting, model mode). The map status showed no sync or locate error, and UI `/_stcore/health` returned ok. Within a minute, 9 of 16 calls with a stated place were located; the new call `南加州大学，西28街` fell back to `南加州大学` and landed on USC.
  * Public checks, read only: `https://demo.211deskdemo.site/` and `/plugins/map/health` returned 200. The public map state listed 66 calls, 9 located automatically, with the Nominatim geocoder. In a browser, the public map drew the markers and showed the automatic-lookup line on the cards.
* Voice bridge, about 18:10 PT, at the user's request:
  * Port 8010 was restarted from the main checkout at `5a33d48`, which includes [record 023](2026-10-17-023-voice-partial-utterances.md)'s bridge change (`19c7d91`). It kept the old process's command line and environment, with secrets from `.env`. No phone call was in progress.
  * The old process had started at 17:36 PT, from the working tree, before `19c7d91` was committed.
  * Output now appends to `.tmp/logs/voice-8010.log`. Startup logged no error, and `/health` returned 200 locally and through the bridge's quick tunnel.
* Not verified: a phone call after the restarts.
