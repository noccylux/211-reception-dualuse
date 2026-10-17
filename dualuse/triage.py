"""Tiers and hold-queue ordering policies.

Policies are pure functions of the waiting calls and the clock, so the
simulation and the live queue share them. Design: docs/architecture.md,
sections "Tiers" and "What is never automated".
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Tier(str, Enum):
    IMMEDIATE = "immediate"
    PRIORITY = "priority"
    UNKNOWN = "unknown"
    NORMAL = "normal"


# UNKNOWN shares PRIORITY's rank: missing information is never ordered as normal.
RANK = {Tier.IMMEDIATE: 0, Tier.PRIORITY: 1, Tier.UNKNOWN: 1, Tier.NORMAL: 2}


@dataclass(frozen=True)
class Waiting:
    """A call in the hold queue as a policy sees it. Times are seconds on one clock."""

    call_id: str
    arrival: float
    tier: Tier


class Policy(Protocol):
    name: str

    def key(self, call: Waiting, now: float) -> tuple[float, ...]: ...


class Fifo:
    """Today's behavior: first come, first served."""

    name = "fifo"

    def key(self, call: Waiting, now: float) -> tuple[float, ...]:
        return (call.arrival,)


class Tiered:
    """Tier rank first, then arrival. A NORMAL caller counts as PRIORITY once it has
    waited `max_normal_wait` seconds (the aging guard), which bounds the delay that
    reordering can impose on anyone."""

    name = "tiered"

    def __init__(self, max_normal_wait: float) -> None:
        self.max_normal_wait = max_normal_wait

    def key(self, call: Waiting, now: float) -> tuple[float, ...]:
        rank = RANK[call.tier]
        if call.tier is Tier.NORMAL and now - call.arrival >= self.max_normal_wait:
            rank = RANK[Tier.PRIORITY]
        return (rank, call.arrival)


def order(waiting: list[Waiting], policy: Policy, now: float) -> list[Waiting]:
    """The queue as the policy would serve it at time `now`, head first."""
    return sorted(waiting, key=lambda call: policy.key(call, now))


def pick_next(waiting: list[Waiting], policy: Policy, now: float) -> Waiting | None:
    """The call an operator who frees up at `now` takes, or None if nobody waits."""
    if not waiting:
        return None
    return min(waiting, key=lambda call: policy.key(call, now))
