import math
from dataclasses import replace

import pytest

from dualuse.surge import DEFAULT_SPEC, SurgeSpec, generate, three_policy_comparison
from dualuse.triage import Tier

SPEC = SurgeSpec(
    duration_s=10 * 3600,
    arrivals_per_hour=10,
    operators=3,
    tier_mix={Tier.IMMEDIATE: 0.1, Tier.PRIORITY: 0.3, Tier.NORMAL: 0.6},
    mean_service_s=300,
    mean_patience_s=600,
    decision_delay_s=45,
    miss_rate=0.0,
    false_alarm_rate=0.0,
    seed=1,
)


def test_same_seed_gives_the_same_calls_and_another_seed_differs():
    assert generate(SPEC) == generate(SPEC)
    assert generate(SPEC) != generate(replace(SPEC, seed=2))


def test_arrivals_are_sorted_and_inside_the_duration():
    arrivals = [call.arrival for call in generate(SPEC)]
    assert arrivals == sorted(arrivals)
    assert arrivals[0] >= 0 and arrivals[-1] <= SPEC.duration_s


def test_call_count_follows_the_arrival_rate():
    assert 60 <= len(generate(SPEC)) <= 140  # mean 100, Poisson


def test_service_patience_and_decision_delay_come_from_the_spec():
    calls = generate(SPEC)
    assert all(call.service_time > 0 for call in calls)
    assert all(call.patience > 0 for call in calls)
    assert all(call.decision_delay == 45 for call in calls)
    assert all(math.isinf(call.patience) for call in generate(replace(SPEC, mean_patience_s=math.inf)))


def test_without_errors_the_assigned_tier_equals_the_true_tier():
    assert all(call.assigned_tier is call.true_tier for call in generate(SPEC))


def test_miss_rate_sends_urgent_calls_to_normal_and_false_alarms_lift_normal_calls():
    only_urgent = replace(SPEC, tier_mix={Tier.IMMEDIATE: 0.5, Tier.PRIORITY: 0.5, Tier.NORMAL: 0.0}, miss_rate=1.0)
    assert all(call.assigned_tier is Tier.NORMAL for call in generate(only_urgent))
    only_normal = replace(SPEC, tier_mix={Tier.IMMEDIATE: 0.0, Tier.PRIORITY: 0.0, Tier.NORMAL: 1.0}, false_alarm_rate=1.0)
    assert all(call.assigned_tier is Tier.PRIORITY for call in generate(only_normal))


def test_true_tiers_roughly_follow_the_mix():
    calls = generate(replace(SPEC, arrivals_per_hour=100))
    share = sum(1 for call in calls if call.true_tier is Tier.NORMAL) / len(calls)
    assert 0.5 < share < 0.7


def test_tier_mix_must_sum_to_one_and_cover_no_unknown():
    with pytest.raises(ValueError, match="tier_mix"):
        generate(replace(SPEC, tier_mix={Tier.IMMEDIATE: 0.5, Tier.NORMAL: 0.6}))
    with pytest.raises(ValueError, match="tier_mix"):
        generate(replace(SPEC, tier_mix={Tier.UNKNOWN: 0.5, Tier.NORMAL: 0.5}))


def test_three_policy_comparison_runs_the_same_calls_under_each_policy():
    result = three_policy_comparison(replace(SPEC, miss_rate=0.1, false_alarm_rate=0.1), max_normal_wait_s=1800)
    assert set(result) == {"fifo", "rules", "model"}
    totals = {name: sum(tier["calls"] for tier in summary["by_true_tier"].values()) for name, summary in result.items()}
    assert len(set(totals.values())) == 1
    assert result["rules"]["misses"] >= result["model"]["misses"]


def mix(immediate, priority, normal):
    return {Tier.IMMEDIATE: immediate, Tier.PRIORITY: priority, Tier.NORMAL: normal}


