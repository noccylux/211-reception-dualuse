"""The CrisisFusion scorer as a shadow second opinion beside our tier."""
import pytest
from fastapi.testclient import TestClient

from dualuse import api
from dualuse.holdqueue import HoldQueue
from dualuse.shadow import UNSUPPORTED, ShadowScorer, disagrees, scorer_language


def scored_text(shadow, call_id):
    return shadow.engine.s["calls"][call_id]["text"], shadow.engine.s["calls"][call_id]["revision"]


@pytest.mark.parametrize("language, text, expected", [
    ("en", "my roof is leaking", "en"), ("es", "necesito comida", "es"), ("zh", "需要帮助", "unknown"),
    ("fr", "j'ai besoin d'aide", "unknown"), ("unknown", "...", "unknown"),
    ("en", "help 着火了", "unknown"),  # a mislabeled call never gets an English-rule number
])
def test_language_maps_to_what_the_scorer_covers(language, text, expected):
    assert scorer_language(language, text) == expected


def test_scorer_reads_only_the_callers_words_with_a_revision_per_caller_turn():
    queue = HoldQueue(1800, mode="rules")
    shadow = ShadowScorer(queue.snapshot)
    call = queue.add()
    queue.say(call.call_id, "There is a fire at 123 Main St")
    shadow.sync_once()
    shadow.sync_once()  # unchanged text sends nothing new
    assert scored_text(shadow, call.call_id) == ("There is a fire at 123 Main St", 1)
    queue.say(call.call_id, "and I am trapped")
    shadow.sync_once()
    text, revision = scored_text(shadow, call.call_id)
    assert (text, revision) == ("There is a fire at 123 Main St\nand I am trapped", 2)
    desk_lines = [t["text"] for t in queue.snapshot()["calls"][0]["dialogue"] if t["speaker"] != "caller"]
    assert desk_lines and not any(line in text for line in desk_lines)
    assert shadow.opinion(call.call_id)["band"] == "IMMEDIATE_HUMAN"


def test_unsupported_language_shows_a_human_check_instead_of_a_number():
    queue = HoldQueue(1800, mode="rules", profile="cn-12345")
    shadow = ShadowScorer(queue.snapshot)
    call = queue.add()
    queue.say(call.call_id, "我家楼下着火了")
    shadow.sync_once()
    assert shadow.opinion(call.call_id) == {"supported": False, "score": None, "band": None, "needs": [],
                                            "disagree": False, "note": UNSUPPORTED}


@pytest.mark.parametrize("tier, band, expected", [
    ("immediate", "IMMEDIATE_HUMAN", False), ("immediate", "HUMAN_VERIFY", True),
    ("priority", "HUMAN_VERIFY", False), ("unknown", "HUMAN_VERIFY", False), ("unknown", "IMMEDIATE_HUMAN", True),
    ("normal", "ROUTINE_HUMAN", False), ("normal", "AUTOMATION_ELIGIBLE", False), ("normal", "HUMAN_VERIFY", True),
    ("priority", "ROUTINE_HUMAN", True), ("normal", None, False),
])
def test_disagreement_follows_the_scorers_policy_bands(tier, band, expected):
    assert disagrees(tier, band) is expected


def test_offline_desk_misses_spanish_danger_and_the_scorer_flags_it():
    queue = HoldQueue(1800, mode="rules")
    shadow = ShadowScorer(queue.snapshot)
    call = queue.add()
    queue.say(call.call_id, "Hay un incendio y estoy atrapado en el segundo piso")
    shadow.sync_once()
    opinion = shadow.opinion(call.call_id)
    assert queue.call(call.call_id).tier.value == "unknown"  # English keyword baseline
    assert opinion["band"] == "IMMEDIATE_HUMAN" and opinion["disagree"] is True


def test_scoring_never_changes_a_tier_or_the_queue_order():
    queue = HoldQueue(1800, mode="rules")
    shadow = ShadowScorer(queue.snapshot)
    for text in ("is the food bank open tomorrow", "Hay un incendio y estoy atrapado", "fire at 5 Oak Ave and I am trapped"):
        queue.say(queue.add().call_id, text)

    def view():
        snapshot = queue.snapshot()
        return [(c["call_id"], c["tier"], c["version"]) for c in snapshot["waiting"]], snapshot["events"]

    before = view()
    shadow.sync_once()
    assert len(shadow.opinions) == 3
    assert view() == before


def test_scorer_errors_surface_in_state():
    client = TestClient(api.app, base_url="http://127.0.0.1")
    client.post("/reset", json={"mode": "rules"})
    call_id = client.post("/calls", json={}).json()["call_id"]
    for _ in range(6):  # 24,000 characters: over the scorer's 20,000-character transcript limit
        client.post(f"/calls/{call_id}/say", json={"text": "x" * 4000})
    with pytest.raises(ValueError):
        api.SHADOW.sync_once()
    state = client.get("/state").json()
    assert call_id in state["scorer"]["error"] and "20000" in state["scorer"]["error"]
    assert "never changes a tier or the queue order" in " ".join(state["invariants"])
    client.post("/reset", json={"mode": "rules"})
