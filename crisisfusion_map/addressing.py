"""Conservative, auditable address *format* assessment for map review.

This is a bounded local recognizer, not an address database, geocoder or accuracy
model. A matched street address may not exist. Human confirmation is an operator
attestation, not independent verification. Device location belongs to a separate
map layer and must never become an incident address implicitly.
"""
from __future__ import annotations

import math
import re
import unicodedata

RULE_VERSION = "address-review-2026-10-17-v1"
_SUFFIX = r"(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|lane|ln|court|ct|way|place|pl|terrace|ter|parkway|pkwy|highway|hwy|circle|cir)\.?"
_LATIN = r"A-Za-zÀ-ÖØ-öø-ÿ\u0100-\u024f"
_WORD = rf"[{_LATIN}0-9][{_LATIN}0-9.'’\-]*"
_STREET = rf"(?:{_WORD}[ \t]+){{1,5}}?{_SUFFIX}(?![{_LATIN}0-9_])"
_CIVIC = re.compile(rf"(?<![{_LATIN}0-9_])\d{{1,6}}(?:-\d{{1,6}})?[ \t]+{_STREET}(?:[ \t]*,?[ \t]+(?:apt\.?|apartment|unit|suite|ste\.?|#)[ \t]*[A-Za-z0-9-]+)?", re.I)
_INTERSECTION = re.compile(rf"(?<![{_LATIN}0-9_]){_STREET}[ \t]*(?:&|\band\b|\bat\b|\by\b|与|和)[ \t]*{_STREET}", re.I)
_CHINESE_CIVIC = re.compile(r"[\u4e00-\u9fff]{1,14}(?:大街|大道|街|路|巷)\s*\d{1,6}\s*号")
_AREAS = re.compile(r"\b(?:Los Angeles(?: County)?|LA County|downtown LA|Santa Monica|Long Beach|Pasadena|Hollywood|Westwood|Burbank|Glendale|Compton|Torrance|Inglewood|Malibu|Lancaster|Palmdale|USC|University of Southern California)\b|洛杉矶(?:县|市)?|南加州大学|帕萨迪纳|圣莫尼卡|长滩", re.I)
_PLACE = re.compile(r"\b(?:[A-Z][A-Za-z'’-]*[ \t]+){1,3}(?:Hall|Hospital|School|Station|Library|Shelter|Mall|Park)\b")
_LA_LOCALITY = r"\b(?:Los Angeles|LA County|Santa Monica|Long Beach|Pasadena|CA|California|9\d{4})\b|洛杉矶|加州"
_EMPTY = {"", "unknown", "unknown location", "unspecified", "n a", "na", "none", "null", "unavailable", "not provided", "未知", "不详", "未提供", "不知道"}
_ALIASES = {"street":"st", "avenue":"ave", "boulevard":"blvd", "road":"rd", "drive":"dr", "lane":"ln", "court":"ct", "place":"pl", "terrace":"ter", "parkway":"pkwy", "highway":"hwy", "circle":"cir", "north":"n", "south":"s", "east":"e", "west":"w"}
_RANK = {"civic_address": 4, "intersection": 3, "named_place": 2, "area": 1, "unknown": 0}


def _normal(value):
    value = "".join(c for c in unicodedata.normalize("NFKD", str(value).lower()) if not unicodedata.combining(c))
    words = re.findall(r"[\w-]+", value, re.UNICODE)
    return " ".join(_ALIASES.get(w, w) for w in words)


def _point(record):
    if not isinstance(record, dict):
        return None
    values = [record.get("lat"), record.get("lon")]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return None
    if abs(values[0]) > 90 or abs(values[1]) > 180:
        return None
    source = str(record.get("source") or "caller_reported_coordinates")
    if any(s in source.lower() for s in ("geolocation", "device", "gps")):
        return None
    result = {"lat": values[0], "lon": values[1], "source": source, "accuracy_m": None}
    accuracy = record.get("accuracy_m")
    if not isinstance(accuracy, bool) and isinstance(accuracy, (int, float)) and math.isfinite(accuracy) and accuracy >= 0:
        result["accuracy_m"] = accuracy
    return result