EXACT = mix({Tier.IMMEDIATE: 1.0}, {Tier.PRIORITY: 1.0}, {Tier.NORMAL: 1.0})
ALL_UNKNOWN = mix({Tier.UNKNOWN: 1.0}, {Tier.UNKNOWN: 1.0}, {Tier.UNKNOWN: 1.0})


def test_a_measured_mix_draws_each_assigned_tier_from_the_true_tiers_row():
    calls = generate(replace(SPEC, assigned_mix=mix({Tier.UNKNOWN: 1.0}, {Tier.NORMAL: 1.0}, {Tier.PRIORITY: 1.0})))
    expected = {Tier.IMMEDIATE: Tier.UNKNOWN, Tier.PRIORITY: Tier.NORMAL, Tier.NORMAL: Tier.PRIORITY}
    assert all(call.assigned_tier is expected[call.true_tier] for call in calls)
    split = generate(replace(SPEC, arrivals_per_hour=100, assigned_mix=mix(
        {Tier.IMMEDIATE: 0.5, Tier.NORMAL: 0.5}, {Tier.PRIORITY: 1.0}, {Tier.NORMAL: 1.0})))
    immediate = [call.assigned_tier for call in split if call.true_tier is Tier.IMMEDIATE]
    assert 0.3 < immediate.count(Tier.IMMEDIATE) / len(immediate) < 0.7


def test_a_measured_mix_keeps_the_calls_and_changes_only_assigned_tiers():
    plain, mixed = generate(SPEC), generate(replace(SPEC, assigned_mix=ALL_UNKNOWN))
    assert [(c.arrival, c.true_tier, c.service_time) for c in plain] == [(c.arrival, c.true_tier, c.service_time) for c in mixed]
    assert {c.assigned_tier for c in mixed} == {Tier.UNKNOWN}


@pytest.mark.parametrize("bad", [
    mix({Tier.IMMEDIATE: 0.5}, {Tier.PRIORITY: 1.0}, {Tier.NORMAL: 1.0}),  # does not sum to 1
    {Tier.IMMEDIATE: {Tier.IMMEDIATE: 1.0}, Tier.NORMAL: {Tier.NORMAL: 1.0}},  # no PRIORITY row
    mix({Tier.IMMEDIATE: 1.5, Tier.NORMAL: -0.5}, {Tier.PRIORITY: 1.0}, {Tier.NORMAL: 1.0}),
])
def test_a_measured_mix_must_be_a_distribution_for_every_true_tier(bad):
    with pytest.raises(ValueError, match="assigned_mix"):
        generate(replace(SPEC, assigned_mix=bad))


def test_measured_mixes_add_policies_on_the_same_calls():
    result = three_policy_comparison(SPEC, max_normal_wait_s=1800, measured={"model_measured": EXACT, "rules_measured": ALL_UNKNOWN})
    assert list(result) == ["fifo", "rules", "model", "model_measured", "rules_measured"]
    totals = {name: sum(tier["calls"] for tier in summary["by_true_tier"].values()) for name, summary in result.items()}
    assert len(set(totals.values())) == 1
    assert result["model_measured"]["misses"] == 0 and result["model_measured"]["assigned_share"]["unknown"] == 0.0
    assert result["rules_measured"]["assigned_share"]["unknown"] == 1.0
    # Everyone ranked UNKNOWN is served in arrival order, exactly as FIFO serves them.
    assert result["rules_measured"]["by_true_tier"] == result["fifo"]["by_true_tier"]


def test_a_measured_policy_cannot_replace_a_built_in_one():
    with pytest.raises(ValueError, match="model"):
        three_policy_comparison(SPEC, max_normal_wait_s=1800, measured={"model": EXACT})


def test_default_spec_is_a_labeled_overloaded_surge():
    assert DEFAULT_SPEC.arrivals_per_hour * DEFAULT_SPEC.mean_service_s / 3600 > DEFAULT_SPEC.operators
    assert abs(sum(DEFAULT_SPEC.tier_mix.values()) - 1) < 1e-9
    assert len(generate(DEFAULT_SPEC)) > 100
