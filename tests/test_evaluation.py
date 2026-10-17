import json

import pytest

from dualuse import evaluation
from dualuse.evaluation import assigned_mix, fifo_summary, measured_rates, proportion, summarize, wilson
from dualuse.triage import Tier


@pytest.mark.parametrize(("k", "n", "low", "high"), [(0, 10, 0.0, 0.2775), (5, 10, 0.2366, 0.7634), (10, 10, 0.7225, 1.0)])
def test_wilson_matches_published_intervals(k, n, low, high):
    assert wilson(k, n) == pytest.approx((low, high), abs=1e-4)


@pytest.mark.parametrize(("k", "n"), [(0, 0), (-1, 5), (6, 5)])
def test_wilson_rejects_impossible_counts(k, n):
    with pytest.raises(ValueError):
        wilson(k, n)


def test_proportion_reports_count_rate_and_interval():
    assert proportion(3, 4) == pytest.approx({"k": 3, "n": 4, "rate": 0.75, "low": wilson(3, 4)[0], "high": wilson(3, 4)[1]})


def row(label, tier, sampled=True, subset=False, review="", error=""):
    return {"label": label, "tier": tier, "sampled": sampled, "subset": subset, "review": review, "error": error}


ROWS = [
    row("needs", "immediate", subset=True),
    row("needs", "priority"),
    row("needs", "unknown", review="Unverified quotes dropped: x"),
    row("needs", "normal"),
    row("needs", "normal", sampled=False, subset=True),  # evaluated only for the subset
    row("routine", "normal"),
    row("routine", "normal"),
    row("routine", "unknown", error="RuntimeError: Interview did not complete (max_tokens)"),
    row("routine", "priority", review="Location not in the caller's words, dropped: x"),
]


def test_a_miss_is_a_needs_a_person_message_ranked_normal():
    assert summarize(ROWS)["miss"]["k"] == 1
    assert summarize(ROWS)["miss"]["n"] == 4  # the subset-only row is not part of the class sample


def test_a_false_alarm_is_a_routine_message_ranked_immediate_or_priority():
    result = summarize(ROWS)
    assert (result["false_alarm"]["k"], result["false_alarm"]["n"]) == (1, 4)


def test_unknown_is_neither_a_miss_nor_a_false_alarm_but_ranks_ahead_of_routine():
    result = summarize(ROWS)
    assert (result["routine_ahead"]["k"], result["routine_ahead"]["n"]) == (2, 4)


def test_the_rescue_medical_death_subset_counts_every_subset_row():
    result = summarize(ROWS)
    assert (result["subset_miss"]["k"], result["subset_miss"]["n"]) == (1, 2)
    assert (result["subset_immediate"]["k"], result["subset_immediate"]["n"]) == (1, 2)


def test_tier_counts_review_flags_and_failures_are_reported_per_class():
    result = summarize(ROWS)
    assert result["tiers"]["needs"] == {"immediate": 1, "priority": 1, "unknown": 1, "normal": 1}
    assert result["tiers"]["routine"] == {"immediate": 0, "priority": 1, "unknown": 1, "normal": 2}
    assert result["review"]["needs"]["k"] == 1 and result["review"]["routine"]["k"] == 1
    assert result["failed"] == 1


def test_summarize_needs_both_classes():
    with pytest.raises(ValueError, match="routine"):
        summarize([row("needs", "normal")])


def test_fifo_ranks_nobody_ahead_by_construction():
    result = fifo_summary(ROWS)
    assert result["by_construction"]
    assert (result["miss"]["k"], result["miss"]["n"], result["miss"]["rate"]) == (4, 4, 1.0)
    assert (result["false_alarm"]["rate"], result["routine_ahead"]["rate"], result["subset_miss"]["rate"]) == (0.0, 0.0, 1.0)


def saved_results(tmp_path):
    summaries = {method: {text: summarize(ROWS) for text in ("english", "original")} for method in ("rules", "model")}
    path = tmp_path / "eval_messages.json"
    path.write_text(json.dumps({"label": "recorded", "summaries": summaries}), encoding="utf-8")
    return path


def test_the_simulator_mix_maps_each_true_tier_to_its_proxy_class():
    mix = assigned_mix(summarize(ROWS))
    assert mix[Tier.IMMEDIATE] == {Tier.IMMEDIATE: 0.5, Tier.PRIORITY: 0.0, Tier.UNKNOWN: 0.0, Tier.NORMAL: 0.5}  # the subset
    assert mix[Tier.PRIORITY] == {Tier.IMMEDIATE: 0.25, Tier.PRIORITY: 0.25, Tier.UNKNOWN: 0.25, Tier.NORMAL: 0.25}  # needs
    assert mix[Tier.NORMAL] == {Tier.IMMEDIATE: 0.0, Tier.PRIORITY: 0.25, Tier.UNKNOWN: 0.25, Tier.NORMAL: 0.5}  # routine


def test_a_simulator_mix_needs_subset_messages():
    without_subset = [dict(r, subset=False) for r in ROWS]
    with pytest.raises(ValueError, match="subset"):
        assigned_mix(summarize(without_subset))


def test_measured_rates_carry_the_summary_and_a_plain_mix_for_display(tmp_path):
    rates = measured_rates(evaluation.load_results(saved_results(tmp_path)), "english")
    assert rates["model"]["miss"]["k"] == 1 and rates["rules"]["miss"]["n"] == 4
    assert rates["model"]["assigned_mix"]["normal"] == {"immediate": 0.0, "priority": 0.25, "unknown": 0.25, "normal": 0.5}


def test_measured_rates_reject_an_unknown_text_column(tmp_path):
    with pytest.raises(ValueError, match="text"):
        measured_rates(evaluation.load_results(saved_results(tmp_path)), "klingon")


def test_results_are_none_before_the_evaluation_has_run(tmp_path):
    assert evaluation.load_results(tmp_path / "missing.json") is None
