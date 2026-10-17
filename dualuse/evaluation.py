"""Metrics for the recorded-message evaluation, and the measured tier shares it gives the simulator.

The messages are recorded SMS from the 2010 Haiti earthquake and Pakistan floods and Hurricane Sandy
message-board posts (Munro test split, direct messages; CC BY 4.0, Robert Munro 2012), judged on the
first message only against proxy labels: request = 1 means the message needs a person. They are not
211 calls, so these rates are not 211 accuracy. Method and results: docs/evaluation.md; the run
itself: scripts/evaluate_messages.py.
"""

import json
import math
from pathlib import Path

from dualuse.config import ROOT
from dualuse.triage import RANK, Tier

RESULTS = ROOT / "data/processed/eval_messages.json"
# The proxy class whose measured tiers stand in for each true tier of a simulated caller.
PROXY_FOR = {Tier.IMMEDIATE: "subset", Tier.PRIORITY: "needs", Tier.NORMAL: "routine"}
TEXTS = ("english", "original")  # the published English translation, and the message as sent
Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got {successes} of {n}")
    p = successes / n
    scale = 1 + z * z / n
    center = (p + z * z / (2 * n)) / scale
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / scale
    return max(0.0, center - half), min(1.0, center + half)


def proportion(successes: int, n: int) -> dict:
    low, high = wilson(successes, n)
    return {"k": successes, "n": n, "rate": successes / n, "low": low, "high": high}


def ahead_of_routine(tier: str) -> bool:
    """IMMEDIATE, PRIORITY and UNKNOWN all rank ahead of NORMAL; UNKNOWN shares PRIORITY's rank."""
    return RANK[Tier(tier)] < RANK[Tier.NORMAL]


def _tiers(rows: list[dict]) -> dict[str, int]:
    return {tier.value: sum(r["tier"] == tier.value for r in rows) for tier in (Tier.IMMEDIATE, Tier.PRIORITY, Tier.UNKNOWN, Tier.NORMAL)}


def _classes(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Class rates come from the stratified sample; the rescue/medical/death subset is evaluated in full."""
    needs = [r for r in rows if r["sampled"] and r["label"] == "needs"]
    routine = [r for r in rows if r["sampled"] and r["label"] == "routine"]
    if not needs or not routine:
        raise ValueError("the sample needs both needs-a-person and routine messages")
    return needs, routine, [r for r in rows if r["subset"]]


def summarize(rows: list[dict]) -> dict:
    """Rates for one method on one text column. Each row: label ('needs' or 'routine'), sampled,
    subset, the tier the desk stored, its review notes and any failure."""
    needs, routine, subset = _classes(rows)
    return {
        "miss": proportion(sum(r["tier"] == Tier.NORMAL.value for r in needs), len(needs)),
        "false_alarm": proportion(sum(r["tier"] in (Tier.IMMEDIATE.value, Tier.PRIORITY.value) for r in routine), len(routine)),
        "routine_ahead": proportion(sum(ahead_of_routine(r["tier"]) for r in routine), len(routine)),
        "subset_miss": proportion(sum(r["tier"] == Tier.NORMAL.value for r in subset), len(subset)) if subset else None,
        "subset_immediate": proportion(sum(r["tier"] == Tier.IMMEDIATE.value for r in subset), len(subset)) if subset else None,
        "tiers": {"needs": _tiers(needs), "routine": _tiers(routine), "subset": _tiers(subset)},
        "review": {"needs": proportion(sum(bool(r["review"]) for r in needs), len(needs)),
                   "routine": proportion(sum(bool(r["review"]) for r in routine), len(routine))},
        "failed": sum(bool(r["error"]) for r in rows),
    }


def fifo_summary(rows: list[dict]) -> dict:
    """FIFO serves in arrival order, so nobody is ranked ahead: every needs-a-person message waits
    as a routine one would. These rates hold by construction; nothing is measured."""
    needs, routine, subset = _classes(rows)

    def exact(k: int, n: int) -> dict:
        return {"k": k, "n": n, "rate": k / n}

    return {
        "by_construction": True,
        "miss": exact(len(needs), len(needs)),
        "false_alarm": exact(0, len(routine)),
        "routine_ahead": exact(0, len(routine)),
        "subset_miss": exact(len(subset), len(subset)) if subset else None,
    }


def load_results(path: Path | None = None) -> dict | None:
    """The saved evaluation, or None before scripts/evaluate_messages.py has run."""
    path = path or RESULTS
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def assigned_mix(summary: dict) -> dict[Tier, dict[Tier, float]]:
    """P(assigned tier | true tier) for the simulator: a true IMMEDIATE caller gets the tiers measured on
    the rescue, medical or death subset, PRIORITY those of the needs-a-person sample and NORMAL those
    of the routine sample. Unlike a miss rate alone, this keeps UNKNOWN (ranked with PRIORITY) and an
    IMMEDIATE caller who was not ranked IMMEDIATE."""
    mix = {}
    for true_tier, group in PROXY_FOR.items():
        counts = summary["tiers"][group]
        n = sum(counts.values())
        if n == 0:
            raise ValueError(f"no {group} messages were evaluated, so {true_tier.value} callers cannot be replayed")
        mix[true_tier] = {Tier(tier): count / n for tier, count in counts.items()}
    return mix


def measured_rates(results: dict, text: str) -> dict[str, dict]:
    """Per method ('rules', 'model'), the summary measured on one text column and, with plain keys for
    display, the assigned-tier mix the simulator replays."""
    if text not in TEXTS:
        raise ValueError(f"text must be one of {TEXTS}, got {text!r}")
    rates = {}
    for method in ("rules", "model"):
        summary = results["summaries"][method][text]
        mix = assigned_mix(summary)
        rates[method] = {**summary, "assigned_mix": {t.value: {a.value: p for a, p in row.items()} for t, row in mix.items()}}
    return rates
