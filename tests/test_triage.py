from dualuse.triage import Fifo, Tier, Tiered, Waiting, order, pick_next


def waiting(call_id: str, arrival: float, tier: Tier) -> Waiting:
    return Waiting(call_id=call_id, arrival=arrival, tier=tier)


def ids(calls: list[Waiting]) -> list[str]:
    return [call.call_id for call in calls]


def test_fifo_orders_by_arrival_regardless_of_tier():
    calls = [
        waiting("late-immediate", 30, Tier.IMMEDIATE),
        waiting("early-normal", 10, Tier.NORMAL),
        waiting("middle-unknown", 20, Tier.UNKNOWN),
    ]
    assert ids(order(calls, Fifo(), now=60)) == ["early-normal", "middle-unknown", "late-immediate"]


def test_tiered_puts_immediate_before_an_earlier_normal_caller():
    calls = [waiting("normal", 0, Tier.NORMAL), waiting("immediate", 100, Tier.IMMEDIATE)]
    assert ids(order(calls, Tiered(max_normal_wait=3600), now=120)) == ["immediate", "normal"]


def test_tiered_keeps_fifo_inside_a_tier():
    calls = [
        waiting("second-priority", 50, Tier.PRIORITY),
        waiting("first-priority", 10, Tier.PRIORITY),
        waiting("second-immediate", 40, Tier.IMMEDIATE),
        waiting("first-immediate", 20, Tier.IMMEDIATE),
    ]
    assert ids(order(calls, Tiered(max_normal_wait=3600), now=60)) == [
        "first-immediate",
        "second-immediate",
        "first-priority",
        "second-priority",
    ]


def test_unknown_ranks_with_priority_and_ahead_of_normal():
    calls = [
        waiting("normal", 0, Tier.NORMAL),
        waiting("priority", 10, Tier.PRIORITY),
        waiting("unknown", 5, Tier.UNKNOWN),
    ]
    assert ids(order(calls, Tiered(max_normal_wait=3600), now=20)) == ["unknown", "priority", "normal"]


def test_aging_guard_promotes_a_normal_caller_after_max_wait():
    calls = [waiting("old-normal", 0, Tier.NORMAL), waiting("new-priority", 500, Tier.PRIORITY)]
    policy = Tiered(max_normal_wait=600)
    assert ids(order(calls, policy, now=599)) == ["new-priority", "old-normal"]
    assert ids(order(calls, policy, now=600)) == ["old-normal", "new-priority"]


def test_aging_guard_never_outranks_immediate():
    calls = [waiting("old-normal", 0, Tier.NORMAL), waiting("immediate", 5000, Tier.IMMEDIATE)]
    assert ids(order(calls, Tiered(max_normal_wait=600), now=6000)) == ["immediate", "old-normal"]


def test_pick_next_returns_head_or_none():
    policy = Tiered(max_normal_wait=600)
    assert pick_next([], policy, now=0) is None
    head = pick_next([waiting("a", 0, Tier.NORMAL), waiting("b", 1, Tier.PRIORITY)], policy, now=2)
    assert head is not None and head.call_id == "b"


def test_policies_report_their_names():
    assert Fifo().name == "fifo"
    assert Tiered(max_normal_wait=600).name == "tiered"
