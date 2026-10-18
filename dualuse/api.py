"""211 reception API. One process per SQLite database; no telephone calls are placed."""
import asyncio
import math
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from dualuse.config import ROOT
from dualuse import evaluation, extract
from dualuse.holdqueue import Conflict, HeldCall, HoldQueue
from dualuse.live_surge import arrival_offsets, plan_surge, start_surge
from dualuse.mapview import MapSync
from dualuse.shadow import ShadowScorer
from dualuse.profiles import PROFILES
from dualuse.samples import SAMPLES
from dualuse.surge import SurgeSpec, three_policy_comparison
from dualuse.triage import Tier

MAX_NORMAL_WAIT_S = 1800
INVARIANTS = [
    "The assistant never ends a call and never places an outbound call.",
    "Unknown information is kept with priority, never treated as a routine call.",
    "Immediate danger stays flagged until human review; every change has an audit event.",
    "An operator can reserve a call while the model is still replying.",
    "Only a confirmed handoff completes transfer; a failure preserves the original arrival time.",
    "After a confirmed takeover of a typed call, only the operator replies, as text in the caller's conversation.",
    "Reports are unverified; a shared location is not proof of a shared incident or dispatch.",
    "Normal callers gain scheduling priority after 30 minutes; this is not a maximum wait guarantee.",
    "Phone callers reach the desk only through the Retell voice bridge when it runs. "
    "Voice transfer to a person, dispatch and automatic callback are not connected.",
    "The incident map shows stated locations and official alerts as context; it never changes a tier.",
    "The map shows only the active line's service area; a call located outside it is flagged for transfer, not answered here.",
    "The CrisisFusion scorer is a shadow second opinion on the caller's words only; its score never changes a tier or the queue order.",
]
Mode = Literal["model", "rules", "fifo"]


def default_mode() -> Mode:
    return "model" if extract.model_available() else "rules"


QUEUE = HoldQueue(MAX_NORMAL_WAIT_S, db_path=Path(os.environ.get("DUALUSE_QUEUE_DB", str(ROOT / ".tmp/211-queue.sqlite3"))), mode=default_mode())
SURGE: dict = {}  # the running or last demo surge: thread, stop event and progress status
SURGE_LOCK = threading.Lock()
SHADOW = ShadowScorer(lambda: QUEUE.snapshot())  # late lookup: tests replace QUEUE
MAP = MapSync(lambda: QUEUE.snapshot(), shadow=lambda call_id: SHADOW.opinion(call_id))


@asynccontextmanager
async def lifespan(app):
    SHADOW.start()
    MAP.start()
    locator = asyncio.create_task(MAP.locate_forever())
    try:
        yield
    finally:
        locator.cancel()
        MAP.stop()
        SHADOW.stop()


app = FastAPI(title="211 reception and hold-queue assistant", lifespan=lifespan)
app.mount("/plugins/map", MAP.mounted)


@app.exception_handler(Conflict)
async def conflict_handler(request: Request, error: Conflict):
    return JSONResponse(status_code=409, content={"detail": str(error)})


class Location(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)