def _context(value, start, end):
    # Sentence/clause boundaries prevent "not injured; at 123 Main St" from
    # negating the address. The cue must immediately precede the mention.
    prefix = re.split(r"[.;!?\n。；！？]|\bbut\b|\bpero\b|但是|不过", value[:start], flags=re.I)[-1][-100:]
    suffix = value[end:end+28]
    negated = bool(re.search(r"(?:\b(?:not|never|no|ni|nowhere)\s+(?:(?:currently|at|in|near|en|estoy|estamos|located|live|living|cerca|de)\s+){0,5}|(?:不在|不是|不住在|并非|并不在)\s*)$", prefix, re.I))
    historical = bool(re.search(r"\b(?:used to (?:live|be)|was (?:at|in)|were (?:at|in)|previously|formerly|yesterday|ayer|antes|estaba en|vivía en|vivia en)\b|以前|之前|曾经|昨天|原来", prefix, re.I))
    historical = historical or bool(re.match(r"\s*(?:,?\s*(?:yesterday|last (?:week|night|year)|ayer)\b|是以前|是之前|是原来)", suffix, re.I))
    if re.search(r"\b(?:now|currently|today|ahora|hoy)\b|现在|目前|今天", prefix, re.I):
        historical = False
    uncertain = bool(re.search(r"\b(?:maybe|perhaps|possibly|not sure|unsure|somewhere|quiz[aá]s|tal vez)\b|可能|大概|不确定|好像", prefix, re.I))
    approximate = bool(re.search(r"\b(?:near|around|close to|cerca de|por)\s*$|(?:附近|靠近)\s*$", prefix, re.I) or re.match(r"\s*(?:附近|周边)", suffix))
    reported = bool(re.search(r"\b(?:heard|someone said|they said|report says|rumou?r|dicen|me dijeron)\b|听说|据说|传闻|别人说", prefix, re.I))
    return dict(negated=negated, historical=historical, uncertain=uncertain, approximate=approximate, reported=reported)


def _mentions(value, revision, source, timestamp, *, label=False):
    value = str(value or "")
    if _normal(value) in _EMPTY:
        return []
    found = []
    spans = []
    for kind, pattern in (("civic_address", _CIVIC), ("civic_address", _CHINESE_CIVIC), ("intersection", _INTERSECTION), ("named_place", _PLACE), ("area", _AREAS)):
        for match in pattern.finditer(value):
            start, end = match.span()
            if any(start < other_end and end > other_start for other_start, other_end in spans):
                continue
            quote = match.group()
            if kind in {"intersection", "named_place"}:
                # Bound the shared English street grammar at conversational
                # lead-ins while keeping the exact substring and offsets.
                trimmed = re.sub(r"^(?:(?:I am|We are|I live|Estoy|Estamos|I am located)\s+)?(?:at|in|near|en|cerca de)\s+", "", quote, flags=re.I)
                start += len(quote)-len(trimmed)
                quote = trimmed
            elif pattern is _CHINESE_CIVIC:
                trimmed = re.sub(r"^(?:我(?:们)?)?(?:(?:现在|目前|以前|之前|曾经|原来|昨天))?(?:不在|在|位于|住在)", "", quote)
                start += len(quote)-len(trimmed)
                quote = trimmed
            spans.append((start, end))
            normalized = _normal(quote)
            if kind == "intersection":
                normalized = " & ".join(sorted(_normal(part) for part in re.split(r"\s*(?:&|\band\b|\bat\b|\by\b|与|和)\s*", quote, flags=re.I)))
            found.append({"quote": quote, "normalized": normalized, "kind": kind,
                          "revision": revision, "source": source, "timestamp": timestamp,
                          "span": [start, end], **_context(value, start, end)})
    if label and not found:
        found.append({"quote": value, "normalized": _normal(value), "kind": "named_place",
                      "revision": revision, "source": source, "timestamp": timestamp,
                      "span": [0, len(value)], **_context(value, 0, len(value))})
    return sorted(found, key=lambda c: c["span"][0])


