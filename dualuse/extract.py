"""Turn what a waiting caller said into structured fields, then into a tier.

The language model only fills fields; `fields_to_tier` decides, so every tier
is explainable from the fields and the rules can change without retraining.
A keyword baseline covers the no-model case and the comparison. Design:
docs/architecture.md, sections "Tiers" and "Components".
"""

import os
import re
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from dualuse.triage import Tier

EXTRACTION_MODEL = "claude-haiku-5-5"


class Extraction(BaseModel):
    situation: str = Field(description="What is happening, one sentence in English.")
    need: str = Field(description="What the caller asks for, one sentence in English; empty if not stated.")
    location: str | None = Field(description="Where, exactly as the caller stated it; null if not stated.")
    life_threat_now: bool = Field(
        description="Someone is in physical danger right now: trapped, fire or smoke at their location, "
        "a medical emergency, violence in progress."
    )
    needs_person_soon: bool = Field(
        description="Urgent but not life-threatening: no shelter tonight, medication or oxygen running out, "
        "a missing person, a minor or a dependent adult without care."
    )
    enough_information: bool = Field(description="The caller said enough to judge the two risk fields above.")
    evidence: list[str] = Field(description="The caller's own words that support the risk judgment, verbatim.")
    missing: list[str] = Field(description="Key facts still unknown that an operator would need.")
    language: str = Field(description="The caller's language, as an English name.")
    incident_kind: Literal["fire", "medical", "utility", "crime", "other", "none"] = "none"
    report_only: bool = False
    safety: Literal["unknown", "danger", "no_immediate_danger"] = "unknown"


@dataclass(frozen=True)
class Classification:
    extraction: Extraction
    tier: Tier
    source: str  # "model" or "rules"


def fields_to_tier(extraction: Extraction) -> Tier:
    """The deterministic rules that turn fields into a tier."""
    if extraction.life_threat_now:
        return Tier.IMMEDIATE
    if extraction.needs_person_soon:
        return Tier.PRIORITY
    if not extraction.enough_information:
        return Tier.UNKNOWN
    return Tier.NORMAL


# Keyword baseline, English only. Phrases, not single words, so "fire damage
# claim" does not read as a fire in progress.
IMMEDIATE_PHRASES = (
    "on fire",
    "is burning",
    "flames",
    "smoke inside",
    "smoke in the house",
    "trapped",
    "can't get out",
    "cannot get out",
    "can't get him out",
    "can't get her out",
    "not breathing",
    "can't breathe",
    "unconscious",
    "bleeding",
    "chest pain",
    "heart attack",
    "stroke",
    "collapsed",
    "drowning",
    "gun*",
    "shooting",
    "shots fired",
    "was shot",
    "been shot",
    "got shot",
    "stabbed",
    "overdos*",
    "is inside",
    "calling for help from inside",
    "shouting for help",
    "suicide",
    "suicidal",
)
PRIORITY_PHRASES = (
    "nowhere to sleep",
    "no shelter",
    "no place to stay",
    "evacuate",
    "evacuated",
    "evacuating",
    "evacuation",
    "oxygen",
    "medication",
    "insulin",
    "dialysis",
    "power is off",
    "power is out",
    "missing",
    "can't find my",
    "wheelchair",
    "elderly",
    "disabled",
    "pregnant",
    "no water",
    "no food",
    "running out",
)


FIRE_WORDS = ("smoke", "flames", "fire", "wildfire")
HAZARD_PHRASES = FIRE_WORDS + ("power line", "gas leak")
ROUTINE_PHRASES = ("freeway", "fema", "calfresh", "benefits", "food pantry", "assistance", "fire damage")
# Removed before matching: these mention a hazard word without reporting a hazard.
NOT_A_REPORT = re.compile(r"\b(?:fire damage|smoke (?:detector|alarm)s?|(?:nobody|no one) is inside)\b")


_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})


def _found(text: str, phrases: tuple[str, ...]) -> dict[str, str]:
    """Phrase -> the caller's matching words. Whole words with an optional plural ('fire' matches
    'fires', not 'fired'); a trailing '*' marks a stem ('gun*' matches 'gunfire', not 'begun')."""
    lowered = text.lower().translate(_APOSTROPHES)
    found = {}
    for phrase in phrases:
        body = re.escape(phrase.rstrip("*"))
        match = re.search(rf"(?<!\w){body}\w*" if phrase.endswith("*") else rf"(?<!\w){body}(?:e?s)?(?!\w)", lowered)
        if match:
            found[phrase] = match.group(0)
    return found


def _matches(text: str, phrases: tuple[str, ...]) -> list[str]:
    return list(_found(text, phrases))


