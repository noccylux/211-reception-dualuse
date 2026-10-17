# Serve the incident map to public visitors through a browser-facing URL

* Type: implementation
* Scope: `dualuse/ui.py`, `dualuse/mapview.py`, `tests/test_ui.py`, `tests/test_mapview.py`, `docs/architecture.md`, `README.md`
* Related: [main release](2026-10-17-020-main-release.md)

## Context

* On Sat 2026-10-17 the public desk at `https://demo.211deskdemo.site/` could not show the incident map. The map would help the presentation.
* The map does not load for outside visitors, for three reasons:
  * The UI built the iframe from `DUALUSE_API_URL` (`http://localhost:8000`), the server-side API address. An outside browser resolves that address to its own machine, and an https page blocks the http frame.
  * The named Cloudflare tunnel sends `demo.211deskdemo.site`, `www.` and the apex to `localhost:8501` only, so `/plugins/map/` reaches Streamlit, not the API. This was read from the local cloudflared `/config` endpoint.
  * The map plugin accepts loopback `Host` headers only, and a tunnel keeps the public `Host`.

## Decision

* Add `DUALUSE_MAP_URL`, the public URL whose `/plugins/map/` path reaches the API:
  * The UI uses it for the map frame. When it is unset or empty, the frame uses `DUALUSE_API_URL` as before.
  * `new_map_app` adds its hostname to the map's allowed hosts, next to loopback. A malformed value stops API startup with a `ValueError`.
* It is a launch-time environment variable for both processes. The UI does not read `.env`, so the variable is not set there; otherwise the API and the UI could disagree.
* The map's mutation check (`Origin` equal to `scheme://host`) is unchanged. Tunnel connections reach WSL from `127.0.0.1`, which uvicorn trusts by default for `X-Forwarded-Proto`. The public HTTPS Origin and CSRF check was verified after deployment below.
* The tunnel route is a separate step in the Cloudflare dashboard. Add `demo.211deskdemo.site`, path `^/plugins/map/`, service `http://localhost:8000`, ordered above the existing `demo.211deskdemo.site` rule. Only the map path is exposed, not `/reset` or `/mode`. A separate `map.` hostname with the same path rule is the fallback if rules cannot be reordered.
* Rejected: a relative frame URL. It would break `localhost:8501`, where `/plugins/map/` is Streamlit. Also rejected: choosing the frame URL from each viewer's `Host`. That adds logic, and every public hostname (www, apex, quick tunnel) would then need its own route.
* With the variable set, local viewers also load the map through the public URL, so the local map then needs the tunnel to be online.

## Verification

* New tests:
  * The map accepts reads and a token-and-Origin-checked POST on the public host. Loopback still works, and an unlisted host gets 403.
  * Without the variable, only loopback is accepted.
  * Malformed values fail.
  * The UI frame uses the variable, and falls back to `DUALUSE_API_URL` when it is unset or empty.
* Full suite, `bash scripts/uv-run.sh python -m pytest tests -q` in WSL: **463 passed in 63.32 s** (455 before plus 8 new).
* On Sat 2026-10-17 at approximately 16:46 PT, after the user moved the first map route to `demo`, the public map returned the plugin's Host-denied 403, confirming it reached the API.
* Restarted only API port 8000 and UI port 8501 through the WSL launcher, preserving their existing environment and launch arguments and adding `DUALUSE_MAP_URL=https://demo.211deskdemo.site` to both. Confirmed the variable in both running processes. Logs: `.tmp/public-map-demo/api.log` and `.tmp/public-map-demo/ui.log`.
* Both local health endpoints passed. Public `/plugins/map/health` and `/plugins/map/api/geo/state` returned 200. A config POST with the existing `enabled` value, public HTTPS Origin and CSRF token also returned 200 without changing the setting.
* Browser check: the public desk's Incident map workspace loaded the CrisisFusion iframe at `https://demo.211deskdemo.site/plugins/map/?line=la-211`, including the service-area map controls and call assessments.
* After restart, reran `bash scripts/uv-run.sh python -m pytest tests -q` in WSL: **463 passed in 65.44 s**.
* Other public hostnames were not separately browser-tested. The UI uses the same absolute demo map URL for every entry hostname; direct map paths on www or the apex would require their own routes and explicitly allowed hosts.
