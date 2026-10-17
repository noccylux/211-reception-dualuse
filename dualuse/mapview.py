"""LA County incident map: the vendored CrisisFusion map plugin fed from the hold queue.

The map is a derived view. It holds no state the desk needs, so it lives in
memory, is rebuilt from the queue after an API restart, and is replaced on a
queue reset (call ids restart at call-1). The plugin never changes a tier;
the tier is passed only as a display label.
"""
import hashlib
import json
import threading
import time
from datetime import datetime, timezone

from crisisfusion_map import create_app

SYNC_INTERVAL_S = 1.0


class SwappableApp:
    """ASGI hop so a queue reset can replace the mounted map app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


def new_map_app():
    app = create_app(db_path=":memory:")
    # Enabling only shows calls on the bundled county boundary; official feeds,
    # geocoding, base tiles and device location stay behind their own buttons.
    app.state.geo.configure({"enabled": True})
    return app


def call_payload(call: dict) -> dict:
    """One snapshot call as a map plugin call, without the revision."""
    x = call.get("extraction") or {}
    payload = {
        "call_id": call["call_id"],
        "text": "\n".join(call["transcript"]),
        "language": call["language"],
        # Injected demo callers are labeled synthetic on the map, like on the desk.
        "input_mode": "host" if call["origin"] == "live" else "replay",
        "timestamp": datetime.fromtimestamp(call["arrival"], timezone.utc).isoformat(),
        "priority_assessment": {"category": call["tier"].upper(), "policy_version": "dualuse-tier-rules"},
    }
    if x.get("location"):
        payload["location"] = {"label": x["location"], "source": "caller_statement"}
    return payload


class MapSync:
    """Pushes changed calls into the map; a new revision only when content changes."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.mounted = SwappableApp(new_map_app())
        self.lock = threading.Lock()
        self.pushed: dict[str, tuple[str, int]] = {}  # call_id -> (fingerprint, revision)
        self.status = {"synced_at": None, "error": None, "calls": 0}
        self._stop = threading.Event()
        self._thread = None

    def sync_once(self):
        calls = self.snapshot()["calls"]
        with self.lock:
            store = self.mounted.app.state.store
            for call in calls:
                payload = call_payload(call)
                fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                last, revision = self.pushed.get(call["call_id"], (None, 0))
                if fingerprint == last:
                    continue
                store.upsert_call({**payload, "revision": revision + 1})
                self.pushed[call["call_id"]] = (fingerprint, revision + 1)
            self.status.update(synced_at=time.time(), error=None, calls=len(self.pushed))

    def reset(self):
        with self.lock:
            old = self.mounted.app
            self.mounted.app = new_map_app()
            self.pushed.clear()
            old.state.store.close()

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
