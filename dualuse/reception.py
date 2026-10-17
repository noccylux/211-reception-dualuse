"""The reception agent: Claude writes each reply from the playbooks; the desk owns queue and handoff facts."""

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel

from dualuse.extract import Classification, Extraction, EXTRACTION_MODEL, classify_with_rules, fields_to_tier
from dualuse.profiles import fallback_question

PLAYBOOKS = Path(__file__).parent / "playbooks"
MAX_REPLY = 1200
Topic = Literal["situation", "location", "safety", "need", "detail", "wait"]


class AgentTurn(BaseModel):
    extraction: Extraction
    topic: Topic
    reply: str
    language_code: str
    distress: Literal["calm", "worried", "distressed", "unknown"]


@dataclass(frozen=True)
class ReceptionTurn:
    classification: Classification
    topic: str
    reply: str
    review: str = ""  # what the operator should double-check; empty when nothing was flagged
    language: str = ""  # BCP 47 code the caller writes in; empty keeps the call's current language
    distress: str = ""


@functools.cache
def system_prompt() -> str:
    """core.md first, then the other playbooks in name order; stable text, so it caches."""
    files = sorted(PLAYBOOKS.glob("*.md"), key=lambda path: (path.name != "core.md", path.name))
    return "\n\n".join(path.read_text(encoding="utf-8").strip() for path in files)


def _plain_schema(value):
    # The provider rejects some annotation-only keys from Pydantic's schema.
    if isinstance(value, dict):
        return {k: _plain_schema(v) for k, v in value.items() if k not in {"title", "default", "maxLength"}}
    if isinstance(value, list):
        return [_plain_schema(v) for v in value]
    return value


@functools.cache
def _schema() -> dict:
    schema = _plain_schema(AgentTurn.model_json_schema())
    # Structured outputs require every property to be present and disallow extras.
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
            obj["required"] = list(obj["properties"])
    return schema


def _messages(dialogue: list[dict], facts: str) -> list[dict]:
    """Caller turns as user, everything said to the caller as assistant, then this turn's desk facts."""
    messages = []
    for turn in dialogue:
        role = "user" if turn["speaker"] == "caller" else "assistant"
        if messages or role == "user":  # the API starts with a user turn; the welcome is in the facts
            messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "system", "content": f"Desk facts for this turn (from the application, not the caller):\n{facts}"})
    return messages


def model_turn(dialogue: list[dict], facts: str = "", client=None) -> ReceptionTurn:
    client = client or anthropic.Anthropic(timeout=20.0, max_retries=0)
    response = client.messages.create(
        model=EXTRACTION_MODEL, max_tokens=1600,
        system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": _schema()}, "effort": "low"},
        messages=_messages(dialogue, facts),
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"Interview did not complete ({response.stop_reason})")
    block = next((b for b in response.content if b.type == "text"), None)
    if block is None:
        raise RuntimeError("Interview returned no structured text")
    result = AgentTurn.model_validate_json(block.text)
    extraction, review = _checked(result.extraction, dialogue)
    reply = result.reply.strip()
    if not reply or len(reply) > MAX_REPLY:
        reply = fallback_question(result.topic, result.language_code)
    return ReceptionTurn(Classification(extraction, fields_to_tier(extraction), "model"), result.topic, reply,
                         review, result.language_code, result.distress)


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalized(text: str) -> str:
    return " ".join(text.casefold().translate(_QUOTES).split())


def _checked(extraction: Extraction, dialogue: list[dict]) -> tuple[Extraction, str]:
    """Keep what the caller's words support and flag the rest, so one bad field never discards a life threat."""
    caller_text = _normalized(" ".join(t["text"] for t in dialogue if t["speaker"] == "caller"))
    verified = [quote for quote in extraction.evidence if quote.strip() and _normalized(quote) in caller_text]
    notes = []
    unverified = [quote for quote in extraction.evidence if quote not in verified]
    if unverified:
        notes.append("Unverified quotes dropped: " + "; ".join(unverified))
    location = extraction.location
    # A location may combine short answers ("Oak Street", "number 12"); every part must come from the caller.
    if location and not all(token in caller_text for token in re.findall(r"\w+", _normalized(location))):
        notes.append(f"Location not in the caller's words, dropped: {location}")
        location = None
    if extraction.life_threat_now and not verified:
        notes.append("Life threat reported without a verified caller quote")
    return extraction.model_copy(update={"evidence": verified, "location": location}), "; ".join(notes)


SCRIPTS = (  # (language code, English name, character range) for scripts the English keywords cannot read
    ("zh", "Chinese", "一-鿿"), ("ko", "Korean", "가-힯"), ("ja", "Japanese", "぀-ヿ"),
    ("ar", "Arabic", "؀-ۿ"), ("hy", "Armenian", "԰-֏"), ("ru", "Russian", "Ѐ-ӿ"),
)


def rules_turn(dialogue: list[dict]) -> ReceptionTurn:
    """Explicitly labeled English baseline; model mode never silently falls back to it."""
    text = "\n".join(t["text"] for t in dialogue if t["speaker"] == "caller")
    unreadable = next(((code, name) for code, name, chars in SCRIPTS if re.search(f"[{chars}]", text)), None)
    if unreadable:
        code, name = unreadable
        review = f"{name} text: the offline English keyword mode cannot read it; a person who reads {name} should review"
        return ReceptionTurn(classify_with_rules(text), "situation", fallback_question("situation", code), review, code)
    result = classify_with_rules(text)
    asked = {t.get("topic") for t in dialogue if t["speaker"] == "assistant"}
    last = next((t["text"].lower() for t in reversed(dialogue) if t["speaker"] == "caller"), "")
    x = result.extraction
    candidates = []
    if not x.enough_information:
        candidates.append("situation")
    if x.safety == "unknown":
        candidates.append("safety")
    if not x.location:
        candidates.append("location")
    if not x.need and not x.report_only:
        candidates.append("need")
    candidates.append("detail")
    topic = next((item for item in candidates if item not in asked), "wait")
    if any(p in last for p in ("just wait", "stop asking", "wait for a person", "nothing else", "that's all")):
        topic = "wait"
    return ReceptionTurn(result, topic, fallback_question(topic, "en"))


def receive(dialogue: list[dict], mode: str, facts: str) -> ReceptionTurn:
    return model_turn(dialogue, facts) if mode == "model" else rules_turn(dialogue)
