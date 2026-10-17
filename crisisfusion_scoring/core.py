"""Auditable prototype rules and durable local workflow.

These rules are development hypotheses, not medical or dispatch standards.
No module reads evaluation labels, and no operation dispatches responders.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .scoring import assess_call, get_policy, queue_key, call_wait_seconds, POLICY_VERSION

RULE_VERSION = "prototype-2026-10-17-v4.1"
PRIORITY = {"IMMEDIATE_HUMAN": 0, "HUMAN_VERIFY": 1,
            "ROUTINE_HUMAN": 2, "AUTOMATION_ELIGIBLE": 3}
DEFAULT_SETTINGS = {
    "association_enabled": True, "realert_enabled": True,
    "model_available": True, "map_available": True, "internet_available": True,
    "available_agents": 2, "surge_calls_per_minute": 8, "surge_backlog": 6,
    "surge_wait_seconds": 120, "callback_max_attempts": 2,
    "association_window_seconds": 900, "association_radius_meters": 75,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def dt(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def normal(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).lower())
                   if not unicodedata.combining(c)).replace("’", "'")


def matched(pattern, value):
    return bool(re.search(pattern, value, re.I))


def waiting_seconds(need, as_of=None):
    """Accumulate actual local queue intervals; connected time is not wait."""
    cursor, waiting, total = dt(need["received_at"]), need.get("initial_transfer_status", "NOT_REQUESTED") != "BRIDGED", 0.0
    for event in need["history"]:
        if "to_transfer" not in event:
            continue
        at = dt(event["at"])
        if waiting:
            total += max(0, (at-cursor).total_seconds())
        waiting = event["to_transfer"] != "BRIDGED" and event["kind"] != "resolve"
        cursor = at
    if waiting and need["unresolved"]:
        total += max(0, (dt(as_of or now())-cursor).total_seconds())
    return round(total, 2)


def extract_call(text, language="en"):
    """Compatibility wrapper for the versioned local evidence extractor."""
    from .extraction import extract_call as extract
    return extract(text, language, rule_version=RULE_VERSION)


class Engine:
    """Atomic SQLite state with immutable audit entries and explicit actions."""
    def __init__(self, db_path=":memory:", settings=None, extractor=None):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
        self.lock = threading.RLock()
        self.extractor = extractor
        row = self.db.execute("SELECT data FROM state WHERE id=1").fetchone()
        self.s = json.loads(row[0]) if row else {"calls": {}, "incidents": {}, "needs": {}, "alerts": [], "audit": [], "events": {}, "settings": copy.deepcopy(DEFAULT_SETTINGS), "latencies_ms": []}
        self.s["settings"] = {**DEFAULT_SETTINGS, **self.s["settings"]}
        if settings:
            self.configure(settings)
        self._refresh_scores(reason="startup_recompute")
        self._save()

    def _save(self):
        with self.db:
            self.db.execute("INSERT INTO state(id,data) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (json.dumps(self.s, ensure_ascii=False),))

    def _audit(self, kind, **data):
        item = {"id": f"audit-{len(self.s['audit'])+1}", "at": now(), "kind": kind, "rule_version": RULE_VERSION, **data}
        self.s["audit"].append(item)
        return item

    def _alert(self, need, kind, reason, evidence, started=None):
        received = now()
        item = {"id": f"alert-{len(self.s['alerts'])+1}", "need_id": need["id"], "call_id": need["call_id"], "incident_id": need["incident_id"],
                "kind": kind, "reason": reason, "evidence": copy.deepcopy(evidence), "at": received,
                "rule_version": RULE_VERSION, "latency_ms": round((time.perf_counter()-started)*1000, 3) if started else 0.0}
        self.s["alerts"].append(item)
        need["alert_count"] += 1
        need["last_alert_at"] = received
        self._audit("human_alert", alert_id=item["id"], need_id=need["id"], reason=reason)
        return item

    def _refresh_scores(self, call_ids=None, reason="clock_refresh", force=False):
        """Persist semantic score changes; polling does not append per-second logs."""
        selected = set(call_ids) if call_ids is not None else set(self.s["calls"])
        at, changed, result = now(), False, {}
        for call_id in sorted(selected):
            call = self.s["calls"].get(call_id)
            if call is None:
                raise KeyError(call_id)
            needs = [n for n in self.s["needs"].values() if n["call_id"] == call_id]
            waits = {n["id"]: waiting_seconds(n, at) for n in needs}
            changed = self._update_call_clock(call, needs, at, reason) or changed
            active = [n for n in needs if n["unresolved"]]
            effective = min((n["triage_status"] for n in active), key=PRIORITY.get) if active else None
            override = call.get("queue_override")
            if override and (override.get("category") != effective or override.get("episode_id") != call["queue_clock"]["episode_id"] or effective in {None, "AUTOMATION_ELIGIBLE"}):
                call.setdefault("queue_override_history", []).append({**override, "expired_at": at, "reason": "Category or human queue episode changed"})
                call["queue_override"] = None
                for n in active:
                    n["manual_order"] = 0
                self._audit("queue_override_expired", call_id=call_id, previous_override=override, reason="Category or human queue episode changed")
                changed = True
            assessment = assess_call(call, needs, as_of=at, wait_by_need=waits,
                                     overdue_after_seconds=self.s["settings"]["surge_wait_seconds"])
            signature_data = None if assessment is None else {
                "policy_version": assessment["policy_version"], "revision": call["revision"],
                "score": assessment["score"], "category": assessment["category"],
                "latest_text_category": assessment["latest_text_category"], "floor": assessment["safety_floor_applied"],
                "need_ids": assessment["unresolved_need_ids"], "gate": assessment["gate"],
                "component_points": [(c["code"], c["points"]) for c in assessment["components"]],
                "overdue": assessment["overdue"], "queue_eligible": assessment["queue_eligible"],
                "transfer_status": assessment["transfer_status"], "parameters": assessment["parameters"],
                "manual_override": assessment["manual_override"],
            }
            signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            previous = call.get("priority_assessment")
            if force or call.get("priority_signature") != signature:
                if previous is not None and assessment is None:
                    call["last_priority_assessment"] = copy.deepcopy(previous)
                elif assessment is not None:
                    call["last_priority_assessment"] = copy.deepcopy(assessment)
                event = self._audit("priority_assessed" if assessment else "priority_assessment_cleared",
                                    call_id=call_id, scoring_policy_version=POLICY_VERSION, reason=reason,
                                    previous_score=previous.get("score") if previous else None,
                                    assessment=copy.deepcopy(assessment))
                call.setdefault("priority_history", []).append({"audit_id": event["id"], "assessed_at": at,
                    "policy_version": POLICY_VERSION, "revision": call["revision"], "reason": reason,
                    "score": assessment["score"] if assessment else None,
                    "category": assessment["category"] if assessment else None})
                call["priority_signature"] = signature
                changed = True
            call["priority_assessment"] = assessment
            if assessment and assessment["overdue"] and not call.get("overdue_notice_active", False):
                candidates = [n for n in needs if n["id"] in assessment["gate"]["source_need_ids"]]
                representative = max(candidates, key=lambda n: waits[n["id"]])
                self._alert(representative, "WAIT_OVERDUE", "Prototype waiting threshold exceeded; supervisor follow-up requested without changing the category.", assessment["components"][1]["evidence"])
                call["overdue_notice_active"] = True
                changed = True
            elif not assessment or not assessment["overdue"]:
                if call.get("overdue_notice_active"):
                    changed = True
                call["overdue_notice_active"] = False
            result[call_id] = copy.deepcopy(assessment)
        return result, changed

    def _update_call_clock(self, call, needs, at, reason):
        """One durable queue clock per caller, independent of Need revisions."""
        human = [n for n in needs if n["unresolved"] and n["triage_status"] != "AUTOMATION_ELIGIBLE"]
        bridged = bool(human) and all(n["transfer_status"] == "BRIDGED" for n in human)
        clock = call.get("queue_clock")
        changed = False
        if clock is None:
            legacy = reason == "startup_recompute" and bool(human)
            clock = {"active": False, "accumulated_seconds": 0.0, "waiting_since": None, "started_at": None,
                     "episode_id": 0, "state": "NO_HUMAN_NEED", "source": "legacy_need_wait_lower_bound" if legacy else "live_call_state"}
            call["queue_clock"] = clock
            if legacy:
                # Existing v3 stores individual Need clocks, not exact past
                # call-level queue intervals. Preserve a documented lower bound
                # instead of inventing an exact historical measurement.
                clock.update({"active": True, "episode_id": 1,
                              "accumulated_seconds": max(waiting_seconds(n, at) for n in human),
                              "started_at": min(n["received_at"] for n in human),
                              "waiting_since": None if bridged else at,
                              "state": "CONNECTED" if bridged else "WAITING"})
            changed = True
        if not human:
            if clock["active"]:
                if clock["waiting_since"]:
                    clock["accumulated_seconds"] += max(0, (dt(at)-dt(clock["waiting_since"])).total_seconds())
                clock.update({"active": False, "waiting_since": None, "state": "NO_HUMAN_NEED", "ended_at": at})
                call.setdefault("queue_clock_history", []).append(copy.deepcopy(clock))
                changed = True
                # Completing the last human Need ends the simulated connection
                # cycle, even if an unrelated automatic-service record remains.
                call["transfer_status"] = "NOT_REQUESTED"
                for n in needs:
                    if n["unresolved"] and n["transfer_status"] != "NOT_REQUESTED":
                        n["history"].append({"kind": "shared_transfer_state", "at": at, "actor": "system_state",
                            "note": "All human needs were explicitly resolved; simulated connection released.",
                            "from_transfer": n["transfer_status"], "to_transfer": "NOT_REQUESTED", "simulation": True})
                        n["transfer_status"] = "NOT_REQUESTED"
                self._audit("human_queue_cycle_ended", call_id=call["id"], episode_id=clock["episode_id"], accumulated_wait_seconds=clock["accumulated_seconds"])
            return changed
        if not clock["active"]:
            clock = {"active": True, "accumulated_seconds": 0.0, "waiting_since": None if bridged else at,
                     "started_at": at, "episode_id": clock["episode_id"]+1,
                     "state": "CONNECTED" if bridged else "WAITING", "source": "live_call_state"}
            call["queue_clock"] = clock
            changed = True
        elif bridged and clock["waiting_since"]:
            clock["accumulated_seconds"] += max(0, (dt(at)-dt(clock["waiting_since"])).total_seconds())
            clock.update({"waiting_since": None, "state": "CONNECTED"})
            changed = True
        elif not bridged and clock["waiting_since"] is None:
            clock.update({"waiting_since": at, "state": "WAITING"})
            changed = True
        return changed

    def recompute_scores(self, call_id=None, reason="manual_recompute"):
        with self.lock:
            result, _ = self._refresh_scores([call_id] if call_id else None, reason=reason, force=True)
            self._save()
            return result

    def scoring_policy(self):
        return get_policy(self.s["settings"]["surge_wait_seconds"])

    def _queue_calls(self):
        rows = []
        for call in self.s["calls"].values():
            assessment = call.get("priority_assessment")
            if not assessment or not assessment["queue_eligible"]:
                continue
            active = [self.s["needs"][nid] for nid in assessment["unresolved_need_ids"]]
            highest = [n for n in active if n["triage_status"] == assessment["category"]]
            representative = min(highest, key=lambda n: (-waiting_seconds(n), n["received_at"], n["id"]))
            override = call.get("queue_override") or {}
            rows.append({"id": call["id"], "call_id": call["id"], "action_need_id": representative["id"],
                         "need_ids": [n["id"] for n in active], "needs_count": len(active),
                         "incident_id": call["incident_id"], "incident_ids": sorted({n["incident_id"] for n in active}),
                         "triage_status": assessment["category"], "transfer_status": assessment["transfer_status"],
                         "waiting_seconds": assessment["waiting_seconds"], "received_at": representative["received_at"],
                         "manual_order": override.get("manual_order", min(n.get("manual_order", 0) for n in highest)),
                         "score": assessment["score"], "priority_assessment": copy.deepcopy(assessment),
                         "text": call["text"], "language": call["language"], "location": copy.deepcopy(call["location"])})
        rows.sort(key=queue_key)
        for position, row in enumerate(rows, 1):
            row["queue_position"] = position
        return rows

    def configure(self, values):
        with self.lock:
            unknown = set(values) - set(DEFAULT_SETTINGS)
            if unknown:
                raise ValueError("Unsupported settings: " + ", ".join(sorted(unknown)))
            for key, val in values.items():
                default = DEFAULT_SETTINGS[key]
                if isinstance(default, bool):
                    if not isinstance(val, bool):
                        raise ValueError(f"{key} must be boolean")
                elif isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
                    raise ValueError(f"{key} must be a finite nonnegative number")
                if key in {"available_agents", "callback_max_attempts"} and (not isinstance(val, int) or val > 100):
                    raise ValueError(f"{key} must be an integer from 0 to 100")
            self.s["settings"].update(values)
            self._audit("settings_changed", changes=values)
            self._refresh_scores(reason="settings_changed")
            self._save()
            return copy.deepcopy(self.s["settings"])

    def _incident(self, call, extracted):
        location = call["location"] or {}
        kind = extracted["hazard_kind"]
        for candidate in self.s["incidents"].values():
            if not self.s["settings"]["association_enabled"]:
                break
            if kind in {"other", "service"} or candidate["hazard_kind"] != kind:
                continue
            if abs((dt(call["timestamp"])-dt(candidate["last_evidence_at"])).total_seconds()) > self.s["settings"]["association_window_seconds"]:
                continue
            other = candidate["location"] or {}
            label, other_label = normal(location.get("label", "")).strip(), normal(other.get("label", "")).strip()
            if label and other_label and label != other_label:
                continue
            same_place = bool(label and other_label and label == other_label and label not in {"unknown", "not known", "nearby", "somewhere"})
            if all(isinstance(loc.get(k), (int, float)) for loc in (location, other) for k in ("lat", "lon")):
                lat1, lat2 = math.radians(location["lat"]), math.radians(other["lat"])
                dlat, dlon = lat2-lat1, math.radians(other["lon"]-location["lon"])
                distance = 6371000*2*math.asin(min(1, math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))
                # Conflicting coordinates never disappear behind a matching label.
                if distance > self.s["settings"]["association_radius_meters"]:
                    continue
                same_place = True
            if same_place:
                return candidate
        incident_id = "inc-" + uuid.uuid4().hex[:10]
        incident = {"id": incident_id, "hazard_kind": kind, "hypothesis": f"Possible {kind} report",
                    "call_ids": [], "location": copy.deepcopy(location), "first_seen_at": call["timestamp"],
                    "last_evidence_at": call["timestamp"], "conflicts": [], "confirmation_status": "UNCONFIRMED",
                    "independent_report_count": 0, "reported_information_count": 0,
                    "distinct_direct_or_unspecified_text_count": 0, "independent_evidence_status": "UNVERIFIED",
                    "evidence_fingerprints": [], "human_history": []}
        self.s["incidents"][incident_id] = incident
        return incident

    def ingest(self, payload):
        started = time.perf_counter()
        with self.lock:
            alert_offset = len(self.s["alerts"])
            allowed = {"call_id", "text", "language", "location", "timestamp", "revision", "event_id", "input_mode", "speaker"}
            extra = set(payload)-allowed
            if extra:
                raise ValueError("Unsupported inference fields: " + ", ".join(sorted(extra)))
            text = str(payload.get("text", "")).strip()
            if len(text) > 20000:
                raise ValueError("Transcript exceeds 20000 characters")
            call_id = str(payload.get("call_id") or "call-"+uuid.uuid4().hex[:10])
            if len(call_id) > 100:
                raise ValueError("call_id exceeds 100 characters")
            revision = payload.get("revision", 1)
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                raise ValueError("revision must be a positive integer")
            timestamp = payload.get("timestamp") or now()
            dt(timestamp)
            mode = payload.get("input_mode", "text")
            if mode not in {"text", "replay", "simulated_voice", "browser_voice"}:
                raise ValueError("Only local text, replay, simulated_voice, or browser_voice is enabled")
            language = payload.get("language", "en")
            if language not in {"en", "es", "mixed", "unknown"}:
                language = "unknown"
            location = copy.deepcopy(payload.get("location") or {})
            if not isinstance(location, dict):
                raise ValueError("location must be an object")
            if set(location)-{"label", "lat", "lon", "source"}:
                raise ValueError("Unsupported location field")
            for field, limit in (("lat", 90), ("lon", 180)):
                if location.get(field) is not None and (isinstance(location[field], bool) or not isinstance(location[field], (int, float)) or not math.isfinite(location[field]) or abs(location[field]) > limit):
                    raise ValueError(f"Invalid {field}")
            event_id = str(payload.get("event_id") or f"transcript:{call_id}:{revision}")
            event_key = "ingest:"+event_id
            existing = self.s["calls"].get(call_id)
            event_fingerprint = hashlib.sha256(json.dumps({"call_id": call_id, "revision": revision, "text": text, "language": language, "location": location, "input_mode": mode, "speaker": payload.get("speaker", "caller"), "timestamp": payload.get("timestamp")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            delivered = self.s["events"].get(event_key)
            if delivered and (delivered.get("call_id") != call_id or delivered.get("revision") != revision or delivered.get("fingerprint", event_fingerprint) != event_fingerprint):
                raise ValueError("Conflicting event_id: this identifier already represents different transcript content")
            if existing and revision == existing["revision"] and (text != existing["text"] or location != existing["location"]):
                raise ValueError("Conflicting transcript revision; submit a higher revision for changed content")
            if event_key in self.s["events"] or (existing and revision <= existing["revision"]):
                self._audit("duplicate_or_stale_transcript_ignored", call_id=call_id, revision=revision, event_id=event_id)
                self._save()
                return {"call": copy.deepcopy(existing), "incident": copy.deepcopy(self.s["incidents"].get(existing["incident_id"])) if existing else None,
                        "needs": [copy.deepcopy(n) for n in self.s["needs"].values() if n["call_id"] == call_id], "alerts": [], "duplicate": True}
            fallback_reason = None
            if self.extractor and self.s["settings"]["model_available"] and self.s["settings"]["internet_available"]:
                try:
                    supplemental = self.extractor.extract(text=text, language=language)
                    if not isinstance(supplemental, dict) or not isinstance(supplemental.get("fields"), dict):
                        raise ValueError("Invalid supplemental extractor output")
                    # Optional providers supply evidence, never a free-form score
                    # or binding action. This MVP keeps its local safety policy.
                    extracted = extract_call(text, language)
                    extracted["supplemental_provider_fields"] = supplemental["fields"]
                    extracted["uncertainties"].append("Optional provider extraction is unverified supplemental evidence; local rules determine the queue.")
                except Exception:
                    extracted = extract_call(text, language)
                    fallback_reason = "External extractor failed; local rules retained the call and queue."
            else:
                extracted = extract_call(text, language)
                if not self.s["settings"]["model_available"]:
                    fallback_reason = "External model unavailable; local rules active."
            if fallback_reason:
                extracted["fallback_reason"] = fallback_reason
            if mode == "browser_voice" and language == "unknown" and PRIORITY[extracted["triage_status"]] > PRIORITY["HUMAN_VERIFY"]:
                extracted["triage_status"] = "HUMAN_VERIFY"
                extracted["reasons"].append("Browser ASR language is outside the validated local rule coverage; human verification is required.")
            call = {"id": call_id, "call_id": call_id, "text": text, "language": language, "location": location,
                    "timestamp": timestamp, "received_at": now(), "revision": revision, "event_id": event_id,
                    "input_mode": mode, "speaker": str(payload.get("speaker", "caller")), "extraction": extracted,
                    "revisions": copy.deepcopy(existing["revisions"]) if existing else [],
                    "connection_status": existing.get("connection_status", "LOCAL_INPUT") if existing else ("BROWSER_VOICE" if mode == "browser_voice" else "LOCAL_INPUT"),
                    "transfer_status": existing.get("transfer_status", "NOT_REQUESTED") if existing else "NOT_REQUESTED"}
            call["revisions"].append({"revision": revision, "text": text, "timestamp": timestamp, "received_at": call["received_at"], "location": location})
            if existing:
                for key in ("priority_assessment", "last_priority_assessment", "priority_history", "priority_signature", "queue_override", "queue_override_history", "overdue_notice_active", "queue_clock", "queue_clock_history"):
                    if key in existing:
                        call[key] = copy.deepcopy(existing[key])
            if existing and not any(n["call_id"] == call_id and n["unresolved"] for n in self.s["needs"].values()):
                call["transfer_status"] = "NOT_REQUESTED"
            previous_incident = self.s["incidents"][existing["incident_id"]] if existing else None
            explicit_new_hazard = previous_incident and extracted["hazard_kind"] not in {"other", "service"} and previous_incident["hazard_kind"] != extracted["hazard_kind"]
            incident = self._incident(call, extracted) if not existing or explicit_new_hazard else previous_incident
            call["incident_history"] = copy.deepcopy(existing.get("incident_history", [])) if existing else []
            if previous_incident and previous_incident["id"] != incident["id"]:
                previous_incident.setdefault("historical_call_ids", []).append(call_id)
                previous_incident["call_ids"] = [cid for cid in previous_incident["call_ids"] if cid != call_id]
                call["incident_history"].append({"previous_incident_id": previous_incident["id"], "new_incident_id": incident["id"], "revision": revision, "at": timestamp, "reason": "Explicit new hazard in transcript revision"})
                self._audit("call_incident_reassociated", call_id=call_id, previous_incident_id=previous_incident["id"], new_incident_id=incident["id"], revision=revision)
            call["incident_id"] = incident["id"]
            if call_id not in incident["call_ids"]:
                incident["call_ids"].append(call_id)
            if dt(timestamp) > dt(incident["last_evidence_at"]):
                incident["last_evidence_at"] = timestamp
            fingerprint = hashlib.sha256(normal(text).encode()).hexdigest()
            reported = any(e.get("provenance") == "reported" for e in extracted["evidence"])
            if (not existing or explicit_new_hazard) and fingerprint not in incident["evidence_fingerprints"]:
                if reported:
                    incident["reported_information_count"] += 1
                else:
                    incident["distinct_direct_or_unspecified_text_count"] = incident.get("distinct_direct_or_unspecified_text_count", 0) + 1
                incident["evidence_fingerprints"].append(fingerprint)
            if extracted["fields"]["contradiction"]["value"] is True:
                incident["conflicts"].append({"call_id": call_id, "quote": text, "at": timestamp, "kind": "within_transcript"})
            # Positive versus negative reports stay visible as an unverified conflict.
            sign = extracted["fields"]["potential_hazard"]["value"]
            for old_call_id in incident["call_ids"]:
                old_call = self.s["calls"].get(old_call_id)
                if old_call and old_call_id != call_id:
                    old_sign = old_call["extraction"]["fields"]["potential_hazard"]["value"]
                    if isinstance(sign, bool) and isinstance(old_sign, bool) and sign != old_sign:
                        incident["conflicts"].append({"call_id": call_id, "other_call_id": old_call_id, "quote": text, "at": timestamp, "kind": "cross_call"})
                        if PRIORITY[extracted["triage_status"]] > PRIORITY["HUMAN_VERIFY"]:
                            extracted["triage_status"] = "HUMAN_VERIFY"
                            extracted["reasons"].append("Conflicting reports about the same possible incident require a person.")
                        break
            location_conflict = bool(existing and location and existing["location"] and location != existing["location"])
            if location_conflict:
                incident["conflicts"].append({"call_id": call_id, "kind": "location_revision", "previous": existing["location"], "current": location, "at": timestamp})
            self.s["calls"][call_id] = call
            new_alerts, affected = [], []
            call_needs = [n for n in self.s["needs"].values() if n["call_id"] == call_id]
            for need_type in extracted["need_types"]:
                need = next((n for n in call_needs if n["need_type"] == need_type and n["unresolved"]), None)
                new = need is None
                if new:
                    need_id = "need-"+uuid.uuid4().hex[:10]
                    need = {"id": need_id, "call_id": call_id, "incident_id": incident["id"], "need_type": need_type,
                            "first_seen_at": timestamp, "received_at": call["received_at"], "updated_at": timestamp,
                            "unresolved": True, "triage_status": extracted["triage_status"], "transfer_status": call["transfer_status"],
                            "initial_transfer_status": call["transfer_status"],
                            "evidence": [], "reasons": [], "uncertainties": [], "history": [], "alert_count": 0,
                            "last_alert_at": None, "callback_attempts": 0, "callback_status": "NOT_REQUIRED", "manual_order": 0,
                            "simulation": True, "rule_version": RULE_VERSION}
                    self.s["needs"][need_id] = need
                old_triage = need["triage_status"]
                if need["incident_id"] != incident["id"]:
                    need["history"].append({"kind": "incident_reassociated", "previous_incident_id": need["incident_id"], "new_incident_id": incident["id"], "at": timestamp})
                    need["incident_id"] = incident["id"]
                if PRIORITY[extracted["triage_status"]] < PRIORITY[old_triage]:
                    need["triage_status"] = extracted["triage_status"]
                evidence_ids = {(e["quote"], e["field"], e["value"]) for e in need["evidence"]}
                additions = [e for e in extracted["evidence"] if (e["quote"], e["field"], e["value"]) not in evidence_ids]
                for item in additions:
                    need["evidence"].append({**item, "call_id": call_id, "revision": revision, "timestamp": timestamp, "rule_version": RULE_VERSION})
                need["updated_at"] = timestamp
                need["reasons"] = list(dict.fromkeys(need["reasons"] + extracted["reasons"]))
                need["uncertainties"] = list(dict.fromkeys(need["uncertainties"] + extracted["uncertainties"]))
                if new and need["triage_status"] != "AUTOMATION_ELIGIBLE":
                    changed = bool(existing and self.s["settings"]["realert_enabled"])
                    new_alerts.append(self._alert(need, "CHANGED_NEED" if changed else "NEW_NEED", "An existing caller has a new unresolved need. " + need["reasons"][0] if changed else need["reasons"][0], need["evidence"], started))
                elif not new and self.s["settings"]["realert_enabled"] and (location_conflict or old_triage != need["triage_status"] or any(e["field"] in {"personal_danger", "trapped", "evacuation_barrier", "potential_hazard", "contradiction"} and e["value"] is True for e in additions)):
                    conflict_evidence = [{"field": "location_conflict", "quote": text, "previous_location": existing["location"], "current_location": location, "call_id": call_id, "revision": revision, "timestamp": timestamp, "rule_version": RULE_VERSION}] if location_conflict else []
                    new_alerts.append(self._alert(need, "CHANGED_NEED", "Location conflict requires human verification." if location_conflict else "New critical evidence or escalation in an unresolved need.", additions + conflict_evidence, started))
                need["history"].append({"kind": "transcript_evidence", "at": timestamp, "revision": revision, "new_evidence_count": len(additions)})
                affected.append(need)
            self.s["events"][event_key] = {"call_id": call_id, "revision": revision, "fingerprint": event_fingerprint}
            latency = round((time.perf_counter()-started)*1000, 3)
            self.s["latencies_ms"].append(latency)
            self._audit("transcript_ingested", call_id=call_id, revision=revision, incident_id=incident["id"], need_ids=[n["id"] for n in affected], processing_ms=latency, fallback_reason=fallback_reason)
            self._refresh_scores([call_id], reason="transcript_ingested")
            self._save()
            return copy.deepcopy({"call": call, "incident": incident, "needs": [n for n in self.s["needs"].values() if n["call_id"] == call_id], "alerts": self.s["alerts"][alert_offset:], "duplicate": False})

    def action(self, need_id, payload):
        with self.lock:
            if need_id not in self.s["needs"]:
                raise KeyError(need_id)
            name = payload.get("action")
            actor = str(payload.get("actor", "dashboard_operator"))
            note = str(payload.get("note", ""))
            event_key = "action:" + str(payload.get("event_id")) if payload.get("event_id") else None
            need = self.s["needs"][need_id]
            action_fingerprint = hashlib.sha256(json.dumps({"need_id": need_id, "action": name, "actor": actor, "note": note, "manual_order": payload.get("manual_order"), "target_category": payload.get("target_category")}, sort_keys=True).encode()).hexdigest()
            if event_key and event_key in self.s["events"]:
                delivered = self.s["events"][event_key]
                if delivered.get("need_id") != need_id or delivered.get("action") != name or delivered.get("fingerprint", action_fingerprint) != action_fingerprint:
                    raise ValueError("Conflicting action event_id: this identifier already represents another action")
                return copy.deepcopy({"need": need, "event": self.s["events"][event_key], "duplicate": True})
            if not need["unresolved"] and name != "resolve":
                raise ValueError("This need is resolved; new evidence must create a new open need before connection actions")
            before = copy.deepcopy(need)
            if name in {"request_transfer", "request_callback", "interrupted"} and need["triage_status"] == "AUTOMATION_ELIGIBLE":
                need["triage_status"] = "ROUTINE_HUMAN"
                need["reasons"].append("An explicit operator action requested a human connection or follow-up.")
                need["evidence"].append({"field": "human_requested", "value": True, "quote": note or "Operator requested a human connection or follow-up.", "subject": "operator", "temporal": "current", "provenance": "human_action", "intent": "request", "call_id": need["call_id"], "revision": None, "timestamp": now(), "rule_version": RULE_VERSION})
            active = len({n["call_id"] for n in self.s["needs"].values() if n["transfer_status"] == "BRIDGED" and n["unresolved"]})
            status = need["transfer_status"]
            if name == "request_transfer":
                if status in {"REQUESTED", "DIALING", "BRIDGED"}:
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                need["transfer_status"] = "REQUESTED"
            elif name == "simulate_dial":
                if status in {"DIALING", "BRIDGED"}:
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                if status != "REQUESTED":
                    raise ValueError("Dialing requires a requested transfer")
                reserved = len({n["call_id"] for n in self.s["needs"].values() if n["transfer_status"] in {"DIALING", "BRIDGED"} and n["unresolved"]})
                if reserved >= self.s["settings"]["available_agents"]:
                    raise ValueError("All simulated operator seats are busy; the request remains queued")
                need["transfer_status"] = "DIALING"
            elif name == "simulate_bridge":
                if status == "BRIDGED":
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                if status != "DIALING":
                    raise ValueError("Simulated bridge requires a dialing transfer")
                if active >= self.s["settings"]["available_agents"]:
                    raise ValueError("No simulated operator seat is available")
                need["transfer_status"] = "BRIDGED"
                need["handled_by"] = actor
            elif name in {"simulate_no_answer", "simulate_failure"}:
                if status not in {"REQUESTED", "DIALING"}:
                    raise ValueError("A pending transfer is required")
                need["transfer_status"] = "NO_ANSWER" if name == "simulate_no_answer" else "FAILED"
                need["retry_target"] = "Next available simulated operator / supervisor"
                self._alert(need, "TRANSFER_FAILED", "No operator connection confirmed; unresolved need retained.", need["evidence"][-3:])
            elif name == "interrupted":
                need["transfer_status"] = "FAILED"
                need["callback_status"] = "PENDING_HUMAN_REVIEW"
                self.s["calls"][need["call_id"]]["connection_status"] = "INTERRUPTED"
                self._alert(need, "CALL_INTERRUPTED", "Caller disconnected; create bounded follow-up without closing the need.", need["evidence"][-3:])
                # Interruption belongs to the call, even if the operator clicked
                # one of several independent needs from that caller.
                for sibling in self.s["needs"].values():
                    if sibling["call_id"] != need["call_id"] or sibling["id"] == need_id or not sibling["unresolved"]:
                        continue
                    sibling_record = {"kind": "interrupted", "at": now(), "actor": actor, "note": "Same call disconnected. " + note,
                                      "simulation": True, "from_transfer": sibling["transfer_status"], "to_transfer": "FAILED"}
                    sibling["transfer_status"] = "FAILED"
                    sibling["callback_status"] = "PENDING_HUMAN_REVIEW"
                    sibling["history"].append(sibling_record)
                    self._alert(sibling, "CALL_INTERRUPTED", "The same caller disconnected; this separate need remains unresolved.", sibling["evidence"][-3:])
                    self._audit("human_action", need_id=sibling["id"], action="interrupted", **{k: v for k, v in sibling_record.items() if k != "kind"})
            elif name == "request_callback":
                same_call_needs = [n for n in self.s["needs"].values() if n["call_id"] == need["call_id"]]
                if any(n["callback_status"] == "DIALING" for n in same_call_needs):
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                if sum(n["callback_attempts"] for n in same_call_needs) >= self.s["settings"]["callback_max_attempts"]:
                    for sibling in same_call_needs:
                        if sibling["unresolved"]:
                            sibling["callback_status"] = "MANUAL_FOLLOWUP"
                    self._save()
                    raise ValueError("Simulated callback budget exhausted; manual follow-up required")
                need["callback_attempts"] += 1
                need["callback_status"] = "DIALING"
            elif name == "callback_no_answer":
                if need["callback_status"] != "DIALING":
                    raise ValueError("No simulated callback is in progress")
                call_attempts = sum(n["callback_attempts"] for n in self.s["needs"].values() if n["call_id"] == need["call_id"])
                need["callback_status"] = "MANUAL_FOLLOWUP" if call_attempts >= self.s["settings"]["callback_max_attempts"] else "NO_ANSWER"
                self._alert(need, "CALLBACK_NO_ANSWER", "Resident not reached; safety is unconfirmed and need stays open.", need["evidence"][-3:])
            elif name == "callback_connected":
                if need["callback_status"] != "DIALING":
                    raise ValueError("No simulated callback is in progress")
                need["callback_status"] = "CONNECTED_SIMULATED"
            elif name == "resolve":
                if not payload.get("actor") or not note.strip():
                    raise ValueError("Manual resolution requires an identified human actor and a note")
                if not need["unresolved"]:
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                need["unresolved"] = False
                need["resolved_at"] = now()
                need["resolved_by"] = actor
            elif name == "override":
                order = payload.get("manual_order", 0)
                if not isinstance(order, int) or not -100 <= order <= 100 or not note.strip():
                    raise ValueError("Override requires integer manual_order from -100 to 100 and a note")
                current = self.s["calls"][need["call_id"]].get("priority_assessment")
                if not current or current["category"] == "AUTOMATION_ELIGIBLE":
                    raise ValueError("Manual ordering requires an unresolved human category")
                override = {"manual_order": order, "actor": actor, "note": note, "at": now(), "scope": "within_current_category",
                            "category": current["category"], "episode_id": self.s["calls"][need["call_id"]]["queue_clock"]["episode_id"]}
                self.s["calls"][need["call_id"]]["queue_override"] = override
                for sibling in self.s["needs"].values():
                    if sibling["call_id"] == need["call_id"] and sibling["unresolved"]:
                        sibling["manual_order"] = order
            elif name == "escalate":
                target = payload.get("target_category")
                if target not in {"IMMEDIATE_HUMAN", "HUMAN_VERIFY", "ROUTINE_HUMAN"}:
                    raise ValueError("Human escalation requires a human target_category")
                if not payload.get("actor") or not str(payload["actor"]).strip() or not note.strip():
                    raise ValueError("Human escalation requires an identified actor and a reason")
                if PRIORITY[target] > PRIORITY[need["triage_status"]]:
                    raise ValueError("Human escalation cannot lower an unresolved need; use explicit resolution after human review")
                if target == need["triage_status"]:
                    return {"need": copy.deepcopy(need), "event": None, "duplicate": True}
                need["triage_status"] = target
                entry = {"field": "manual_escalation", "value": True, "quote": note, "target_category": target,
                         "subject": "operator", "temporal": "current", "provenance": "human_action", "intent": "escalation",
                         "actor": actor, "call_id": need["call_id"], "revision": None, "timestamp": now(), "rule_version": RULE_VERSION}
                need["evidence"].append(entry)
                need["reasons"].append("Identified operator escalation: " + note)
                self._alert(need, "HUMAN_ESCALATION", "An identified operator raised this unresolved need's category.", [entry])
            elif name == "confirm_incident":
                if not payload.get("actor") or not note.strip():
                    raise ValueError("Incident confirmation requires a human actor and a note")
                incident = self.s["incidents"][need["incident_id"]]
                incident["confirmation_status"] = "HUMAN_REVIEWED"
                incident["human_history"].append({"actor": actor, "at": now(), "note": note})
            else:
                raise ValueError("Unsupported action")
            if name in {"request_transfer", "simulate_dial", "simulate_bridge", "simulate_no_answer", "simulate_failure", "interrupted"}:
                self.s["calls"][need["call_id"]]["transfer_status"] = need["transfer_status"]
                for sibling in self.s["needs"].values():
                    if sibling["call_id"] != need["call_id"] or sibling["id"] == need_id or not sibling["unresolved"] or sibling["transfer_status"] == need["transfer_status"]:
                        continue
                    shared_record = {"kind": "shared_transfer_state", "at": now(), "actor": actor,
                                     "note": "One simulated connection per call; individual needs remain unresolved.",
                                     "simulation": True, "from_transfer": sibling["transfer_status"], "to_transfer": need["transfer_status"]}
                    sibling["transfer_status"] = need["transfer_status"]
                    sibling["history"].append(shared_record)
                    self._audit("shared_transfer_state", need_id=sibling["id"], call_id=need["call_id"], **{k: v for k, v in shared_record.items() if k != "kind"})
            record = {"kind": name, "at": now(), "actor": actor, "note": note, "simulation": True,
                      "from_transfer": before["transfer_status"], "to_transfer": need["transfer_status"]}
            need["history"].append(record)
            event = self._audit("human_action", need_id=need_id, action=name, **{k: v for k, v in record.items() if k != "kind"})
            if event_key:
                self.s["events"][event_key] = {**event, "fingerprint": action_fingerprint}
            self._refresh_scores([need["call_id"]], reason="human_action:" + name)
            self._save()
            return copy.deepcopy({"need": need, "event": event, "duplicate": False, "priority_assessment": self.s["calls"][need["call_id"]].get("priority_assessment")})

    def metrics(self):
        with self.lock:
            _, refreshed = self._refresh_scores()
            if refreshed:
                self._save()
            calls, needs = list(self.s["calls"].values()), list(self.s["needs"].values())
            unresolved = [n for n in needs if n["unresolved"]]
            pending = [n for n in unresolved if n["triage_status"] != "AUTOMATION_ELIGIBLE" and n["transfer_status"] != "BRIDGED"]
            elapsed = lambda t: max(0, (dt(now())-dt(t)).total_seconds())
            last_minute = sum(elapsed(c["received_at"]) < 60 for c in calls)
            waits = {kind: [waiting_seconds(n) for n in pending if n["triage_status"] == kind] for kind in PRIORITY}
            queue_calls = self._queue_calls()
            call_waits = {kind: [c["waiting_seconds"] for c in queue_calls if c["triage_status"] == kind] for kind in PRIORITY}
            actions = [x for x in self.s["audit"] if x["kind"] == "human_action"]
            transfers = sum(x.get("to_transfer") == "DIALING" and x.get("from_transfer") != "DIALING" for x in actions)
            bridges = sum(x.get("to_transfer") == "BRIDGED" and x.get("from_transfer") != "BRIDGED" for x in actions)
            requested = sum(x.get("action") == "request_transfer" for x in actions)
            active = len({n["call_id"] for n in unresolved if n["transfer_status"] in {"DIALING", "BRIDGED"}})
            return {"calls": len(calls), "transcript_versions": sum(len(c["revisions"]) for c in calls),
                    "incidents": len(self.s["incidents"]), "needs": len(needs), "unresolved_needs": len(unresolved),
                    "pending_human_needs": len(pending), "pending_human_calls": len(queue_calls), "alerts": len(self.s["alerts"]),
                    "attention_overdue_calls": sum(c["priority_assessment"]["overdue"] for c in queue_calls),
                    "scoring_policy_version": POLICY_VERSION,
                    "critical_realerts": sum(a["kind"] == "CHANGED_NEED" for a in self.s["alerts"]),
                    "calls_last_minute": last_minute, "available_simulated_seats": max(0, self.s["settings"]["available_agents"]-active),
                    "all_agents_busy": active >= self.s["settings"]["available_agents"],
                    "maximum_current_wait_seconds": round(max([v for group in waits.values() for v in group] or [0]), 2),
                    "wait_by_category_seconds": {k: {"count": len(v), "mean": round(sum(v)/len(v), 2) if v else 0, "max": round(max(v or [0]), 2)} for k, v in waits.items()},
                    "call_wait_by_category_seconds": {k: {"count": len(v), "mean": round(sum(v)/len(v), 2) if v else 0, "max": round(max(v or [0]), 2)} for k, v in call_waits.items()},
                    "processing_ms_mean": round(sum(self.s["latencies_ms"])/len(self.s["latencies_ms"]), 3) if self.s["latencies_ms"] else None,
                    "simulated_transfer_requests": requested, "simulated_dial_attempts": transfers,
                    "simulated_transfer_attempts": requested, "simulated_bridges": bridges,
                    "simulated_bridge_rate": bridges/requested if requested else None,
                    "actual_transfer_success_rate": None, "actual_voice_minutes": 0,
                    "actual_external_model_calls": 0, "automatic_need_closures": 0,
                    "surge_risk": last_minute >= self.s["settings"]["surge_calls_per_minute"] or len(queue_calls) >= self.s["settings"]["surge_backlog"] or any(v >= self.s["settings"]["surge_wait_seconds"] for group in call_waits.values() for v in group),
                    "metric_scope": "Local observations; real telephony and operator service time are not measured."}

    def snapshot(self):
        with self.lock:
            _, refreshed = self._refresh_scores()
            if refreshed:
                self._save()
            needs = copy.deepcopy(list(self.s["needs"].values()))
            for need in needs:
                need["waiting_seconds"] = waiting_seconds(need)
            queue = sorted((n for n in needs if n["unresolved"] and n["triage_status"] != "AUTOMATION_ELIGIBLE" and n["transfer_status"] != "BRIDGED"), key=lambda n: (PRIORITY[n["triage_status"]], n["manual_order"], n["received_at"], n["id"]))
            settings = self.s["settings"]
            degradation = {"extractor": "local_bilingual_rules", "external_model_unavailable": not settings["model_available"],
                           "map_fallback": not settings["map_available"], "internet_offline": not settings["internet_available"],
                           "real_voice_enabled": False, "message": "Local text, stored evidence and queue remain available. Cloud calls cannot be received offline." if not settings["internet_available"] else "Local prototype. All voice and bridge operations are dashboard simulations."}
            return {"calls": copy.deepcopy(list(self.s["calls"].values())), "incidents": copy.deepcopy(list(self.s["incidents"].values())),
                    "needs": needs, "queue": queue, "queue_calls": self._queue_calls(), "alerts": copy.deepcopy(self.s["alerts"]), "audit": copy.deepcopy(self.s["audit"]),
                    "settings": copy.deepcopy(settings), "metrics": self.metrics(), "degradation": degradation, "rule_version": RULE_VERSION,
                    "scoring_policy": self.scoring_policy(), "scoring_policy_version": POLICY_VERSION}

    def reset(self):
        with self.lock:
            settings = copy.deepcopy(self.s["settings"])
            self.s = {"calls": {}, "incidents": {}, "needs": {}, "alerts": [], "audit": [], "events": {}, "settings": settings, "latencies_ms": []}
            self._audit("local_demo_reset", note="Explicit local demo reset; no external call or service was affected.")
            self._save()
            return self.snapshot()