def assess_address(call, confirmation=None, locality=None):
    """Return an independent, JSON-safe map assessment without mutating inputs.

    ``locality`` is the service area's regex for wording that names its city or
    postal code; the default is the Los Angeles County wording.

    ``confirmation`` is either an operator attestation or an unconfirmed map/
    geocoder point. Its revision must equal the current call revision to remain
    confirmed. No external services are called and no coordinates are inferred.
    """
    call = call or {}
    latest = call.get("revision", 1)
    revisions = [r for r in call.get("revisions", []) if isinstance(r, dict)]
    if not any(r.get("revision") == latest for r in revisions):
        revisions = revisions + [{"revision": latest, "text": call.get("text", ""), "location": call.get("location"), "timestamp": call.get("timestamp")}]
    candidates = []
    for rev in revisions:
        revision = rev.get("revision", latest)
        timestamp = rev.get("timestamp")
        location = rev.get("location") or {}
        candidates.extend(_mentions(rev.get("text", ""), revision, "transcript", timestamp))
        if isinstance(location, dict):
            candidates.extend(_mentions(location.get("label"), revision, "location_label:"+str(location.get("source") or "caller_reported"), timestamp, label=True))
    flags = []
    reasons = []
    for key, flag in (("negated", "negated_address_mention"), ("historical", "historical_address_mention"), ("uncertain", "uncertain_address_mention"), ("approximate", "approximate_location"), ("reported", "secondhand_location")):
        if any(c[key] for c in candidates):
            flags.append(flag)
    usable = [c for c in candidates if not c["negated"] and not c["historical"]]
    highest = max((_RANK[c["kind"]] for c in usable), default=0)
    specific = [c for c in usable if _RANK[c["kind"]] == highest]
    current = [c for c in specific if c["revision"] == latest]
    selected = (current or specific)[-1] if specific else None
    if selected and selected["revision"] != latest:
        flags.append("address_from_prior_revision")
    # Same civic address with a long/abbreviated suffix is one claim. Different
    # street addresses across revisions remain visible until a person resolves.
    distinct = {c["normalized"] for c in specific}
    conflict = highest >= 3 and len(distinct) > 1
    if conflict:
        flags.append("multiple_specific_addresses")
        if len({c["revision"] for c in specific}) > 1:
            flags.append("address_changed_between_revisions")
    retracted = any(c["negated"] and c["revision"] == latest and c["normalized"] in distinct for c in candidates)
    if retracted:
        conflict = True
        flags.append("previous_address_retracted")
    location = call.get("location") or {}
    coordinates = _point(location)
    if isinstance(location, dict) and any(s in str(location.get("source", "")).lower() for s in ("geolocation", "device", "gps")):
        flags.append("device_coordinates_excluded")
    confirmation = confirmation if isinstance(confirmation, dict) else {}
    confirmed_point = _point(confirmation)
    stale = bool(confirmation) and confirmation.get("revision") != latest
    if stale:
        flags.append("stale_confirmation")
        old_mentions = _mentions(confirmation.get("label") or confirmation.get("matched_address"), confirmation.get("revision"), "prior_confirmation", confirmation.get("confirmed_at"), label=True)
        old_specific = {c["normalized"] for c in old_mentions if _RANK[c["kind"]] >= 3}
        if current and old_specific and not old_specific.intersection(c["normalized"] for c in current):
            conflict = True
            flags.append("current_address_differs_from_stale_point")
    verified = bool(confirmation.get("confirmed") is True and not stale and confirmed_point and str(confirmation.get("reviewer") or "").strip() and confirmation.get("confirmed_at"))
    if confirmation.get("confirmed") is True and not verified and not stale:
        flags.append("incomplete_confirmation")
    if confirmed_point:
        coordinates = {**confirmed_point, "stale": stale, "revision": confirmation.get("revision")}
    label = str(confirmation.get("label") or confirmation.get("matched_address") or "") if confirmed_point else ""
    label = label or (selected["quote"] if selected else "")
    if verified:
        status = "HUMAN_CONFIRMED"
        reasons.append("A local operator confirmed this point for the current transcript revision; this is not independent address validation.")
        if conflict:
            flags.append("conflict_resolved_by_operator")
    elif conflict:
        status = "CONFLICT"
        reasons.append("Distinct or retracted specific address claims need a person to choose the incident location.")
    elif coordinates:
        status = "LOCATED_UNCONFIRMED"
        reasons.append("An explicit incident point is available, but its address and current relevance are unconfirmed.")
    elif selected and highest >= 3:
        status = "ADDRESS_CANDIDATE"
        reasons.append("Street-address or intersection syntax was recognized; existence, uniqueness and position have not been validated.")
    elif selected:
        status = "AREA_ONLY"
        reasons.append("Only an area or named-place reference is available; it does not identify a dispatchable street address.")
    else:
        status = "NO_ADDRESS"
        reasons.append("No supported current address reference was recognized. This does not prove that the caller gave no address.")
    kind = selected["kind"] if selected else "unknown"
    missing = []
    if not selected:
        missing.append("address_reference")
    elif kind not in {"civic_address", "intersection"}:
        missing.append("street_address_or_cross_streets")
    elif kind == "intersection":
        missing.append("building_number_or_exact_side")
    if not coordinates:
        missing.append("incident_coordinates")
    if not verified:
        missing.append("human_confirmation")
    if selected and not re.search(locality or _LA_LOCALITY, str(call.get("text", ""))+" "+str(location.get("label", "") if isinstance(location, dict) else ""), re.I):
        missing.append("city_or_postal_code")
    if conflict and not verified:
        missing.append("conflict_resolution")
    if call.get("input_mode") == "browser_voice":
        flags.append("asr_transcription_unverified")
    return {"rule_version": RULE_VERSION, "call_id": call.get("call_id") or call.get("id"),
            "revision": latest, "status": status, "address_kind": kind, "display_label": label,
            "source": (confirmation.get("source") if confirmed_point else None) or (selected["source"] if selected else None) or (coordinates["source"] if coordinates else None),
            "candidates": candidates, "coordinates": coordinates,
            "coordinate_role": "reported_incident" if coordinates else None,
            "flags": list(dict.fromkeys(flags)), "reasons": reasons, "missing_fields": missing,
            "completeness": "street_reference" if highest >= 3 else ("place_or_area" if selected else "none"),
            "measured_accuracy": {"value": None, "unit": None, "validation": "not_measured"},
            "verification": {"confirmed": verified, "reviewer": confirmation.get("reviewer") if verified else None,
                             "confirmed_at": confirmation.get("confirmed_at") if verified else None,
                             "scope": "local_operator_attestation_only" if verified else "unverified"}}
