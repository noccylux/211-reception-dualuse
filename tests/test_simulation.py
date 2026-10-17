import math

from dualuse.simulation import Call, Outcome, compare, simulate, summarize
from dualuse.triage import Fifo, Tier, Tiered


def call(
    call_id: str,
    arrival: float,
    service_time: float = 100,
    true_tier: Tier = Tier.NORMAL,
    assigned_tier: Tier | None = None,
    decision_delay: float = 0,
    patience: float = math.inf,
) -> Call:
    return Call(
        call_id=call_id,
        arrival=arrival,
        service_time=service_time,
        patience=patience,
        true_tier=true_tier,
        assigned_tier=true_tier if assigned_tier is None else assigned_tier,
        decision_delay=decision_delay,
    )


def by_id(outcomes: list[Outcome]) -> dict[str, Outcome]:
    return {outcome.call_id: outcome for outcome in outcomes}


def test_one_operator_serves_fifo_calls_back_to_back():
    outcomes = by_id(simulate([call("a", 0, service_time=100), call("b", 10, service_time=50)], 1, Fifo()))
    assert outcomes["a"].started == 0 and outcomes["a"].wait == 0
    assert outcomes["b"].started == 100 and outcomes["b"].wait == 90


def test_two_operators_start_two_arrivals_at_once():
    outcomes = by_id(simulate([call("a", 0), call("b", 0)], 2, Fifo()))
    assert outcomes["a"].started == 0 and outcomes["b"].started == 0


def test_tiered_policy_serves_immediate_before_an_earlier_normal_caller():
    calls = [
        call("busy", 0, service_time=100),
        call("normal", 5),
        call("immediate", 10, true_tier=Tier.IMMEDIATE),
    ]
    assert by_id(simulate(calls, 1, Fifo()))["normal"].started == 100
    tiered = by_id(simulate(calls, 1, Tiered(max_normal_wait=3600)))
    assert tiered["immediate"].started == 100
    assert tiered["normal"].started == 200


def test_tier_is_unknown_until_the_decision_delay_has_passed():
    calls = [
        call("busy", 0, service_time=100),
        call("priority", 20, true_tier=Tier.PRIORITY),
        call("immediate", 30, true_tier=Tier.IMMEDIATE, decision_delay=100),
    ]
    policy = Tiered(max_normal_wait=3600)
    # At t=100 the immediate call is still UNKNOWN (known at 130), ranked with priority; the earlier priority call goes first.
    delayed = by_id(simulate(calls, 1, policy))
    assert delayed["priority"].started == 100 and delayed["immediate"].started == 200
    prompt = by_id(simulate([calls[0], calls[1], call("immediate", 30, true_tier=Tier.IMMEDIATE)], 1, policy))
    assert prompt["immediate"].started == 100


def test_caller_abandons_when_patience_runs_out_and_is_not_served_later():
    calls = [call("busy", 0, service_time=100), call("impatient", 10, patience=30), call("patient", 20)]
    outcomes = by_id(simulate(calls, 1, Fifo()))
    assert outcomes["impatient"].started is None
    assert outcomes["impatient"].abandoned_at == 40
    assert outcomes["impatient"].wait is None
    assert outcomes["patient"].started == 100


def test_simulate_returns_one_outcome_per_call_in_input_order():
    calls = [call("b", 10), call("a", 0)]
    assert [outcome.call_id for outcome in simulate(calls, 1, Fifo())] == ["b", "a"]


def test_summarize_reports_waits_per_true_tier_and_misses():
    outcomes = [
        Outcome("i1", Tier.IMMEDIATE, Tier.IMMEDIATE, arrival=0, started=10, abandoned_at=None),
        Outcome("i2", Tier.IMMEDIATE, Tier.NORMAL, arrival=0, started=30, abandoned_at=None),
        Outcome("n1", Tier.NORMAL, Tier.NORMAL, arrival=0, started=None, abandoned_at=50),
        Outcome("n2", Tier.NORMAL, Tier.PRIORITY, arrival=0, started=100, abandoned_at=None),
    ]
    summary = summarize(outcomes)
    immediate = summary["by_true_tier"]["immediate"]
    assert immediate["calls"] == 2 and immediate["served"] == 2 and immediate["abandoned"] == 0
    assert immediate["wait_mean"] == 20 and immediate["wait_p50"] == 10 and immediate["wait_p95"] == 30
    normal = summary["by_true_tier"]["normal"]
    assert normal["calls"] == 2 and normal["served"] == 1 and normal["abandoned"] == 1
    assert normal["wait_mean"] == 100
    assert summary["misses"] == 1
    assert summary["assigned_share"] == {"immediate": 0.25, "priority": 0.25, "unknown": 0.0, "normal": 0.5}
    assert summary["served"] == 3 and summary["abandoned"] == 1


def test_summarize_has_no_wait_statistics_for_a_tier_nobody_was_served_in():
    summary = summarize([Outcome("n", Tier.NORMAL, Tier.NORMAL, arrival=0, started=None, abandoned_at=5)])
    normal = summary["by_true_tier"]["normal"]
    assert normal["served"] == 0 and normal["wait_mean"] is None and normal["wait_p95"] is None
    assert summary["by_true_tier"]["immediate"]["calls"] == 0


def test_compare_runs_every_policy_on_the_same_calls():
    calls = [call("busy", 0, service_time=100), call("normal", 5), call("immediate", 10, true_tier=Tier.IMMEDIATE)]
    result = compare(calls, 1, [Fifo(), Tiered(max_normal_wait=3600)])
    assert set(result) == {"fifo", "tiered"}
    assert result["fifo"]["by_true_tier"]["immediate"]["wait_mean"] == 190
    assert result["tiered"]["by_true_tier"]["immediate"]["wait_mean"] == 90
    assert result["tiered"]["by_true_tier"]["normal"]["wait_p95"] == 195
