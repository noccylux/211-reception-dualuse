"""Incident map for the active line: the vendored CrisisFusion map plugin fed from the hold queue.

The map is a derived view. It holds no state the desk needs, so it lives in
memory, is rebuilt from the queue after an API restart, and is replaced on a
queue reset (call ids restart at call-1) or when the desk switches line
profile. Each profile brings its own service area (boundary, view, geocoder,
official feeds); only that line's calls are drawn, and a call located outside
the area is flagged for transfer, because real lines route by jurisdiction.
The plugin never changes a tier; the tier and the shadow scorer's band are
passed only as display labels.

The place the desk extracted from the caller's words is looked up
automatically, inside the service area only, so a call reaches the map
without an operator click. Only that place text leaves the desk, never the
transcript. A single match is drawn as unverified until a person confirms it.
"""
import asyncio
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from crisisfusion_map import create_app
from dualuse.profiles import PROFILES

SYNC_INTERVAL_S = 1.0
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class SwappableApp:
    """ASGI hop so a queue reset or profile switch can replace the mounted map app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


def map_hosts() -> tuple[str, ...]:
    """Loopback, plus the public host of DUALUSE_MAP_URL when a tunnel serves the map to outside browsers."""
    url = os.environ.get("DUALUSE_MAP_URL")
    if not url:
        return LOOPBACK_HOSTS
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"DUALUSE_MAP_URL must be an http(s) URL with a host, got {url!r}")
    return LOOPBACK_HOSTS + (parts.hostname,)


def new_map_app(profile: str):
    app = create_app(db_path=":memory:", allowed_hosts=map_hosts(), area=PROFILES[profile].map_area.spec())
    # Enabling only shows calls on the bundled boundary; official feeds,
    # geocoding, base tiles and device location stay behind their own buttons.
    app.state.geo.configure({"enabled": True})
    return app


def call_payload(call: dict, shadow: dict | None = None) -> dict:
    """One snapshot call as a map plugin call, without the revision."""
    x = call.get("extraction") or {}
    policy = "dualuse-tier-rules"
    if shadow and shadow.get("band"):
        # The band, not the score: the score moves every waiting minute and would churn map revisions.
        policy += f" · shadow scorer band {shadow['band']} (display only)"
    payload = {
        "call_id": call["call_id"],
        "text": "\n".join(call["transcript"]),
        "language": call["language"],
        # Typed and phone callers are people; injected and replayed callers are labeled synthetic on the map.
        "input_mode": "host" if call["origin"] in ("live", "phone") else "replay",
        "timestamp": datetime.fromtimestamp(call["arrival"], timezone.utc).isoformat(),
        "priority_assessment": {"category": call["tier"].upper(), "policy_version": policy},
    }
    if call.get("location"):
        payload["location"] = {**call["location"], "source": "test_data_replay"}
    elif x.get("location"):
        payload["location"] = {"label": x["location"], "source": "caller_statement"}
    return payload


class MapSync:
    """Pushes the active line's changed calls into the map; a new revision only when content changes."""

    def __init__(self, snapshot, shadow=None):
        self.snapshot = snapshot
        self.shadow = shadow or (lambda call_id: None)
        self.profile = snapshot()["profile"]
        self.mounted = SwappableApp(new_map_app(self.profile))
        self.lock = threading.Lock()
        self.pushed: dict[str, tuple[str, int]] = {}  # call_id -> (fingerprint, revision)
        self.status = {"synced_at": None, "error": None, "locate_error": None, "calls": 0, "other_lines": 0,
                       "profile": self.profile, "area": PROFILES[self.profile].map_area.name}
        self._stop = threading.Event()
        self._thread = None

    def _replace(self, profile: str):
        old = self.mounted.app
        self.mounted.app = new_map_app(profile)
        self.pushed.clear()
        self.profile = profile
        self.status.update(profile=profile, area=PROFILES[profile].map_area.name, calls=0)
        old.state.store.close()

    def sync_once(self):
        snapshot = self.snapshot()
        with self.lock:
            if snapshot["profile"] != self.profile:
                self._replace(snapshot["profile"])
            calls = [c for c in snapshot["calls"] if c["profile"] == self.profile]
            store = self.mounted.app.state.store
            for call in calls:
                payload = call_payload(call, self.shadow(call["call_id"]))
                fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                last, revision = self.pushed.get(call["call_id"], (None, 0))
                if fingerprint == last:
                    continue
                store.upsert_call({**payload, "revision": revision + 1})
                self.pushed[call["call_id"]] = (fingerprint, revision + 1)
            # A new revision of an already located place keeps its point without another lookup.
            self.mounted.app.state.geo.apply_auto_lookups()
            self.status.update(synced_at=time.time(), error=None, calls=len(self.pushed),
                               other_lines=len(snapshot["calls"]) - len(calls))

    async def locate_forever(self):
        """Looks up one new stated place per interval in the server's event loop, where the
        geocoder's rate limit (Nominatim allows one request a second) is shared with operator lookups."""
        while True:
            await asyncio.sleep(SYNC_INTERVAL_S)
            try:
                await self.mounted.app.state.geo.auto_locate_once()
                self.status["locate_error"] = None
            except Exception as error:
                # Kept apart from the sync error, which each successful sync clears.
                self.status["locate_error"] = f"{type(error).__name__}: {getattr(error, 'detail', error)}"

    def reset(self):
        with self.lock:
            self._replace(self.snapshot()["profile"])

    def _run(self):
        while not self._stop.wait(SYNC_INTERVAL_S):
            try:
                self.sync_once()
            except Exception as error:
                # Surfaced in /state so the UI shows a stale map instead of hiding it.
                self.status["error"] = f"{type(error).__name__}: {getattr(error, 'detail', error)}"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="map-sync", daemon=True)
        self._thread.start()

    def stop(self):
        # The in-memory store stays open: it dies with the process, and a test
        # client may start the app again.
        self._stop.set()
        if self._thread:
            self._thread.join()