def classify_with_rules(text: str) -> Classification:
    """Fields from keywords alone: the degraded mode and the comparison baseline."""
    reported = NOT_A_REPORT.sub(" ", text.lower())
    immediate = list(_found(reported, IMMEDIATE_PHRASES).values())
    priority = list(_found(text, PRIORITY_PHRASES).values())
    hazard = _matches(reported, HAZARD_PHRASES)
    routine = bool(_matches(text, ROUTINE_PHRASES))
    enough = bool(immediate or priority or hazard or routine)
    place = re.search(r"\b(?:at|on|near|above)\s+((?:\d{1,5}\s+)?(?:[A-Za-z'-]+\s+){1,3}(?:Street|St|Road|Rd|Avenue|Ave|Drive|Lane|Boulevard))\b", text, re.I)
    location = place.group(1).strip() if place else None
    if not location:
        # A short answer to a location question may have no preposition.
        place = re.search(r"^(?:\d{1,5}\s+)?(?:[A-Za-z'-]+\s+){1,3}(?:Street|St|Road|Rd|Avenue|Ave|Drive|Lane|Boulevard)[.!]?$", text.splitlines()[-1], re.I) if text.strip() else None
        location = place.group(0).rstrip(".!") if place else None
    missing = [] if enough else ["what is happening", "what the caller needs"]
    if not location:
        missing.append("where the caller is")
    safe = any(p in text.lower() for p in ("nobody is hurt", "no one is hurt", "i am safe", "i'm safe", "we are safe"))
    if not immediate and not safe:
        missing.append("whether anyone is in immediate danger")
    extraction = Extraction(
        situation=text.strip()[:160] or "(the caller has not said anything yet)",
        need="",
        location=location,
        life_threat_now=bool(immediate),
        needs_person_soon=bool(priority or hazard),
        enough_information=enough,
        evidence=immediate + priority,
        missing=missing,
        language="not detected (rules)",
        incident_kind="fire" if set(hazard) & set(FIRE_WORDS) else "utility" if hazard else "medical" if immediate else "none",
        report_only=bool(hazard) and any(p in text.lower() for p in ("i see", "i saw", "report")) and not immediate,
        safety="danger" if immediate else "no_immediate_danger" if safe else "unknown",
    )
    return Classification(extraction, fields_to_tier(extraction), "rules")


def keyword_tier(text: str) -> Tier:
    return classify_with_rules(text).tier


SYSTEM_PROMPT = (
    "You read what a caller said while waiting on hold for a 211 community and disaster assistance line. "
    "Fill the fields from the caller's words only; quote them as evidence and never invent a location. "
    "life_threat_now means someone is in physical danger right now. needs_person_soon means urgent but not "
    "life-threatening. enough_information is false when the caller has not yet said what is happening or "
    "what they need. Write situation and need in English, one sentence each, whatever language the caller "
    "used, and name that language."
)


def model_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def classify_with_model(
    text: str, client: anthropic.Anthropic | None = None, model: str = EXTRACTION_MODEL
) -> Classification:
    """Fields from Claude with a validated schema; the tier still comes from the rules."""
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text or "(the caller has not said anything yet)"}],
        output_format=Extraction,
        output_config={"effort": "low"},  # per-turn extraction sits on the voice path; keep it quick
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"extraction failed: stop_reason={response.stop_reason}")
    extraction = response.parsed_output
    return Classification(extraction, fields_to_tier(extraction), "model")


TIER_LABELS = {
    Tier.IMMEDIATE: "IMMEDIATE, life-threatening now",
    Tier.PRIORITY: "PRIORITY, needs a person soon",
    Tier.UNKNOWN: "UNKNOWN, not enough information, kept with priority",
    Tier.NORMAL: "NORMAL, can wait",
}


def format_wait(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def handoff_summary(extraction: Extraction, tier: Tier, waited_s: float) -> str:
    """The card the operator sees at transfer: fixed fields, the caller's words as evidence, and gaps."""
    evidence = "; ".join(f'"{quote}"' for quote in extraction.evidence) or "no risk words from the caller"
    return "\n".join(
        [
            f"Tier: {TIER_LABELS[tier]}",
            f"Waited: {format_wait(waited_s)}",
            f"Situation: {extraction.situation}",
            f"Need: {extraction.need or 'not stated'}",
            f"Location: {extraction.location or 'not confirmed'}",
            f"Why this tier: {evidence}",
            f"Still unknown: {', '.join(extraction.missing) or 'nothing flagged'}",
            f"Language: {extraction.language}",
        ]
    )
