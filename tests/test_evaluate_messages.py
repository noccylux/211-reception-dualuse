"""The evaluation script's data handling, response cache and desk path; no network calls."""
import csv
import hashlib
import importlib.util
import json
import threading
from pathlib import Path

import anthropic
import httpx2
import pytest
from anthropic.types import Message

spec = importlib.util.spec_from_file_location("evaluate_messages", Path(__file__).resolve().parent.parent / "scripts/evaluate_messages.py")
evaluate_messages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate_messages)

FIELDS = ["id", "split", "message", "original", "genre", "request", "search_and_rescue", "medical_help", "death", "event"]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"split": "test", "genre": "direct", "original": "", "search_and_rescue": 0,
                             "medical_help": 0, "death": 0, "event": "haiti_earthquake", **row})
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_messages_keeps_direct_test_messages_and_marks_the_subset(tmp_path):
    path = tmp_path / "test.csv"
    digest = write_csv(path, [
        {"id": 1, "message": "We need water", "original": "Nou bezwen dlo", "request": 1},
        {"id": 2, "message": "People trapped under the church", "request": 1, "search_and_rescue": 1},
        {"id": 3, "message": "Weather news", "request": 0, "genre": "news"},
        {"id": 4, "message": "Doctors needed", "request": 0, "medical_help": 1},
    ])
    rows = evaluate_messages.load_messages(path, digest)
    assert [r["id"] for r in rows] == ["1", "2", "4"]
    assert [r["label"] for r in rows] == ["needs", "needs", "routine"]
    assert [r["subset"] for r in rows] == [False, True, False]  # the subset needs request = 1
    assert rows[0]["original"] == "Nou bezwen dlo" and rows[1]["original"] == ""


def test_load_messages_reads_only_the_requested_split(tmp_path):
    path = tmp_path / "validation.csv"
    digest = write_csv(path, [{"id": 1, "message": "We need water", "request": 1, "split": "validation"},
                              {"id": 2, "message": "Weather news", "request": 0}])
    assert [r["id"] for r in evaluate_messages.load_messages(path, digest, split="validation")] == ["1"]
    assert [r["id"] for r in evaluate_messages.load_messages(path, digest)] == ["2"]


def test_a_message_without_english_is_kept_for_its_original_and_one_without_any_text_fails(tmp_path):
    path = tmp_path / "test.csv"
    digest = write_csv(path, [{"id": 1, "message": " ", "original": "Shikarpur", "request": 0}])
    assert [(r["message"], r["original"]) for r in evaluate_messages.load_messages(path, digest)] == [("", "Shikarpur")]
    digest = write_csv(path, [{"id": 2, "message": " ", "original": "", "request": 0}])
    with pytest.raises(ValueError, match="message 2 has no text"):
        evaluate_messages.load_messages(path, digest)


def test_load_messages_keeps_one_copy_of_a_repeated_message(tmp_path):
    path = tmp_path / "test.csv"
    digest = write_csv(path, [{"id": 7, "message": "We can donate clothing", "request": 0}] * 2
                       + [{"id": 8, "message": "We need water", "request": 1}])
    assert [r["id"] for r in evaluate_messages.load_messages(path, digest)] == ["7", "8"]


def test_load_messages_rejects_one_id_with_two_different_messages(tmp_path):
    path = tmp_path / "test.csv"
    digest = write_csv(path, [{"id": 7, "message": "We can donate clothing", "request": 0},
                              {"id": 7, "message": "We need water", "request": 1}])
    with pytest.raises(ValueError, match="7"):
        evaluate_messages.load_messages(path, digest)


def test_load_messages_refuses_a_changed_file(tmp_path):
    path = tmp_path / "test.csv"
    write_csv(path, [{"id": 1, "message": "We need water", "request": 1}])
    with pytest.raises(ValueError, match="SHA-256"):
        evaluate_messages.load_messages(path, "0" * 64)


def test_load_messages_rejects_a_request_label_outside_zero_and_one(tmp_path):
    path = tmp_path / "test.csv"
    digest = write_csv(path, [{"id": 1, "message": "We need water", "request": 2}])
    with pytest.raises(ValueError, match="request"):
        evaluate_messages.load_messages(path, digest)


def rows_for_sampling():
    rows = []
    for i in range(40):
        label = "needs" if i % 2 else "routine"
        rows.append({"id": str(i), "label": label, "subset": label == "needs" and i % 4 == 1,
                     "message": f"m{i}", "original": "", "event": "haiti_earthquake"})
    return rows


