"""The live hold queue behind the API: who is waiting, what they said, and who
the next free operator takes.

Callers leave only through `operator_free` (served) or `hang_up` (their own
choice); nothing here ends a call. One injected clock keeps tests exact.
"""

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from dualuse.extract import Classification, Extraction, handoff_summary
from dualuse.triage import Fifo, Tier, Tiered, Waiting, order

MODES = ("model", "rules", "fifo")  # fifo = degraded: no classification, today's order


@dataclass
class HeldCall:
    call_id: str
    arrival: float
    transcript: list[str] = field(default_factory=list)
    tier: Tier = Tier.UNKNOWN
    extraction: Extraction | None = None
    source: str = "none"


@dataclass(frozen=True)
class Handoff:
    call_id: str
    tier: Tier
    waited_s: float
    summary: str
    transcript: list[str]
    extraction: Extraction | None
    at: float


@dataclass(frozen=True)
class Departure:
    call_id: str
    waited_s: float
    reason: str
    at: float


def _silent_caller() -> Extraction:
    return Extraction(
        situation="(the caller has not said anything yet)",
        need="",
        location=None,
        life_threat_now=False,
        needs_person_soon=False,
        enough_information=False,
        evidence=[],
        missing=["what is happening", "what the caller needs", "where the caller is"],
        language="not detected",
    )


class HoldQueue:
    def __init__(self, max_normal_wait: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._calls: dict[str, HeldCall] = {}
        self._clock = clock
        self._policies = {"fifo": Fifo(), "tiered": Tiered(max_normal_wait)}
        self._mode = "model"
        self._counter = 0
        self.handoffs: list[Handoff] = []
        self.departed: list[Departure] = []

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {value!r}")
        self._mode = value

    @property
    def active_policy(self) -> str:
        return "fifo" if self._mode == "fifo" else "tiered"

    def now(self) -> float:
        return self._clock()

    def add(self, call_id: str | None = None) -> HeldCall:
        if call_id is None:
            self._counter += 1
            call_id = f"call-{self._counter}"
        if call_id in self._calls:
            raise ValueError(f"call {call_id} is already waiting")
        call = HeldCall(call_id=call_id, arrival=self._clock())
        self._calls[call_id] = call
        return call

    def say(self, call_id: str, text: str, classify: Callable[[str], Classification]) -> HeldCall:
        """Record an utterance and re-classify the whole transcript so far."""
        call = self._calls[call_id]
        call.transcript.append(text)
        result = classify("\n".join(call.transcript))
        call.tier, call.extraction, call.source = result.tier, result.extraction, result.source
        return call

    def order(self, policy_name: str) -> list[HeldCall]:
        now = self._clock()
        waiting = [Waiting(call.call_id, call.arrival, call.tier) for call in self._calls.values()]
        return [self._calls[item.call_id] for item in order(waiting, self._policies[policy_name], now)]

    def operator_free(self) -> Handoff | None:
        """An operator is free: the head of the queue under the active policy transfers now."""
        ordered = self.order(self.active_policy)
        if not ordered:
            return None
        head = ordered[0]
        del self._calls[head.call_id]
        now = self._clock()
        waited = now - head.arrival
        handoff = Handoff(
            call_id=head.call_id,
            tier=head.tier,
            waited_s=waited,
            summary=handoff_summary(head.extraction or _silent_caller(), head.tier, waited),
            transcript=list(head.transcript),
            extraction=head.extraction,
            at=now,
        )
        self.handoffs.append(handoff)
        return handoff

    def hang_up(self, call_id: str) -> Departure:
        """The caller chose to leave."""
        call = self._calls.pop(call_id)
        now = self._clock()
        departure = Departure(call_id, now - call.arrival, "caller_hung_up", now)
        self.departed.append(departure)
        return departure

    def clusters(self) -> list[dict]:
        """Waiting calls grouped by the location the caller stated, largest first."""
        groups: dict[str, list[HeldCall]] = defaultdict(list)
        for call in sorted(self._calls.values(), key=lambda call: call.arrival):
            if call.extraction is not None and call.extraction.location:
                groups[call.extraction.location.strip().lower()].append(call)
        clusters = [
            {
                "location": location,
                "count": len(calls),
                "call_ids": [call.call_id for call in calls],
                "tiers": dict(Counter(call.tier.value for call in calls)),
                "situations": sorted({call.extraction.situation for call in calls if call.extraction}),
            }
            for location, calls in groups.items()
        ]
        return sorted(clusters, key=lambda cluster: (-cluster["count"], cluster["location"]))
