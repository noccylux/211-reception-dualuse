"""Labeled synthetic surge scenarios for the simulation.

Everything here is simulated. The default parameters are informed by 211 LA's
January 2025 wildfires after-action report (Appendix D: on 2025-01-08, 7,815
contacts offered, 60.66% abandoned, 1 h 23 min average wait, 6 min 16 s
average handle time), but the arrival process, the tier mix, caller patience
and the classifier error rates are assumptions. They are stated in the spec
and labeled as simulated wherever they are shown. The one exception is an
`assigned_mix` measured on recorded messages (dualuse.evaluation), labeled as such.
"""

import math
import random
from dataclasses import dataclass, replace

from dualuse.simulation import Call, simulate, summarize
from dualuse.triage import Fifo, Tier, Tiered

TRUE_TIERS = (Tier.IMMEDIATE, Tier.PRIORITY, Tier.NORMAL)
ASSIGNABLE = (Tier.IMMEDIATE, Tier.PRIORITY, Tier.UNKNOWN, Tier.NORMAL)


@dataclass(frozen=True)
class SurgeSpec:
    duration_s: float  # arrivals keep coming for this long
    arrivals_per_hour: float  # Poisson arrival rate
    operators: int
    tier_mix: dict[Tier, float]  # probabilities of the true tiers, summing to 1
    mean_service_s: float  # operator handle time, exponential
    mean_patience_s: float  # time before a waiting caller hangs up, exponential; inf = never
    decision_delay_s: float  # interview plus extraction time before the tier is known
    miss_rate: float  # P(a true IMMEDIATE or PRIORITY call is assigned NORMAL)
    false_alarm_rate: float  # P(a true NORMAL call is assigned PRIORITY)
    seed: int
    # Measured P(assigned tier | true tier), UNKNOWN included; when set it replaces the two rates above.
    assigned_mix: dict[Tier, dict[Tier, float]] | None = None


DEFAULT_SPEC = SurgeSpec(
    duration_s=2 * 3600,
    arrivals_per_hour=120,
    operators=8,
    tier_mix={Tier.IMMEDIATE: 0.03, Tier.PRIORITY: 0.22, Tier.NORMAL: 0.75},
    mean_service_s=376,  # 211 LA, 2025-01-08: 6 min 16 s
    mean_patience_s=1200,
    decision_delay_s=45,
    miss_rate=0.05,
    false_alarm_rate=0.10,
    seed=7,
)

# Assumed accuracy of a keyword-only baseline, used as the middle policy in the
# comparison. An assumption until a keyword classifier is measured on real text.
RULES_MISS_RATE = 0.25
RULES_FALSE_ALARM_RATE = 0.30


def generate(spec: SurgeSpec) -> list[Call]:
    """Calls for the scenario. The same seed gives the same arrivals, service times,
    patience and true tiers; the error rates only change the assigned tiers."""
    if set(spec.tier_mix) - set(TRUE_TIERS) or any(p < 0 for p in spec.tier_mix.values()):
        raise ValueError("tier_mix must give non-negative probabilities for IMMEDIATE, PRIORITY and NORMAL only")
    if not math.isclose(sum(spec.tier_mix.values()), 1.0, abs_tol=1e-9):
        raise ValueError("tier_mix probabilities must sum to 1")
    if spec.assigned_mix is not None:
        for true_tier in TRUE_TIERS:
            row = spec.assigned_mix.get(true_tier)
            if (row is None or set(row) - set(ASSIGNABLE) or any(p < 0 for p in row.values())
                    or not math.isclose(sum(row.values()), 1.0, abs_tol=1e-9)):
                raise ValueError(f"assigned_mix must give each true tier a distribution over the four tiers; "
                                 f"{true_tier.value} does not")
    tiers = list(spec.tier_mix)
    weights = [spec.tier_mix[tier] for tier in tiers]
    rng = random.Random(spec.seed)
    errors = random.Random(spec.seed ^ 0x5EED)
    calls: list[Call] = []
    now = 0.0
    while True:
        now += rng.expovariate(spec.arrivals_per_hour / 3600)
        if now > spec.duration_s:
            return calls
        true_tier = rng.choices(tiers, weights)[0]
        service_time = rng.expovariate(1 / spec.mean_service_s)
        patience = math.inf if math.isinf(spec.mean_patience_s) else rng.expovariate(1 / spec.mean_patience_s)
        draw = errors.random()
        if spec.assigned_mix is not None:
            assigned_tier = _drawn(spec.assigned_mix[true_tier], draw)
        elif true_tier is not Tier.NORMAL and draw < spec.miss_rate:
            assigned_tier = Tier.NORMAL
        elif true_tier is Tier.NORMAL and draw < spec.false_alarm_rate:
            assigned_tier = Tier.PRIORITY
        else:
            assigned_tier = true_tier
        calls.append(
            Call(
                call_id=f"call-{len(calls) + 1:04d}",
                arrival=now,
                service_time=service_time,
                patience=patience,
                true_tier=true_tier,
                assigned_tier=assigned_tier,
                decision_delay=spec.decision_delay_s,
            )
        )


def _drawn(row: dict[Tier, float], draw: float) -> Tier:
    """The assigned tier for a uniform draw in [0, 1), walking the row in rank order."""
    total = 0.0
    for tier in ASSIGNABLE:
        total += row.get(tier, 0.0)
        if draw < total:
            return tier
    return next(tier for tier in reversed(ASSIGNABLE) if row.get(tier, 0.0) > 0)  # float rounding at the top


def three_policy_comparison(spec: SurgeSpec, max_normal_wait_s: float,
                            measured: dict[str, dict[Tier, dict[Tier, float]]] | None = None) -> dict[str, dict]:
    """FIFO, keyword rules (assumed accuracy) and the model (the spec's accuracy) on
    the same arrivals, operators, service times and patience. Each `measured` entry,
    name -> P(assigned tier | true tier) from dualuse.evaluation.assigned_mix, adds a
    tiered policy on the same calls; only the assigned tiers differ."""
    tiered = Tiered(max_normal_wait=max_normal_wait_s)
    rules_spec = replace(spec, miss_rate=RULES_MISS_RATE, false_alarm_rate=RULES_FALSE_ALARM_RATE)
    results = {
        "fifo": summarize(simulate(generate(spec), spec.operators, Fifo())),
        "rules": summarize(simulate(generate(rules_spec), spec.operators, tiered)),
        "model": summarize(simulate(generate(spec), spec.operators, tiered)),
    }
    for name, mix in (measured or {}).items():
        if name in results:
            raise ValueError(f"measured policy {name!r} would replace a built-in policy")
        results[name] = summarize(simulate(generate(replace(spec, assigned_mix=mix)), spec.operators, tiered))
    return results