def test_choose_is_seeded_stratified_and_keeps_the_whole_subset():
    rows = rows_for_sampling()
    chosen = evaluate_messages.choose(rows, per_class=5, seed=7)
    assert chosen == evaluate_messages.choose(rows, per_class=5, seed=7)
    assert chosen != evaluate_messages.choose(rows, per_class=5, seed=8)
    sampled = [r for r in chosen if r["sampled"]]
    assert sum(r["label"] == "needs" for r in sampled) == 5 and sum(r["label"] == "routine" for r in sampled) == 5
    assert {r["id"] for r in rows if r["subset"]} <= {r["id"] for r in chosen}


def test_choose_refuses_a_sample_larger_than_a_class():
    with pytest.raises(ValueError, match="only 20 needs messages"):
        evaluate_messages.choose(rows_for_sampling(), per_class=21, seed=7)


def interview(life=True, evidence=("on fire",), location=None):
    extraction = {"situation": "caller reports danger", "need": "", "location": location,
                  "life_threat_now": life, "needs_person_soon": False, "enough_information": True,
                  "evidence": list(evidence), "missing": [], "language": "English", "incident_kind": "fire",
                  "report_only": False, "safety": "danger" if life else "unknown"}
    return {"extraction": extraction, "topic": "location", "reply": "Where are you right now?",
            "language_code": "en", "distress": "worried"}


def message(payload, stop_reason="end_turn"):
    return Message.model_validate({
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": json.dumps(payload)}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 7, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 30},
    })


