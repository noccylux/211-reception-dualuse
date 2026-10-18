# Calls in progress first on the incident map

* Type: implementation
* Scope: `dualuse/mapview.py`, `crisisfusion_map/static/geo.js`, `crisisfusion_map/static/geo.css`, `crisisfusion_map/README.md`, `tests/test_mapview.py`
* Related: [automatic map location](2026-10-17-024-automatic-map-location.md)

## Context

* On Sat 2026-10-17 at about 18:15 PT the user asked whether the map can show the address of the call in progress, during a live phone call (`call-69`).
* `call-69`'s address was already on the map: the desk extracted `3335 South Figueroa Street, Los Angeles`, and the automatic lookup placed an unverified point at University Gateway. Finding it was the problem:
  * The desk never marked any call active in the map, so the plugin's active-call list was empty.
  * Its card sat in call order among 69 others, and its marker looked like any other.

## Decision

* The desk's map sync marks a call active while its caller can still speak, which is the `waiting`, `connecting` and `handed_off` statuses that `HoldQueue.say` accepts. It clears the flag when the call ends. The plugin's `set_active_call` is lifecycle only; it is not location consent.
* The map page:
  * shows "Calls in progress" above the map, newest first, at most five rows, each with its place, address status, "Show on map" and "Review / edit address";
  * lists live calls' cards first with an "In progress" tag;
  * draws their markers on top with a teal ring. Red already means critical area risk on this map.
* Not done: automatically panning the map to a new call. The page re-renders every 5 s and would fight the operator's own panning.

## Verification

* New test: a waiting call is active on the map and an ended call is not; after hang-up neither is. It fails on main `7a7549f` and passes with the change.
* Full suite: `bash scripts/uv-run.sh python -m pytest tests -q` in WSL, **494 passed in 86.88 s**.
* Browser check on a test server (port 8093) with a snapshot of the live desk queue, plus one typed rules-mode test call: "There is smoke at 3650 McClintock Ave and I am trapped".
  * The strip read "Calls in progress (11), newest first". The test call came first with its matched place (Olin Hall of Engineering, 3650 McClintock Avenue), then `call-41` at USC.
  * Two live markers carried the ring, and "Show on map" zoomed to them.
* Observed: 10 of the snapshot's in-progress calls are old test calls still waiting in the queue, such as typed callers who closed the page. The desk cannot tell that they left, so the strip lists them too.
