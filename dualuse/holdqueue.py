"""One persistent desk. Inference runs outside the queue lock; handoff is two-phase.

Run one API process per database. Only confirmed handoffs leave the waiting lifecycle.
"""
import copy
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from dualuse.extract import Classification, Extraction, handoff_summary
from dualuse.profiles import PROFILES, language_of, line, welcome
from dualuse.reception import ReceptionTurn, receive
from dualuse.storage import DeskStore
from dualuse.triage import Fifo, Tier, Tiered, Waiting, order

MODES = ("model", "rules", "fifo")


class Conflict(ValueError):
    pass


@dataclass
class HeldCall:
    call_id: str
    arrival: float
    transcript: list[str] = field(default_factory=list)
    tier: Tier = Tier.UNKNOWN
    extraction: Extraction | None = None
    source: str = "none"
    dialogue: list[dict] = field(default_factory=list)
    status: str = "waiting"
    version: int = 0
    processing: bool = False
    error: str = ""
    attention: str = ""
    silence_count: int = 0
    last_activity: float = 0
    callback_status: str = "none"
    transfer_id: str = ""
    operator_id: str = ""
    ended_at: float | None = None
    profile: str = "la-211"
    language: str = "en"  # primary language subtag; desk lines follow it
    distress: str = "unknown"


@dataclass(frozen=True)
class Handoff:
    call_id: str
    tier: Tier
    waited_s: float
    summary: str
    transcript: list[str]
    extraction: Extraction | None
    at: float
    dialogue: list[dict] = field(default_factory=list)
    operator_id: str = ""


@dataclass(frozen=True)
class Departure:
    call_id: str
    waited_s: float
    reason: str
    at: float


def _silent_caller() -> Extraction:
    return Extraction(situation="No usable information yet", need="", location=None,
                      life_threat_now=False, needs_person_soon=False, enough_information=False,
                      evidence=[], missing=["situation", "safety", "location", "need"], language="unknown")


def _encode(value):
    result = asdict(value)
    if result.get("extraction") is not None:
        result["extraction"] = value.extraction.model_dump()
    return result


