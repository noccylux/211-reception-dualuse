# Profile-scoped incident map and shadow CrisisFusion scorer

* Type: implementation
* Scope: `crisisfusion_map/` (geo, geocoding, addressing, static), `crisisfusion_scoring/` (vendored),
  `dualuse/profiles.py`, `dualuse/mapview.py`, `dualuse/shadow.py`, `dualuse/api.py`, `dualuse/holdqueue.py`,
  `dualuse/ui.py`, `tests/test_map_scope.py`, `tests/test_shadow.py`
* Related: [2026-10-17-011](2026-10-17-011-map-plugin.md) (map plugin), [2026-10-17-006](2026-10-17-006-twist-2-global.md) (Twist 2)

## Context

* `feature/map-plugin` drew an LA County map only, and was based on an older main.
  Twist 2 made the desk global with profiles `la-211` and `cn-12345`.
* A classmate's CrisisFusion scoring plugin (1.0.0, deterministic English/Spanish rules,
  0–100 Human Attention Index) was available as a second reading of each call.

## Decision

* Merged `feature/map-plugin` into the voice-bridge main (d6a1b85). Main's surge stop lock,
  caption and voice invariant are kept; the map resets inside the surge lock.
* The map is scoped by the active line profile, not a global overview, because real
  911/211/12345 lines route by jurisdiction. Each `Profile` has a `MapArea`: boundary,
  default view, geocoder, official feeds and the wording that names the area's city.
  * `la-211`: LA County boundary, US Census geocoder, NWS + USGS.
  * `cn-12345`: Shanghai Municipality, OpenStreetMap boundary (relation 913067, via Nominatim,
    downloaded 2026-10-17T20:16:30Z, sha256 in `crisisfusion_map/data/geo_sources.json`;
    not an official boundary), Nominatim geocoder behind the same consent button at most once
    a second, USGS only. Census covers US addresses only and NWS US weather only.
  * The city is an assumption: no global test dataset was found in `data/`, other worktrees
    or branches, so Shanghai was used pending confirmation.
* The base map stays world-wide and freely zoomable. Only the active line's calls are drawn;
  switching profile replaces the map app. A call whose coordinates fall outside the area is
  grey and dashed, labeled "outside service area — transfer"; a call without coordinates gets
  no area judgement and no guessed point.
* Replayed test calls may carry `location: {label, lat, lon}` on `POST /calls`, accepted only
  with origin `replay`. They land on the map directly, labeled synthetic replay. Phone calls
  are no longer labeled synthetic on the map.
* The CrisisFusion scorer runs as a shadow second opinion (`dualuse/shadow.py`). It receives
  only the caller's cumulative words, revision = number of caller turns; language en/es pass
  through, anything else (or any CJK text) becomes `unknown`. The operator desk shows score,
  band and open needs beside the tier; unsupported languages show "scorer covers English and
  Spanish only — human check" instead of a number. It never changes a tier or the queue order
  (new entry in `INVARIANTS`). The map card shows the band, not the score, so waiting minutes
  do not churn map revisions.
* Disagreement rule, shown in the UI: tier and band on different steps of immediate ↔
  IMMEDIATE_HUMAN (80–100); priority or unknown ↔ HUMAN_VERIFY (50–79); normal ↔
  ROUTINE_HUMAN or AUTOMATION_ELIGIBLE (0–49). Example observed: in offline mode the Spanish
  "Hay un incendio y estoy atrapado" stays UNKNOWN for us; the scorer says IMMEDIATE_HUMAN 80
  and the row is flagged for an operator check.
* Scorer and map sync errors appear in `/state` and the UI.

## Verification

* `tests/` 387 passed after the change (360 after the merge alone; main had 207).
  New: `tests/test_map_scope.py` (boundary choice and provenance, profile switch, out-of-area
  flag, lat/lon passthrough, replay-only coordinates, Nominatim not Census for China) and
  `tests/test_shadow.py` (language mapping, caller-only text and revisions, unsupported-language
  note, disagreement table, offline Spanish case, tiers/order/events unchanged, errors in `/state`).
* API 8066 + UI 8566 from this worktree (8060/8561 were taken by another session at 13:14 PT), rules mode: LA typed calls, a replay in San Francisco
  (outside) and Long Beach (inside), an 8-caller surge; then `cn-12345` with a Chinese typed call,
  an English call, replays in Pudong (inside) and Beijing (outside), a 4-caller surge. `/state`
  showed scorer values, the zh human-check note and disagreement flags; the map showed the
  Shanghai scope, `usgs` only, the Beijing marker dashed grey with the transfer label.
* Not verified: live Nominatim, Census, NWS or USGS lookups from the desk (tests use mock
  transports); model mode with the new columns; the LA County boundary file's sha256 does not
  match the value recorded in `geo_sources.json` (already so in `feature/map-plugin`).