class NewCall(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    # A fixed set, so no client writes its own label into the operator's origin column.
    origin: Literal["live", "phone", "replay"] = "live"
    location: Location | None = None

    @model_validator(mode="after")
    def located_only_in_replay(self):
        # Coordinates come only from test data, which stays labeled as a replay.
        if self.location is not None and self.origin != "replay":
            raise ValueError("location is accepted only for replayed test calls (origin 'replay')")
        return self


class Utterance(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("utterance cannot be blank")
        return value.strip()


class ModeChange(BaseModel):
    mode: Mode


class Reset(BaseModel):
    mode: Mode | None = None


class SurgeRequest(BaseModel):
    count: int = Field(ge=1, le=60)
    source: Literal["mixed", "scripts", "messages"]
    pattern: Literal["even", "austin"]
    span_s: float = Field(ge=0, le=600)
    seed: int


class ProfileChange(BaseModel):
    profile: str

    @field_validator("profile")
    @classmethod
    def known(cls, value):
        if value not in PROFILES:
            raise ValueError(f"profile must be one of {sorted(PROFILES)}")
        return value


class Operator(BaseModel):
    operator_id: str = Field(default="operator-1", min_length=1, max_length=80, pattern=r"^[\w-]+$")


class OperatorMessage(Utterance):
    operator_id: str = Field(min_length=1, max_length=80, pattern=r"^[\w-]+$")


class Confirmation(BaseModel):
    success: bool


class CallbackReview(BaseModel):
    disposition: Literal["handled_by_operator", "no_callback_needed"]


class TierMix(BaseModel):
    immediate: float = Field(ge=0, le=1)
    priority: float = Field(ge=0, le=1)
    normal: float = Field(ge=0, le=1)


class SimulateRequest(BaseModel):
    duration_s: float = Field(gt=0, le=43200)
    arrivals_per_hour: float = Field(gt=0, le=1000)
    operators: int = Field(ge=1, le=100)
    tier_mix: TierMix
    mean_service_s: float = Field(gt=0)
    mean_patience_s: float | None = Field(gt=0, description="null means callers never hang up")
    decision_delay_s: float = Field(ge=0)
    miss_rate: float = Field(ge=0, le=1)
    false_alarm_rate: float = Field(ge=0, le=1)
    seed: int
    max_normal_wait_s: float = Field(gt=0)
    measured_text: Literal["english", "original"] = "english"  # which recorded-message rates to replay


def check_mode(mode: str):
    if mode == "model" and not extract.model_available():
        raise HTTPException(409, "ANTHROPIC_API_KEY is not set; model mode is unavailable")


def state() -> dict:
    return {**QUEUE.snapshot(), "model_available": extract.model_available(),
            "max_normal_wait_s": MAX_NORMAL_WAIT_S, "invariants": INVARIANTS, "map": dict(MAP.status),
            "scorer": {**SHADOW.status, "opinions": SHADOW.opinions},
            "profiles": [{"key": p.key, "name": p.name, "languages": list(p.languages)} for p in PROFILES.values()]}


def one_call(call: HeldCall) -> dict:
    return next(c for c in QUEUE.snapshot()["calls"] if c["call_id"] == call.call_id)


def require_call(call_id: str) -> HeldCall:
    try:
        return QUEUE.call(call_id)
    except KeyError:
        raise HTTPException(404, f"Unknown call {call_id}") from None


def process_turn(call_id: str, text: str) -> dict:
    require_call(call_id)
    try:
        return one_call(QUEUE.say(call_id, text))
    except Conflict:
        raise
    except ValueError as error:
        # Validation from a failed model is recorded by the desk and needs review.
        status = 502 if QUEUE.call(call_id).error else 422
        raise HTTPException(status, {"call_id": call_id, "message": "Interview failed; message saved for human review" if status == 502 else str(error)}) from error
    except Exception as error:
        raise HTTPException(502, {"call_id": call_id, "message": "Interview failed; message saved for human review", "type": type(error).__name__}) from error


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
def get_state() -> dict:
    return state()


@app.get("/calls/{call_id}")
def get_call(call_id: str) -> dict:
    return one_call(require_call(call_id))


@app.post("/calls", status_code=201)
def new_call(body: NewCall) -> dict:
    if body.text is not None and not body.text.strip():
        raise HTTPException(422, "utterance cannot be blank")
    call = QUEUE.add(origin=body.origin, location=body.location.model_dump() if body.location else None)
    return process_turn(call.call_id, body.text) if body.text else one_call(call)


@app.post("/calls/{call_id}/say")
def say(call_id: str, body: Utterance) -> dict:
    return process_turn(call_id, body.text)


@app.post("/calls/{call_id}/silence")
def silence(call_id: str) -> dict:
    require_call(call_id)
    return one_call(QUEUE.silence(call_id))


@app.post("/calls/{call_id}/hangup")
def hang_up(call_id: str) -> dict:
    require_call(call_id)
    return asdict(QUEUE.hang_up(call_id))


@app.post("/calls/{call_id}/disconnect")
def disconnect(call_id: str) -> dict:
    require_call(call_id)
    return asdict(QUEUE.hang_up(call_id, disconnected=True))


@app.post("/operator/free")
def operator_free(body: Operator = Operator()) -> dict:
    call = QUEUE.claim(body.operator_id)
    return {"handoff": one_call(call) if call else None}


@app.post("/handoffs/{transfer_id}/confirm")
def confirm(transfer_id: str, body: Confirmation) -> dict:
    return one_call(QUEUE.confirm(transfer_id, body.success))


@app.post("/calls/{call_id}/complete")
def complete(call_id: str) -> dict:
    require_call(call_id)
    return one_call(QUEUE.finish(call_id))


@app.post("/calls/{call_id}/operator-message")
def operator_message(call_id: str, body: OperatorMessage) -> dict:
    require_call(call_id)
    return one_call(QUEUE.operator_say(call_id, body.operator_id, body.text))


@app.post("/calls/{call_id}/callback-review")
def callback_review(call_id: str, body: CallbackReview) -> dict:
    require_call(call_id)
    return one_call(QUEUE.review_callback(call_id, body.disposition))


@app.post("/mode")
def change_mode(body: ModeChange) -> dict:
    check_mode(body.mode)
    QUEUE.mode = body.mode
    return state()


@app.post("/profile")
def change_profile(body: ProfileChange) -> dict:
    QUEUE.profile = body.profile
    return state()


def surge_status() -> dict:
    running = bool(SURGE.get("thread") and SURGE["thread"].is_alive())
    return {**SURGE.get("status", {}), "running": running}


@app.post("/demo/surge")
def demo_surge(body: SurgeRequest) -> dict:
    """Simulated arrivals into the live desk; each call carries its origin label."""
    with SURGE_LOCK:
        if surge_status()["running"]:
            raise HTTPException(409, "A demo surge is already running")
        try:
            callers = plan_surge(body.count, body.source, body.seed)
            offsets = arrival_offsets(len(callers), body.span_s, body.pattern, body.seed)
        except FileNotFoundError as error:
            raise HTTPException(409, f"Dataset missing: {error}") from error
        status, stop = {}, threading.Event()
        SURGE.update(status=status, stop=stop, thread=start_surge(QUEUE, callers, offsets, status=status, stop=stop))
        return surge_status()


@app.get("/demo/surge")
def get_surge() -> dict:
    return surge_status()


@app.post("/reset")
def reset(body: Reset) -> dict:
    mode = body.mode or default_mode()
    check_mode(mode)
    with SURGE_LOCK:
        if SURGE.get("stop"):
            SURGE["stop"].set()
            SURGE["thread"].join(timeout=5)  # its callers stop before the desk is cleared
        QUEUE.reset(mode)
        MAP.reset()
        SHADOW.reset()
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
    saved = saved_evaluation()
    measured = saved_rates(saved, body.measured_text) if saved else {}
    policies = {f"{method}_measured": evaluation.assigned_mix(rates) for method, rates in measured.items()}
    try:
        results = three_policy_comparison(spec, body.max_normal_wait_s, policies)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "label": "simulated",
        "note": "Synthetic surge from the stated parameters; defaults informed by 211 LA's January 2025 "
        "after-action report. Not real calls.",
        "spec": body.model_dump(),
        "results": results,
        "measured": {"text": body.measured_text, "label": saved["label"], "generated_at": saved["generated_at"],
                     "rates": measured} if measured else None,
    }


def saved_evaluation() -> dict | None:
    try:
        return evaluation.load_results()
    except ValueError as error:  # includes invalid JSON
        raise HTTPException(500, f"{evaluation.RESULTS} is malformed: {error}") from error


def saved_rates(saved: dict, text: str) -> dict:
    try:
        return evaluation.measured_rates(saved, text)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(500, f"{evaluation.RESULTS} lacks measured rates for {text}: {error!r}") from error


@app.get("/evaluation")
def get_evaluation() -> dict:
    """Recorded-message evaluation summaries (proxy labels, first message only), without per-message rows."""
    saved = saved_evaluation()
    if saved is None:
        return {"available": False}
    mixes = {text: {method: rates["assigned_mix"] for method, rates in saved_rates(saved, text).items()}
             for text in evaluation.TEXTS}
    return {"available": True, **{key: value for key, value in saved.items() if key != "rows"}, "assigned_mix": mixes}


@app.get("/samples")
def samples() -> list[dict]:
    return SAMPLES
