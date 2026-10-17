"""Versioned, deterministic Human Attention Index; never a risk probability.

The index encodes an evidence-gated action category plus bounded operational
attention. It does not sum disaster labels, model confidence, or demographics.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timezone

POLICY_VERSION = "human-attention-2026-10-17-v1"
CATEGORY_RANK = {"IMMEDIATE_HUMAN": 0, "HUMAN_VERIFY": 1,
                 "ROUTINE_HUMAN": 2, "AUTOMATION_ELIGIBLE": 3}
BANDS = {"IMMEDIATE_HUMAN": (80, 100), "HUMAN_VERIFY": (50, 79),
         "ROUTINE_HUMAN": (20, 49), "AUTOMATION_ELIGIBLE": (0, 19)}
WAIT_STEP_SECONDS = 60
WAIT_CAP_POINTS = 15
FOLLOWUP_POINTS = 5
SCORE_SEMANTICS = "Category plus operational attention; not a probability, diagnosis, or independent predictor."
SORT_POLICY = "validated category band, explicit within-category manual order, longest accumulated waiting, stable call ID"


def call_wait_seconds(call, as_of, fallback=0):
    clock = call.get("queue_clock")
    if not clock:
        return round(fallback, 2)
    if not clock.get("active"):
        return 0.0
    total = float(clock.get("accumulated_seconds", 0))
    if clock.get("waiting_since"):
        parse = lambda value: datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        current, since = parse(as_of), parse(clock["waiting_since"])
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        total += max(0, (current-since).total_seconds())
    return round(total, 2)


def get_policy(overdue_after_seconds=120):
    """Return actual constants rather than a second documentation-only policy."""
    return {"policy_version": POLICY_VERSION, "name": "Human Attention Index",
            "score_range": [0, 100], "bands": {k: {"min": lo, "max": hi, "anchor": lo} for k, (lo, hi) in BANDS.items()},
            "wait_step_seconds": WAIT_STEP_SECONDS, "wait_cap_points": WAIT_CAP_POINTS,
            "followup_points": FOLLOWUP_POINTS, "overdue_after_seconds": overdue_after_seconds,
            "sort_policy": SORT_POLICY, "score_semantics": SCORE_SEMANTICS,
            "assumptions": "Band anchors, one point per waiting minute, the 15-point waiting cap, five follow-up points, and the overdue threshold are unvalidated prototype policy choices. They are not learned weights or professional standards.",
            "excluded_from_points": ["language identity", "protected characteristics", "missing location", "incident duplication", "available staff", "model confidence", "uncertainty"],
            "automation_gate": "Whole-transcript approved service intent; unexplained content requires human verification.",
            "hard_constraints": ["No automatic downgrade of an unresolved need", "No automatic resolution", "No cross-band aging", "One queue action per call", "Manual ordering cannot cross categories", "Scalar score does not replace within-category FIFO"]}


def category_for_score(score):
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("Human Attention Index must be an integer from 0 to 100")
    for category, (lower, upper) in BANDS.items():
        if lower <= score <= upper:
            return category
    raise ValueError("No category band for score")


def queue_key(row):
    """The score band must agree with the hard category before queue use."""
    assessment = row["priority_assessment"]
    category = category_for_score(assessment["score"])
    if category != assessment["category"] or category != row["triage_status"]:
        raise ValueError("Score/category mismatch: queue ordering refused")
    return (CATEGORY_RANK[category], row["manual_order"], -row["waiting_seconds"], row["received_at"], row["call_id"])


def _evidence(need, rule_id, predicate=None):
    result = []
    for entry in need.get("evidence", []):
        if predicate is not None and not predicate(entry):
            continue
        result.append({**copy.deepcopy(entry), "rule_id": rule_id, "call_id": need["call_id"],
                       "need_id": need["id"], "revision": entry.get("revision"),
                       "timestamp": entry.get("timestamp", need.get("first_seen_at"))})
    return result


def assess_call(call, needs, *, as_of, wait_by_need, overdue_after_seconds=120):
    """Pure per-call rubric. Input is persisted evidence and unresolved state.

    Return None for a call with no unresolved need. The engine retains previous
    assessments separately. Latest transcript classification is informational;
    only unresolved needs determine the retained category floor.
    """
    active = [n for n in needs if n.get("call_id") == call["id"] and n.get("unresolved")]
    if not active:
        return None
    if any(n.get("triage_status") not in CATEGORY_RANK for n in active):
        raise ValueError("Unknown unresolved-need category; cannot compute an index")
    if not isinstance(overdue_after_seconds, (int, float)) or isinstance(overdue_after_seconds, bool) or not math.isfinite(overdue_after_seconds) or overdue_after_seconds < 0:
        raise ValueError("Overdue threshold must be finite and nonnegative")
    effective = min((n["triage_status"] for n in active), key=CATEGORY_RANK.get)
    critical_needs = [n for n in active if n["triage_status"] == effective]
    latest = call.get("extraction", {}).get("triage_status", "HUMAN_VERIFY")
    if latest not in CATEGORY_RANK:
        latest = "HUMAN_VERIFY"
    floor_applied = CATEGORY_RANK[effective] < CATEGORY_RANK[latest]
    human_needs = [n for n in active if n["triage_status"] != "AUTOMATION_ELIGIBLE"]
    waits = [wait_by_need.get(n["id"], 0) for n in human_needs]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in waits):
        raise ValueError("Waiting observations must be finite nonnegative seconds")
    waiting = call_wait_seconds(call, as_of, max(waits or [0]))
    transfer = call.get("transfer_status") or active[0].get("transfer_status", "NOT_REQUESTED")
    # Every need in one call shares a connection. A legacy mixed snapshot must
    # not invent a bridge that is absent from the retained need records.
    if any(n.get("transfer_status") != "BRIDGED" for n in active) and transfer == "BRIDGED":
        transfer = next(n.get("transfer_status", "NOT_REQUESTED") for n in active if n.get("transfer_status") != "BRIDGED")
    queue_eligible = effective != "AUTOMATION_ELIGIBLE" and transfer != "BRIDGED"
    overdue = queue_eligible and waiting >= overdue_after_seconds
    rule_id = {"IMMEDIATE_HUMAN": "G1_CURRENT_DANGER", "HUMAN_VERIFY": "G2_HUMAN_VERIFICATION",
               "ROUTINE_HUMAN": "G3_HUMAN_CHANNEL", "AUTOMATION_ELIGIBLE": "G4_APPROVED_SERVICE"}[effective]
    labels = {"G1_CURRENT_DANGER": "Current explicit danger, entrapment, or evacuation barrier",
              "G2_HUMAN_VERIFICATION": "Potential danger, uncertainty, conflict, or insufficient automation evidence",
              "G3_HUMAN_CHANNEL": "A person is requested or operational follow-up needs a person",
              "G4_APPROVED_SERVICE": "Limited approved service response is eligible"}
    if effective == "IMMEDIATE_HUMAN":
        predicate = lambda e: e.get("value") is True and e.get("field") in {"personal_danger", "trapped", "evacuation_barrier"} and e.get("temporal") == "current" and e.get("provenance") != "reported" and e.get("intent") != "offering"
    else:
        predicate = None
    gate_evidence = [e for n in critical_needs for e in _evidence(n, rule_id, predicate)]
    manual_evidence = [e for n in critical_needs for e in _evidence(n, "H1_MANUAL_ESCALATION", lambda item: item.get("field") == "manual_escalation" and item.get("target_category") == effective)]
    if manual_evidence and (not gate_evidence or effective != "IMMEDIATE_HUMAN"):
        rule_id = "H1_MANUAL_ESCALATION"
        labels[rule_id] = "Identified human escalation; this is an operator decision, not a detected clinical fact"
        gate_evidence = manual_evidence
    if not gate_evidence and effective == "HUMAN_VERIFY":
        # Refusing automation for uninterpretable input still has a traceable
        # source: the exact revision that first created this clarification Need.
        # This records the input requiring review, not a detected hazard.
        for need in critical_needs:
            first = next((h for h in need.get("history", []) if h.get("kind") == "transcript_evidence"), None)
            original = next((r for r in call.get("revisions", []) if first and r["revision"] == first.get("revision")), None)
            if original is not None:
                gate_evidence.append({"rule_id": rule_id, "field": "uninterpreted_input", "value": "unknown",
                    "quote": original["text"], "call_id": call["id"], "need_id": need["id"],
                    "revision": original["revision"], "timestamp": original["timestamp"],
                    "source": "original_transcript_requiring_verification",
                    "explanation": "This exact input could not be completely admitted to approved automation; no danger is inferred from the quotation alone."})
    if not gate_evidence:
        rule_id = "F2_RETAINED_CATEGORY_NO_SOURCE"
        labels[rule_id] = "Retained unresolved category has no matching original evidence; human review required"
        gate_evidence = [{"rule_id": rule_id, "quote": None, "call_id": call["id"], "need_id": n["id"], "revision": None, "timestamp": None, "source": "legacy_category_no_source", "explanation": "No matching original quotation is available. The latest transcript is not substituted for missing historical evidence."} for n in critical_needs]
    triggers = [{"id": rule_id, "label": labels[rule_id], "evidence": gate_evidence}]
    if manual_evidence and rule_id != "H1_MANUAL_ESCALATION":
        triggers.append({"id": "H1_MANUAL_ESCALATION", "label": "Identified operator escalation also supports this category", "evidence": manual_evidence})
    if floor_applied:
        triggers.append({"id": "F1_UNRESOLVED_FLOOR", "label": "Earlier unresolved evidence is more urgent than the latest transcript; automatic downgrade is forbidden.", "evidence": gate_evidence})
    refusal_reasons = []
    if effective == "HUMAN_VERIFY":
        refusal_reasons = list(dict.fromkeys(reason for n in critical_needs for reason in n.get("reasons", [])))
        if not refusal_reasons:
            refusal_reasons = ["A complete approved automation interpretation is unavailable."]
    followup_needs = [n for n in active if n.get("transfer_status") in {"FAILED", "NO_ANSWER"} or n.get("callback_status") in {"NO_ANSWER", "MANUAL_FOLLOWUP", "PENDING_HUMAN_REVIEW"}]
    followup = bool(followup_needs) and effective != "AUTOMATION_ELIGIBLE" and transfer != "BRIDGED"
    followup_evidence = []
    if followup:
        for n in followup_needs:
            records = [h for h in n.get("history", []) if h.get("kind") in {"simulate_no_answer", "simulate_failure", "interrupted", "callback_no_answer"}]
            event = records[-1] if records else {}
            followup_evidence.append({"rule_id": "O2_CONTACT_FOLLOWUP", "quote": event.get("note", "") or "Contact is unconfirmed; this is an operational follow-up signal.", "call_id": call["id"], "need_id": n["id"], "revision": None, "timestamp": event.get("at"), "source": "operational_state", "transfer_status": n.get("transfer_status"), "callback_status": n.get("callback_status")})
        triggers.append({"id": "O2_CONTACT_FOLLOWUP", "label": "One bounded contact-follow-up addition per call", "evidence": followup_evidence})
    wait_points = min(WAIT_CAP_POINTS, int(waiting // WAIT_STEP_SECONDS)) if effective != "AUTOMATION_ELIGIBLE" else 0
    wait_evidence = [{"rule_id": "O1_BOUNDED_WAIT", "quote": "Accumulated per-call human queue waiting; automatic-service and connected time excluded.", "call_id": call["id"], "need_id": None, "revision": None, "timestamp": as_of, "source": call.get("queue_clock", {}).get("source", "legacy_need_wait_lower_bound"), "waiting_seconds": waiting}]
    anchor, upper = BANDS[effective]
    components = [
        {"code": "CATEGORY_ANCHOR", "label": labels[rule_id], "points": anchor, "cap": anchor, "evidence": gate_evidence},
        {"code": "BOUNDED_WAIT", "label": "One point per complete waiting minute, at most fifteen", "points": wait_points, "cap": WAIT_CAP_POINTS, "evidence": wait_evidence},
        {"code": "CONTACT_FOLLOWUP", "label": "Unconfirmed failed contact requires follow-up; counted once", "points": FOLLOWUP_POINTS if followup else 0, "cap": FOLLOWUP_POINTS, "evidence": followup_evidence},
    ]
    raw_score = sum(c["points"] for c in components)
    score = min(upper, max(anchor, raw_score))
    components.append({"code": "BAND_CLIP", "label": "Keep operational attention inside the evidence-gated category band", "points": score-raw_score, "cap": 0, "evidence": []})
    if category_for_score(score) != effective:
        raise ValueError("Scoring contract violated: category band changed")
    fields = call.get("extraction", {}).get("fields", {})
    unknown_fields = sorted(k for k, v in fields.items() if v.get("value") == "unknown")
    location = call.get("location") or {}
    missing_location = not (location.get("label") or (location.get("lat") is not None and location.get("lon") is not None))
    uncertainty_items = list(dict.fromkeys(u for n in active for u in n.get("uncertainties", [])))
    if unknown_fields:
        uncertainty_items.append("Latest transcript unknown fields: " + ", ".join(unknown_fields))
    if missing_location:
        uncertainty_items.append("Location is missing; the category and index are not reduced.")
    if call.get("queue_clock", {}).get("source") == "legacy_need_wait_lower_bound":
        uncertainty_items.append("Historical queue age is a reconstructed lower bound from a pre-scoring database; later waiting is measured by the per-call clock.")
    if any(e.get("provenance") == "reported" for n in active for e in n.get("evidence", [])):
        uncertainty_items.append("Reported wording is not verified independent evidence.")
    override = copy.deepcopy(call.get("queue_override"))
    return {"call_id": call["id"], "policy_version": POLICY_VERSION, "extraction_rule_version": call.get("extraction", {}).get("rule_version"),
            "assessed_at": as_of, "score": score, "raw_score": raw_score, "name": "Human Attention Index", "band": {"min": anchor, "max": upper},
            "category": effective, "effective_category": effective, "latest_text_category": latest, "safety_floor_applied": floor_applied,
            "components": components, "gate": {"rule_ids": [t["id"] for t in triggers if t["id"].startswith(("G", "F", "H"))], "decision": effective,
              "source_need_ids": [n["id"] for n in critical_needs], "evidence": gate_evidence, "refusal_reasons": refusal_reasons},
            "trigger_rules": triggers, "uncertainty": {"items": list(dict.fromkeys(uncertainty_items)), "unknown_fields": unknown_fields, "missing_location": missing_location, "not_scored": True, "is_probability": False},
            "unresolved_need_ids": [n["id"] for n in active], "waiting_seconds": waiting,
            "queue_clock": copy.deepcopy(call.get("queue_clock")),
            "overdue": overdue, "overdue_after_seconds": overdue_after_seconds, "transfer_status": transfer,
            "queue_eligible": queue_eligible, "manual_override": override,
            "parameters": {"wait_step_seconds": WAIT_STEP_SECONDS, "wait_cap_points": WAIT_CAP_POINTS, "followup_points": FOLLOWUP_POINTS, "overdue_after_seconds": overdue_after_seconds},
            "score_semantics": SCORE_SEMANTICS, "sort_policy": SORT_POLICY}
