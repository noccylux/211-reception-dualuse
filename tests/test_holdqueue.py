import pytest

from dualuse.extract import Classification, Extraction
from dualuse.holdqueue import HoldQueue
from dualuse.triage import Tier


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def classification(tier: Tier, location: str | None = "Altadena", situation: str = "smoke") -> Classification:
    return Classification(
        extraction=Extraction(
            situation=situation,
            need="help",
            location=location,
            life_threat_now=tier is Tier.IMMEDIATE,
            needs_person_soon=tier is Tier.PRIORITY,
            enough_information=tier is not Tier.UNKNOWN,
            evidence=["quoted words"],
            missing=[],
            language="English",
        ),
        tier=tier,
        source="test",
    )


def make_queue() -> tuple[HoldQueue, Clock]:
    clock = Clock()
    return HoldQueue(max_normal_wait=1800, clock=clock), clock


def test_new_call_starts_unknown_at_the_current_time():
    queue, clock = make_queue()
    clock.now = 12.5
    call = queue.add("c1")
    assert call.tier is Tier.UNKNOWN and call.arrival == 12.5 and call.transcript == []


def test_say_appends_the_utterance_and_applies_the_classification():
    queue, _ = make_queue()
    queue.add("c1")
    call = queue.say("c1", "my house is on fire", lambda transcript: classification(Tier.IMMEDIATE))
    assert call.transcript == ["my house is on fire"]
    assert call.tier is Tier.IMMEDIATE and call.source == "test"
    assert call.extraction is not None and call.extraction.situation == "smoke"


def test_say_classifies_the_whole_transcript_so_far():
    queue, _ = make_queue()
    queue.add("c1")
    seen = []
    queue.say("c1", "hello", lambda transcript: (seen.append(transcript), classification(Tier.UNKNOWN))[1])
    queue.say("c1", "my kid is inside", lambda transcript: (seen.append(transcript), classification(Tier.IMMEDIATE))[1])
    assert seen == ["hello", "hello\nmy kid is inside"]


def test_tiered_order_moves_an_immediate_call_ahead_while_fifo_order_does_not():
    queue, clock = make_queue()
    queue.add("first")
    clock.now = 10
    queue.add("second")
    queue.say("second", "fire", lambda transcript: classification(Tier.IMMEDIATE))
    assert [call.call_id for call in queue.order("fifo")] == ["first", "second"]
    assert [call.call_id for call in queue.order("tiered")] == ["second", "first"]


def test_operator_free_hands_off_the_tiered_head_with_a_summary():
    queue, clock = make_queue()
    queue.add("first")
    clock.now = 10
    queue.add("second")
    queue.say("second", "fire", lambda transcript: classification(Tier.IMMEDIATE))
    clock.now = 130
    handoff = queue.operator_free()
    assert handoff is not None
    assert handoff.call_id == "second" and handoff.tier is Tier.IMMEDIATE
    assert handoff.waited_s == 120
    assert "smoke" in handoff.summary and "IMMEDIATE" in handoff.summary
    assert [call.call_id for call in queue.order("tiered")] == ["first"]
    assert queue.handoffs == [handoff]


def test_operator_free_returns_none_when_nobody_waits():
    queue, _ = make_queue()
    assert queue.operator_free() is None


def test_fifo_mode_hands_off_by_arrival_regardless_of_tier():
    queue, clock = make_queue()
    queue.add("first")
    clock.now = 10
    queue.add("second")
    queue.say("second", "fire", lambda transcript: classification(Tier.IMMEDIATE))
    queue.mode = "fifo"
    handoff = queue.operator_free()
    assert handoff is not None and handoff.call_id == "first"


def test_hang_up_is_the_callers_choice_and_leaves_the_queue():
    queue, clock = make_queue()
    queue.add("c1")
    clock.now = 40
    departed = queue.hang_up("c1")
    assert departed.call_id == "c1" and departed.waited_s == 40 and departed.reason == "caller_hung_up"
    assert queue.order("fifo") == []
    assert queue.departed == [departed]


def test_unknown_call_id_is_an_error():
    queue, _ = make_queue()
    with pytest.raises(KeyError):
        queue.say("missing", "hello", lambda transcript: classification(Tier.UNKNOWN))


def test_clusters_group_waiting_calls_by_stated_location():
    queue, _ = make_queue()
    for call_id, location in [("a", "Altadena"), ("b", "altadena "), ("c", "Pasadena"), ("d", None)]:
        queue.add(call_id)
        queue.say(call_id, "smoke", lambda transcript, location=location: classification(Tier.PRIORITY, location))
    clusters = queue.clusters()
    assert clusters[0]["location"] == "altadena" and clusters[0]["count"] == 2
    assert clusters[0]["call_ids"] == ["a", "b"]
    assert [cluster["location"] for cluster in clusters] == ["altadena", "pasadena"]


def test_mode_must_be_one_of_the_known_modes():
    queue, _ = make_queue()
    with pytest.raises(ValueError, match="mode"):
        queue.mode = "oracle"