class HoldQueue:
    def __init__(self, max_normal_wait: float, clock: Callable[[], float] = time.time,
                 db_path: Path | None = None, mode: str = "model", profile: str = "la-211") -> None:
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {tuple(PROFILES)}")
        self._lock = threading.RLock()
        self._clock = clock
        self._policies = {"fifo": Fifo(), "tiered": Tiered(max_normal_wait)}
        self._store = DeskStore(db_path) if db_path else None
        self._calls: dict[str, HeldCall] = {}
        self._mode = mode
        self._profile = profile
        self._counter = 0
        self.handoffs: list[Handoff] = []
        self.departed: list[Departure] = []
        self.events: list[dict] = []
        saved = self._store.load() if self._store else None
        if saved:
            self._mode, self._counter = saved["mode"], saved["counter"]
            self._profile = saved.get("profile", profile)  # desks saved before profiles existed
            for row in saved["calls"]:
                row["tier"] = Tier(row["tier"])
                row["extraction"] = Extraction.model_validate(row["extraction"]) if row["extraction"] else None
                call = HeldCall(**row)
                self._calls[call.call_id] = call
            for row in saved["handoffs"]:
                row["tier"] = Tier(row["tier"])
                row["extraction"] = Extraction.model_validate(row["extraction"]) if row["extraction"] else None
                self.handoffs.append(Handoff(**row))
            self.departed = [Departure(**row) for row in saved["departed"]]
            self.events = saved["events"]
            for call in self._calls.values():
                if call.status == "connecting":
                    call.version += 1
                    call.status = "waiting"
                    call.transfer_id = call.operator_id = ""
                    call.attention = "Service restarted during a transfer; operator review required"
                    self._log(call, "recovered", call.attention)
                if self._interrupt(call, "Service restarted during an interview"):
                    self._log(call, "recovered", call.attention)
            self._save()

    def _save(self):
        if self._store:
            self._store.save({"mode": self._mode, "profile": self._profile, "counter": self._counter,
                              "calls": [_encode(c) for c in self._calls.values()],
                              "handoffs": [_encode(h) for h in self.handoffs],
                              "departed": [asdict(d) for d in self.departed], "events": self.events})

    def _log(self, call: HeldCall, event: str, detail: str):
        self.events.append({"at": self.now(), "call_id": call.call_id, "event": event, "detail": detail})

    def _speak(self, call: HeldCall, text: str, topic: str = "status"):
        if text:
            call.dialogue.append({"speaker": "assistant", "text": text, "at": self.now(), "topic": topic})

    def _desk(self, call: HeldCall, key: str):
        """Say a code-owned line in the caller's language, with the call's profile numbers."""
        self._speak(call, line(call.profile, key, call.language))

    def _interrupt(self, call: HeldCall, reason: str) -> bool:
        """Cancel a running turn. Its caller message was never classified, so a person must read it."""
        if not call.processing:
            return False
        call.processing = False
        call.version += 1
        call.attention = f"{reason}; review the latest caller message"
        if call.tier == Tier.NORMAL:
            call.tier = Tier.UNKNOWN
            self._log(call, "tier_changed", f"normal -> unknown: {reason}")
        return True

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if value not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        with self._lock:
            if value != self._mode:
                for call in self._calls.values():
                    self._interrupt(call, "Mode changed during an interview")
            self._mode = value
            self._save()

    @property
    def profile(self) -> str:
        return self._profile

    @profile.setter
    def profile(self, value: str):
        """Applies to calls that join from now on; waiting calls keep the line they called."""
        if value not in PROFILES:
            raise ValueError(f"profile must be one of {tuple(PROFILES)}")
        with self._lock:
            self._profile = value
            self._save()

    @property
    def active_policy(self) -> str:
        return "fifo" if self._mode == "fifo" else "tiered"

    def now(self) -> float:
        return self._clock()

    def reset(self, mode: str):
        if mode not in MODES:
            raise ValueError("invalid mode")
        with self._lock:
            self._calls.clear()
            self.handoffs.clear()
            self.departed.clear()
            self.events.clear()
            # IDs are never reused, including after reset and process restart.
            self._mode = mode
            self._save()

    def call(self, call_id: str) -> HeldCall:
        return self._calls[call_id]

    def add(self, call_id: str | None = None) -> HeldCall:
        with self._lock:
            if call_id is None:
                self._counter += 1
                call_id = f"call-{self._counter}"
            if call_id in self._calls:
                raise ValueError(f"call {call_id} already exists")
            call = HeldCall(call_id, self.now(), last_activity=self.now(), profile=self._profile,
                            language=PROFILES[self._profile].languages[0])
            self._calls[call_id] = call
            ahead = [c.call_id for c in self.order(self.active_policy)].index(call_id)
            self._speak(call, welcome(call.profile, call.language, ahead, reorders=self.active_policy != "fifo"), "welcome")
            self._log(call, "joined", "Entered queue; no information yet")
            self._save()
            return call

    def order(self, policy_name: str) -> list[HeldCall]:
        with self._lock:
            waiting = [Waiting(c.call_id, c.arrival, c.tier) for c in self._calls.values() if c.status == "waiting"]
            return [self._calls[w.call_id] for w in order(waiting, self._policies[policy_name], self.now())]

    def say(self, call_id: str, text: str, classify: Callable[[str], Classification] | None = None,
            responder=receive) -> HeldCall:
        text = text.strip()
        if not text or len(text) > 4000:
            raise ValueError("utterance must contain 1 to 4000 characters")
        with self._lock:
            call = self._calls[call_id]
            if call.status != "waiting" or call.processing:
                raise Conflict("Call is not waiting or an interview turn is already running")
            if sum(len(t) for t in call.transcript) + len(text) > 32000:
                raise ValueError("Conversation limit reached; ask an operator to take this call")
            call.transcript.append(text)
            call.dialogue.append({"speaker": "caller", "text": text, "at": self.now()})
            call.last_activity, call.silence_count = self.now(), 0
            call.version += 1
            version, mode = call.version, self.mode
            call.processing = mode != "fifo"
            self._log(call, "caller_message", "New information received")
            if mode == "fifo":
                call.source = "none"
                self._desk(call, "fifo")
                self._save()
                return call
            dialogue = copy.deepcopy(call.dialogue)
            self._save()
        try:
            turn = ReceptionTurn(classify("\n".join(call.transcript)), "wait", "") if classify else responder(dialogue, mode)
        except Exception as error:
            # The failure remains visible; a failed model never becomes a successful rules prediction.
            with self._lock:
                if self._calls.get(call_id) is not call or call.version != version or call.status != "waiting":
                    raise Conflict("Call state changed while the interview ran; late failure discarded") from error
                if self._calls.get(call_id) is call and call.version == version and call.status == "waiting":
                    call.processing = False
                    call.error = f"Interview failed ({type(error).__name__}); operator review required"
                    call.attention = call.error
                    if call.tier != Tier.IMMEDIATE:
                        call.tier = Tier.UNKNOWN
                    self._desk(call, "failed_turn")
                    self._log(call, "interview_error", call.error)
                    self._save()
            raise
        with self._lock:
            if self._calls.get(call_id) is not call or call.version != version or call.status != "waiting":
                raise Conflict("Call state changed while the interview ran; late response discarded")
            old_tier = call.tier
            old_report = (call.extraction.incident_kind, call.extraction.location) if call.extraction else None
            result = turn.classification
            call.extraction, call.source = result.extraction, result.source
            if old_tier == Tier.IMMEDIATE and result.tier != Tier.IMMEDIATE:
                previous = next((e["detail"] for e in reversed(self.events)
                                 if e["call_id"] == call_id and e["event"] == "tier_changed" and "-> immediate:" in e["detail"]), "")
                call.attention = "Earlier immediate danger remains flagged for human review: " + previous
            call.tier = Tier.IMMEDIATE if old_tier == Tier.IMMEDIATE else result.tier
            call.processing, call.error = False, ""
            if call.attention.startswith(("No response", "Interview failed")):
                call.attention = ""
            if turn.review:
                call.attention = f"{call.attention}; {turn.review}" if call.attention else turn.review
                self._log(call, "review_flag", turn.review)
            if turn.language:
                call.language = language_of(turn.language)
            if turn.distress:
                call.distress = turn.distress
            if old_tier != call.tier:
                self._log(call, "tier_changed", f"{old_tier.value} -> {call.tier.value}: " + "; ".join(result.extraction.evidence))
            x = call.extraction
            if call.tier == Tier.IMMEDIATE and old_tier != Tier.IMMEDIATE:
                self._desk(call, "emergency")
            if x.incident_kind != "none" and x.location and old_report != (x.incident_kind, x.location):
                self._desk(call, "incident")
            if turn.question:
                self._speak(call, turn.question, turn.topic)
            else:
                self._speak(call, line(call.profile, "saved_wait", call.language), "wait")
            self._save()
            return call

    def silence(self, call_id: str) -> HeldCall:
        with self._lock:
            call = self._calls[call_id]
            if call.status != "waiting" or call.processing:
                raise Conflict("Silence event requires a waiting call with no turn running")
            call.silence_count += 1
            call.last_activity = self.now()
            if call.silence_count == 1:
                self._desk(call, "silence_1")
            else:
                if call.tier != Tier.IMMEDIATE:
                    call.tier = Tier.UNKNOWN
                call.attention = "No response after a check-in; human review required"
                self._desk(call, "silence_2")
            self._log(call, "silence", f"Check-in {call.silence_count}")
            self._save()
            return call

    def claim(self, operator_id: str) -> HeldCall | None:
        with self._lock:
            if any(c.operator_id == operator_id and c.status in ("connecting", "handed_off") for c in self._calls.values()):
                raise Conflict("Operator already has a reserved or active call")
            ordered = self.order(self.active_policy)
            if not ordered:
                return None
            call = ordered[0]
            self._interrupt(call, "An operator reserved the call during an interview")
            call.status, call.operator_id = "connecting", operator_id
            call.transfer_id = uuid.uuid4().hex
            call.version += 1
            self._desk(call, "reserved")
            self._log(call, "handoff_reserved", operator_id)
            self._save()
            return call

    def confirm(self, transfer_id: str, success: bool) -> HeldCall:
        with self._lock:
            call = next((c for c in self._calls.values() if c.transfer_id == transfer_id), None)
            if call is None or call.status != "connecting":
                raise Conflict("Transfer is no longer pending")
            if success:
                call.status, call.ended_at = "handed_off", self.now()
                self._desk(call, "confirmed")
                self.handoffs.append(Handoff(call.call_id, call.tier, self.now() - call.arrival,
                                            self.summary(call), list(call.transcript), call.extraction, self.now(),
                                            copy.deepcopy(call.dialogue), call.operator_id))
                self._log(call, "handoff_confirmed", call.operator_id)
            else:
                call.status = "waiting"
                call.transfer_id = call.operator_id = ""
                self._desk(call, "failed")
                self._log(call, "handoff_failed", "Returned to queue without changing arrival")
            self._save()
            return call

    def finish(self, call_id: str) -> HeldCall:
        with self._lock:
            call = self._calls[call_id]
            if call.status != "handed_off":
                raise Conflict("Only an operator-held call can be completed")
            call.status = "completed"
            self._log(call, "operator_completed", call.operator_id)
            self._save()
            return call

    def operator_free(self) -> Handoff | None:
        """In-process simulation helper; HTTP clients must reserve then confirm."""
        call = self.claim(f"simulation-{uuid.uuid4().hex}")
        if call is None:
            return None
        self.confirm(call.transfer_id, True)
        return self.handoffs[-1]

    def hang_up(self, call_id: str, disconnected: bool = False) -> Departure:
        with self._lock:
            call = self._calls[call_id]
            if call.status not in ("waiting", "connecting"):
                raise Conflict("Call is no longer in the waiting or connecting state")
            self._interrupt(call, "The caller left during an interview")
            call.status = "disconnected" if disconnected else "hung_up"
            call.ended_at = self.now()
            call.version += 1
            call.transfer_id = call.operator_id = ""
            if disconnected or not call.transcript or call.tier in (Tier.IMMEDIATE, Tier.PRIORITY, Tier.UNKNOWN):
                call.callback_status = "pending_review"
            reason = "connection_lost" if disconnected else "caller_hung_up"
            departure = Departure(call_id, self.now() - call.arrival, reason, self.now())
            self.departed.append(departure)
            self._log(call, reason, "Saved; callback review task created" if call.callback_status != "none" else "Saved")
            self._save()
            return departure

    def review_callback(self, call_id: str, disposition: str) -> HeldCall:
        with self._lock:
            call = self._calls[call_id]
            if call.callback_status != "pending_review":
                raise Conflict("No pending callback task")
            if disposition not in ("handled_by_operator", "no_callback_needed"):
                raise ValueError("Invalid callback disposition")
            call.callback_status = disposition
            self._log(call, "callback_reviewed", disposition + "; no automatic call was placed")
            self._save()
            return call

    def summary(self, call: HeldCall) -> str:
        end = call.ended_at if call.ended_at is not None else self.now()
        return handoff_summary(call.extraction or _silent_caller(), call.tier, end - call.arrival) + f"\nReview: {call.attention or 'none flagged'}"

    def clusters(self) -> list[dict]:
        with self._lock:
            groups = defaultdict(list)
            for call in sorted(self._calls.values(), key=lambda c: c.arrival):
                if call.extraction and call.extraction.location and call.extraction.incident_kind != "none":
                    place = re.sub(r"\s+", " ", call.extraction.location.strip().lower()).rstrip(".,")
                    groups[(call.extraction.incident_kind, place)].append(call)
            return [{"kind": kind, "location": place, "count": len(calls),
                     "call_ids": [c.call_id for c in calls], "tiers": dict(Counter(c.tier.value for c in calls)),
                     "situations": [c.extraction.situation for c in calls],
                     "verification": "Unverified reports; matching kind and stated location only"}
                    for (kind, place), calls in sorted(groups.items(), key=lambda item: -len(item[1]))]

    def snapshot(self) -> dict:
        with self._lock:
            fifo = {c.call_id: i for i, c in enumerate(self.order("fifo"))}
            tiered = {c.call_id: i for i, c in enumerate(self.order("tiered"))}
            rows = []
            for call in self._calls.values():
                row = _encode(call)
                row.update(waited_s=(call.ended_at if call.ended_at is not None else self.now()) - call.arrival,
                           fifo_position=fifo.get(call.call_id), tiered_position=tiered.get(call.call_id),
                           summary=self.summary(call))
                rows.append(row)
            by_id = {c["call_id"]: c for c in rows}
            return copy.deepcopy({"mode": self.mode, "profile": self._profile, "active_policy": self.active_policy,
                "waiting": [by_id[c.call_id] for c in self.order(self.active_policy)], "calls": rows,
                "clusters": self.clusters(), "handoffs": [_encode(h) for h in self.handoffs[-20:]],
                "departed": [asdict(d) for d in self.departed[-20:]], "events": self.events[-100:],
                "persistent": self._store is not None})
