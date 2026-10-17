"""HTTP service: the hold-queue assistant's backend and the demo UI's data source.

One in-memory queue per process; `POST /reset` clears it. Run:
bash scripts/uv-run.sh uvicorn dualuse.api:app --reload --host 0.0.0.0 --port 8000
"""

import math
from typing import Literal

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from dualuse import extract
from dualuse.extract import Classification, Extraction
from dualuse.holdqueue import HeldCall, HoldQueue
from dualuse.samples import SAMPLES
from dualuse.surge import SurgeSpec, three_policy_comparison
from dualuse.triage import Tier

MAX_NORMAL_WAIT_S = 1800  # the aging guard

INVARIANTS = [
    "The assistant never ends a call; a caller leaves only when served or when they choose to hang up.",
    "It never tells a caller they are not urgent and never makes the final decision; it orders the hold queue.",
    "When an operator is free, the head of the queue transfers at once, even mid-sentence.",
    "Insufficient or conflicting information is ordered as priority, never as normal.",
    f"A normal-tier caller is promoted after {MAX_NORMAL_WAIT_S // 60} minutes, so reordering delays anyone by a bounded amount.",
    "It never contacts outside agencies on its own; the supervisor presses that button.",
    "If the model or the network is unavailable, the queue is plain FIFO, which is today's behavior.",
]

Mode = Literal["model", "rules", "fifo"]

app = FastAPI(title="Hold-queue assistant, 211 demo")


def default_mode() -> Mode:
    return "model" if extract.model_available() else "rules"


QUEUE = HoldQueue(max_normal_wait=MAX_NORMAL_WAIT_S)
QUEUE.mode = default_mode()


class NewCall(BaseModel):
    text: str | None = None


class Utterance(BaseModel):
    text: str = Field(min_length=1)


class ModeChange(BaseModel):
    mode: Mode


class Reset(BaseModel):
    mode: Mode | None = None


class TierMix(BaseModel):
    immediate: float
    priority: float
    normal: float


class SimulateRequest(BaseModel):
    duration_s: float
    arrivals_per_hour: float
    operators: int = Field(ge=1)
    tier_mix: TierMix
    mean_service_s: float
    mean_patience_s: float | None = Field(description="null means callers never hang up")
    decision_delay_s: float
    miss_rate: float = Field(ge=0, le=1)
    false_alarm_rate: float = Field(ge=0, le=1)
    seed: int
    max_normal_wait_s: float = Field(gt=0)


def record_only(transcript: str) -> Classification:
    """FIFO mode: keep the transcript, classify nothing."""
    extraction = Extraction(
        situation=transcript[:160],
        need="",
        location=None,
        life_threat_now=False,
        needs_person_soon=False,
        enough_information=False,
        evidence=[],
        missing=["classification is off in FIFO mode"],
        language="not detected",
    )
    return Classification(extraction, Tier.UNKNOWN, "none")


def classify(transcript: str) -> Classification:
    if QUEUE.mode == "model":
        try:
            return extract.classify_with_model(transcript)
        except anthropic.APIError as error:
            raise HTTPException(502, f"Claude extraction failed: {type(error).__name__}: {error}") from error
    if QUEUE.mode == "rules":
        return extract.classify_with_rules(transcript)
    return record_only(transcript)


def set_mode(mode: Mode) -> None:
    if mode == "model" and not extract.model_available():
        raise HTTPException(409, "ANTHROPIC_API_KEY is not set; model mode is unavailable")
    QUEUE.mode = mode


def call_dict(call: HeldCall, fifo_positions: dict[str, int], tiered_positions: dict[str, int]) -> dict:
    return {
        "call_id": call.call_id,
        "arrival": call.arrival,
        "waited_s": QUEUE.now() - call.arrival,
        "tier": call.tier.value,
        "source": call.source,
        "transcript": call.transcript,
        "extraction": call.extraction.model_dump() if call.extraction else None,
        "fifo_position": fifo_positions[call.call_id],
        "tiered_position": tiered_positions[call.call_id],
    }