class Upstream:
    """Counts requests; returns one canned response, or raises the given error."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, 0
        self.messages = self

    def create(self, **request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def test_the_cache_sends_a_request_once_and_replays_it_from_disk(tmp_path):
    upstream = Upstream(message(interview()))
    path = tmp_path / "cache.jsonl"
    client = evaluate_messages.CachedClient(path, lambda: upstream)
    first = client.messages.create(model="m", messages=[{"role": "user", "content": "fire"}])
    again = client.messages.create(model="m", messages=[{"role": "user", "content": "fire"}])
    other = client.messages.create(model="m", messages=[{"role": "user", "content": "smoke"}])
    assert upstream.calls == 2 and first == again and isinstance(other, Message)
    replay = evaluate_messages.CachedClient(path, lambda: pytest.fail("a cached request reached the API"))
    assert replay.messages.create(model="m", messages=[{"role": "user", "content": "fire"}]) == first
    assert (replay.sent, replay.reused) == (0, 1)
    assert replay.usage() == {"responses": 1, "input_tokens": 12, "output_tokens": 7,
                              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 30}


def test_concurrent_identical_requests_reach_the_api_once(tmp_path):
    release = threading.Event()

    class Slow(Upstream):
        def create(self, **request):
            assert release.wait(5)
            return super().create(**request)

    upstream = Slow(message(interview()))
    client = evaluate_messages.CachedClient(tmp_path / "cache.jsonl", lambda: upstream)
    threads = [threading.Thread(target=client.messages.create, kwargs={"model": "m", "messages": []}) for _ in range(3)]
    for thread in threads:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(5)
    assert upstream.calls == 1


def test_a_model_override_sends_and_caches_each_request_under_that_model(tmp_path):
    models = []

    class Recording(Upstream):
        def create(self, **request):
            models.append(request["model"])
            return super().create(**request)

    upstream = Recording(message(interview()))
    path = tmp_path / "cache.jsonl"
    evaluate_messages.CachedClient(path, lambda: upstream).messages.create(model="claude-haiku-5-5", messages=[])
    sonnet = evaluate_messages.CachedClient(path, lambda: upstream, model="claude-sonnet-5-5")
    sonnet.messages.create(model="claude-haiku-5-5", messages=[])
    assert models == ["claude-haiku-5-5", "claude-sonnet-5-5"] and sonnet.sent == 1


def test_only_the_test_split_with_the_desk_model_feeds_the_app_and_the_docs():
    assert evaluate_messages.outputs("test", "claude-haiku-5-5") == (evaluate_messages.evaluation.RESULTS, True)
    path, publish = evaluate_messages.outputs("validation", "claude-haiku-5-5")
    assert not publish and path != evaluate_messages.evaluation.RESULTS and "validation" in path.name
    assert evaluate_messages.outputs("test", "claude-sonnet-5-5")[1] is False
    # Each model writes its own cache, so runs of two models can proceed at the same time.
    assert evaluate_messages.cache_for("claude-haiku-5-5") == evaluate_messages.CACHE
    assert evaluate_messages.cache_for("claude-sonnet-5-5") != evaluate_messages.CACHE


def test_the_cost_uses_the_price_of_the_model_that_answered():
    usage = {"input_tokens": 0, "output_tokens": 1_000_000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert evaluate_messages.cost(usage, "claude-haiku-5-5") == pytest.approx(0.50)
    assert evaluate_messages.cost(usage, "claude-sonnet-5-5") == pytest.approx(10.0)


def test_a_corrupt_cache_line_fails_loudly(tmp_path):
    path = tmp_path / "cache.jsonl"
    path.write_text('{"key": "abc", "response":\n', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        evaluate_messages.CachedClient(path, lambda: None)


def test_first_turn_in_offline_mode_uses_the_keyword_rules():
    outcome = evaluate_messages.first_turn("My house is on fire and my kid is inside", "rules")
    assert outcome["tier"] == "immediate" and outcome["error"] == ""


def test_first_turn_in_model_mode_stores_the_desk_tier_and_review_notes(tmp_path):
    client = evaluate_messages.CachedClient(tmp_path / "cache.jsonl", lambda: Upstream(message(interview(evidence=("on fire", "invented")))))
    outcome = evaluate_messages.first_turn("My house is on fire", "model", client)
    assert outcome["tier"] == "immediate"
    assert "Unverified quotes dropped: invented" in outcome["review"]
    assert outcome["language"] == "en" and outcome["error"] == ""


def test_an_incomplete_model_answer_is_counted_as_the_desk_counts_it(tmp_path):
    client = evaluate_messages.CachedClient(tmp_path / "cache.jsonl", lambda: Upstream(message(interview(), stop_reason="max_tokens")))
    outcome = evaluate_messages.first_turn("We need water", "model", client)
    assert outcome["tier"] == "unknown"
    assert "max_tokens" in outcome["error"] and "Interview failed" in outcome["review"]


def test_an_api_failure_stops_the_run_instead_of_becoming_a_result(tmp_path):
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client = evaluate_messages.CachedClient(tmp_path / "cache.jsonl", lambda: Upstream(error=error))
    with pytest.raises(anthropic.APIConnectionError):
        evaluate_messages.first_turn("We need water", "model", client)


def test_the_results_block_reports_every_method_text_and_label():
    rows = [{"label": label, "tier": tier, "sampled": True, "subset": label == "needs", "review": "", "error": ""}
            for label, tier in (("needs", "normal"), ("routine", "unknown"))]
    summaries = {m: {t: evaluate_messages.evaluation.summarize(rows) for t in ("english", "original")} for m in ("rules", "model")}
    summaries["fifo"] = {t: evaluate_messages.evaluation.fifo_summary(rows) for t in ("english", "original")}
    results = {
        "label": evaluate_messages.label("test"), "generated_at": "Sat 2026-10-17 13:30 PT", "summaries": summaries,
        "source": {"split": "test", "messages": 1069, "needs": 422, "routine": 647, "subset": 83},
        "sample": {"seed": 7, "per_class": 150, "evaluated": 357, "subset_in_sample": 26, "with_original": 341,
                   "events": {"haiti_earthquake": 330}},
        "desk": {"models_seen": ["claude-haiku-5-5"]},
        "usage": {"responses": 2, "sent_this_run": 0, "input_tokens": 1, "output_tokens": 2,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 3, "cost_usd": 0.0},
        "review_kinds": {"model": {t: dict.fromkeys(evaluate_messages.REVIEW_KINDS, 0) for t in ("english", "original")}},
        "languages": {"original": {"ht": 1}},
    }
    block = evaluate_messages.markdown(results)
    assert "not 211 calls" in block
    assert "| FIFO (reference) | English translation | 100% by construction | 0% by construction |" in block
    assert "| Claude model mode (claude-haiku-5-5) | Original text | 100.0% (1/1; " in block
    assert "`ht` 1" in block
    results["desk"]["models_seen"], results["source"]["split"] = ["claude-sonnet-5-5"], "validation"
    other = evaluate_messages.markdown(results)
    assert "| Claude model mode (claude-sonnet-5-5) | Original text |" in other and "of the validation split" in other


def test_the_docs_results_block_is_replaced_between_its_markers(tmp_path):
    doc = tmp_path / "evaluation.md"
    doc.write_text(f"intro\n{evaluate_messages.START}\nold\n{evaluate_messages.END}\noutro\n", encoding="utf-8")
    evaluate_messages.replace_block(doc, "new table")
    assert doc.read_text(encoding="utf-8") == f"intro\n{evaluate_messages.START}\nnew table\n{evaluate_messages.END}\noutro\n"
    doc.write_text("no markers", encoding="utf-8")
    with pytest.raises(ValueError, match="marker"):
        evaluate_messages.replace_block(doc, "new table")
