"""Discrete-event simulation of a hold queue served by a fixed number of operators.

The same calls run under several policies so the comparison isolates the
policy. A call's tier is UNKNOWN until `arrival + decision_delay`, which models
the interview and extraction time; before that the policy cannot use it.
Callers leave only by being served or by running out of patience. Design:
docs/architecture.md, section "Evaluation".
"""

import heapq
import math
from dataclasses import dataclass, replace
from statistics import mean

from dualuse.triage import Policy, Tier, Waiting, pick_next

# Event kinds in processing order at equal times: an operator frees up before a
# newly arrived or newly classified call is considered, and a caller who is
# served at the very moment their patience ends counts as served.
FREE, DECISION, ARRIVAL, ABANDON = 0, 1, 2, 3


@dataclass(frozen=True)
class Call:
    """One call as the simulation knows it in advance. Times are seconds."""

    call_id: str
    arrival: float
    service_time: float
    patience: float  # math.inf for a caller who never hangs up
    true_tier: Tier  # the evaluation label
    assigned_tier: Tier  # what the policy learns after decision_delay
    decision_delay: float


@dataclass(frozen=True)
class Outcome:
    call_id: str
    true_tier: Tier
    assigned_tier: Tier
    arrival: float
    started: float | None  # service start, None if the caller abandoned
    abandoned_at: float | None

    @property
    def wait(self) -> float | None:
        return None if self.started is None else self.started - self.arrival


def simulate(calls: list[Call], n_operators: int, policy: Policy) -> list[Outcome]:
    """Run the queue and return one outcome per call, in the input order."""
    by_id = {call.call_id: call for call in calls}
    events: list[tuple[float, int, int, str]] = []
    seq = 0

    def push(time: float, kind: int, call_id: str) -> None:
        nonlocal seq
        heapq.heappush(events, (time, kind, seq, call_id))
        seq += 1

    for call in calls:
        push(call.arrival, ARRIVAL, call.call_id)

    waiting: dict[str, Waiting] = {}
    outcomes: dict[str, Outcome] = {}
    free = n_operators

    while events:
        now, kind, _, call_id = heapq.heappop(events)
        call = by_id[call_id]
        if kind == ARRIVAL:
            known = call.decision_delay <= 0
            waiting[call_id] = Waiting(call_id, now, call.assigned_tier if known else Tier.UNKNOWN)
            if not known:
                push(now + call.decision_delay, DECISION, call_id)
            if math.isfinite(call.patience):
                push(now + call.patience, ABANDON, call_id)
        elif kind == DECISION:
            if call_id in waiting:
                waiting[call_id] = replace(waiting[call_id], tier=call.assigned_tier)
        elif kind == ABANDON:
            if call_id in waiting:
                del waiting[call_id]
                outcomes[call_id] = Outcome(call_id, call.true_tier, call.assigned_tier, call.arrival, None, now)
        elif kind == FREE:
            free += 1

        while free > 0 and waiting:
            head = pick_next(list(waiting.values()), policy, now)
            assert head is not None
            del waiting[head.call_id]
            free -= 1
            served = by_id[head.call_id]
            outcomes[head.call_id] = Outcome(
                head.call_id, served.true_tier, served.assigned_tier, served.arrival, now, None
            )
            push(now + served.service_time, FREE, head.call_id)

    return [outcomes[call.call_id] for call in calls]


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[index]


def summarize(outcomes: list[Outcome]) -> dict:
    """Per-true-tier waits and abandonment, assigned-tier shares, and misses
    (a true IMMEDIATE or PRIORITY call that the policy ranked NORMAL)."""
    by_true_tier = {}
    for tier in Tier:
        group = [outcome for outcome in outcomes if outcome.true_tier is tier]
        waits = [outcome.wait for outcome in group if outcome.wait is not None]
        by_true_tier[tier.value] = {
            "calls": len(group),
            "served": len(waits),
            "abandoned": len(group) - len(waits),
            "wait_mean": mean(waits) if waits else None,
            "wait_p50": percentile(waits, 50) if waits else None,
            "wait_p95": percentile(waits, 95) if waits else None,
        }
    total = len(outcomes)
    assigned_share = {
        tier.value: (sum(1 for outcome in outcomes if outcome.assigned_tier is tier) / total if total else 0.0)
        for tier in Tier
    }
    misses = sum(
        1
        for outcome in outcomes
        if outcome.true_tier in (Tier.IMMEDIATE, Tier.PRIORITY) and outcome.assigned_tier is Tier.NORMAL
    )
    served = sum(1 for outcome in outcomes if outcome.started is not None)
    return {
        "by_true_tier": by_true_tier,
        "assigned_share": assigned_share,
        "misses": misses,
        "served": served,
        "abandoned": total - served,
    }


def compare(calls: list[Call], n_operators: int, policies: list[Policy]) -> dict[str, dict]:
    """Summaries of the same calls under each policy, keyed by policy name."""
    return {policy.name: summarize(simulate(calls, n_operators, policy)) for policy in policies}