def one_call(call: HeldCall) -> dict:
    fifo = {item.call_id: i for i, item in enumerate(QUEUE.order("fifo"))}
    tiered = {item.call_id: i for i, item in enumerate(QUEUE.order("tiered"))}
    return call_dict(call, fifo, tiered)


def state() -> dict:
    fifo = {item.call_id: i for i, item in enumerate(QUEUE.order("fifo"))}
    tiered_order = QUEUE.order("tiered")
    tiered = {item.call_id: i for i, item in enumerate(tiered_order)}
    return {
        "mode": QUEUE.mode,
        "model_available": extract.model_available(),
        "active_policy": QUEUE.active_policy,
        "max_normal_wait_s": MAX_NORMAL_WAIT_S,
        "invariants": INVARIANTS,
        "waiting": [call_dict(call, fifo, tiered) for call in tiered_order],
        "clusters": QUEUE.clusters(),
        "handoffs": [handoff_dict(handoff) for handoff in QUEUE.handoffs[-20:]],
        "departed": [
            {"call_id": d.call_id, "waited_s": d.waited_s, "reason": d.reason, "at": d.at} for d in QUEUE.departed[-20:]
        ],
    }


def handoff_dict(handoff) -> dict:
    return {
        "call_id": handoff.call_id,
        "tier": handoff.tier.value,
        "waited_s": handoff.waited_s,
        "summary": handoff.summary,
        "transcript": handoff.transcript,
        "extraction": handoff.extraction.model_dump() if handoff.extraction else None,
        "at": handoff.at,
    }


def waiting_call(call_id: str) -> None:
    if call_id not in {call.call_id for call in QUEUE.order("fifo")}:
        raise HTTPException(404, f"no call {call_id} is waiting")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
def get_state() -> dict:
    return state()


@app.post("/calls", status_code=201)
def new_call(body: NewCall) -> dict:
    call = QUEUE.add()
    if body.text:
        QUEUE.say(call.call_id, body.text, classify)
    return one_call(call)


@app.post("/calls/{call_id}/say")
def say(call_id: str, body: Utterance) -> dict:
    waiting_call(call_id)
    return one_call(QUEUE.say(call_id, body.text, classify))


@app.post("/calls/{call_id}/hangup")
def hang_up(call_id: str) -> dict:
    waiting_call(call_id)
    departure = QUEUE.hang_up(call_id)
    return {"call_id": departure.call_id, "waited_s": departure.waited_s, "reason": departure.reason, "at": departure.at}


@app.post("/operator/free")
def operator_free() -> dict:
    handoff = QUEUE.operator_free()
    return {"handoff": handoff_dict(handoff) if handoff else None}


@app.post("/mode")
def change_mode(body: ModeChange) -> dict:
    set_mode(body.mode)
    return state()


@app.post("/reset")
def reset(body: Reset) -> dict:
    global QUEUE
    QUEUE = HoldQueue(max_normal_wait=MAX_NORMAL_WAIT_S)
    set_mode(body.mode or default_mode())
    return state()


@app.post("/simulate")
def simulate(body: SimulateRequest) -> dict:
    spec = SurgeSpec(
        duration_s=body.duration_s,
        arrivals_per_hour=body.arrivals_per_hour,
        operators=body.operators,
        tier_mix={
            Tier.IMMEDIATE: body.tier_mix.immediate,
            Tier.PRIORITY: body.tier_mix.priority,
            Tier.NORMAL: body.tier_mix.normal,
        },
        mean_service_s=body.mean_service_s,
        mean_patience_s=math.inf if body.mean_patience_s is None else body.mean_patience_s,
        decision_delay_s=body.decision_delay_s,
        miss_rate=body.miss_rate,
        false_alarm_rate=body.false_alarm_rate,
        seed=body.seed,
    )
    try:
        results = three_policy_comparison(spec, body.max_normal_wait_s)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "label": "simulated",
        "note": "Synthetic surge from the stated parameters; defaults informed by 211 LA's January 2025 "
        "after-action report. Not real calls.",
        "spec": body.model_dump(),
        "results": results,
    }


@app.get("/samples")
def samples() -> list[dict]:
    return SAMPLES
