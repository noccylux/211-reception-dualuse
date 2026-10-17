"""Small single-process store. No dependency on CrisisFusion core or voice."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


def now():
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """Persist map data and host-supplied calls in a dedicated SQLite file.

    One process owns this store; workers >1 and shared DB writers unsupported.
    Public methods return detached values. A revision is a full call snapshot.
    """
    def __init__(self, db_path=":memory:"):
        self.lock = threading.RLock()
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS map_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        row = self.connection.execute("SELECT payload FROM map_state WHERE id=1").fetchone()
        self.s = json.loads(row[0]) if row else {"calls": {}, "active_calls": {}, "event_ids": {}, "settings": {"internet_available": True, "map_available": True}, "audit": []}
        self.s.setdefault("event_ids",{})
        if not self.s.get("store_id"):
            self.s["store_id"] = str(uuid.uuid4())
        # Active sessions never survive a process restart; the host must renew them.
        self.s["active_calls"] = {}
        self._save()

    def _save(self):
        with self.lock:
            self.connection.execute("INSERT OR REPLACE INTO map_state (id,payload) VALUES (1,?)", (json.dumps(self.s, ensure_ascii=False, allow_nan=False),))
            self.connection.commit()

    def _audit(self, event, **fields):
        self.s["audit"].append({"event": event, "timestamp": now(), **fields})
        self.s["audit"] = self.s["audit"][-1000:]

    def close(self):
        with self.lock:
            self.connection.close()

    def upsert_call(self, payload):
        """Accept full current transcript, monotonic revision, optional display score.

        Same revision plus identical normalized fields is idempotent; different
        content at the same revision or older revision is rejected with HTTP 409.
        """
        if not isinstance(payload, dict) or set(payload) - {"call_id", "text", "language", "revision", "location", "input_mode", "priority_assessment", "timestamp", "event_id"}:
            raise ValueError("Unsupported call fields; send a full transcript snapshot")
        call_id = payload.get("call_id")
        if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", call_id):
            raise ValueError("call_id must be 1–128 letters, numbers, dot, underscore, colon or hyphen")
        revision = payload.get("revision")
        if type(revision) is not int or not 1 <= revision <= 2_147_483_647:
            raise ValueError("revision must be a positive integer")
        transcript = payload.get("text")
        if not isinstance(transcript, str) or len(transcript) > 100000:
            raise ValueError("text must be a string of at most 100000 characters")
        language = payload.get("language", "und")
        mode = payload.get("input_mode", "host")
        if not isinstance(language, str) or not 1 <= len(language) <= 32:
            raise ValueError("language must be a short language code")
        if not isinstance(mode, str) or not 1 <= len(mode) <= 64:
            raise ValueError("input_mode must be a short source label")
        timestamp = payload.get("timestamp")
        if timestamp is not None:
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z","+00:00"))
                if not parsed.tzinfo:
                    raise ValueError()
            except (ValueError,AttributeError,TypeError):
                raise ValueError("timestamp must be an ISO datetime with timezone") from None
        event_id = payload.get("event_id")
        if event_id is not None and (not isinstance(event_id,str) or not 1 <= len(event_id) <= 512):
            raise ValueError("event_id must be 1–512 characters")
        location = payload.get("location")
        if location is not None:
            if not isinstance(location, dict) or set(location)-{"label", "lat", "lon", "source", "accuracy_m"}:
                raise ValueError("location must be an incident location object or null")
            location = copy.deepcopy(location)
            for key in ("label", "source"):
                if key in location and (not isinstance(location[key], str) or len(location[key]) > 500):
                    raise ValueError("location label/source must be bounded strings")
            if ("lat" in location) != ("lon" in location):
                raise ValueError("Provide both incident lat and lon")
            for key, low, high in (("lat", -90, 90), ("lon", -180, 180), ("accuracy_m", 0, 100000)):
                value = location.get(key)
                if key in location and (isinstance(value, bool) or not isinstance(value, (float,int)) or not math.isfinite(value) or not low <= value <= high):
                    raise ValueError("Invalid incident coordinate or accuracy")
        priority = payload.get("priority_assessment")
        if priority is not None:
            if not isinstance(priority, dict) or set(priority)-{"category", "score", "policy_version"}:
                raise ValueError("priority_assessment accepts display-only category, score, policy_version")
            if not isinstance(priority.get("category"), str) or len(priority["category"]) > 100:
                raise ValueError("priority category must be text")
            score = priority.get("score")
            if score is not None and (isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0 <= score <= 100):
                raise ValueError("priority score must be between 0 and 100")
            if "policy_version" in priority and (not isinstance(priority["policy_version"],str) or len(priority["policy_version"])>200):
                raise ValueError("priority policy_version must be text")
        canonical = {"call_id":call_id, "revision":revision, "text":transcript, "language":language,
                     "location":location, "input_mode":mode, "priority_assessment":copy.deepcopy(priority),
                     "source_timestamp":timestamp,"event_id":event_id}
        fingerprint = hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        with self.lock:
            previous_event = self.s["event_ids"].get(event_id) if event_id else None
            if previous_event:
                if previous_event != fingerprint:
                    raise HTTPException(409,"event_id already belongs to different call data")
                # An acknowledged event can be replayed after newer revisions
                # without reverting current text or silently losing host cursors.
                return {"call":copy.deepcopy(self.s["calls"][call_id]),"duplicate":True,"event_revision":revision}
            old = self.s["calls"].get(call_id)
            if old and revision <= old["revision"]:
                if revision == old["revision"] and all(old.get(k)==v for k,v in canonical.items()):
                    return {"call":copy.deepcopy(old), "duplicate":True}
                raise HTTPException(409, "Call revision must increase; an identical revision can only repeat identical content")
            if not old and len(self.s["calls"]) >= 1000:
                raise HTTPException(409,"Map store reached 1000 calls; archive with a separate database")
            revisions = copy.deepcopy(old["revisions"]) if old else []
            if len(revisions) >= 100:
                raise HTTPException(409,"Call reached 100 full revisions; archive with a new call identifier")
            timestamp = timestamp or now()
            revisions.append({"revision":revision,"text":transcript,"location":location,"timestamp":timestamp})
            self.s["calls"][call_id] = {**canonical, "timestamp":timestamp, "revisions":revisions}
            if event_id:
                self.s["event_ids"][event_id] = fingerprint
            self._audit("host_call_upserted",call_id=call_id,revision=revision)
            self._save()
            return {"call":copy.deepcopy(self.s["calls"][call_id]),"duplicate":False}

    def set_active_call(self, call_id, active=True):
        """Host attests call lifecycle. Activation is not location consent."""
        if type(active) is not bool:
            raise ValueError("active must be boolean")
        with self.lock:
            if call_id not in self.s["calls"]:
                raise HTTPException(404, "Call not found")
            if active:
                self.s["active_calls"][call_id] = {"call_id":call_id,"activated_at":now()}
            else:
                self.s["active_calls"].pop(call_id,None)
            self._audit("host_call_activity",call_id=call_id,active=active)
            self._save()
            return {"call_id":call_id,"active":active}
