"""Evaluate the 211 desk's first-turn tiers on recorded disaster messages with proxy labels.

Data: Munro disaster response messages, direct messages of one split (test by default); CC BY 4.0,
Robert Munro (2012), Processing short message communications in low-resource languages, Stanford
University. These are SMS sent after the 2010 Haiti earthquake and Pakistan floods, and Hurricane
Sandy message-board posts; not 211 calls.
Proxy labels: request = 1 means the message needs a person, request = 0 is routine; messages that
also carry search_and_rescue, medical_help or death form a subset reported separately.

Each chosen message joins a fresh in-memory desk and speaks once, in the offline keyword mode and in
model mode (the app's reception.model_turn), on the English translation and on the original text.
Claude's raw responses are cached by request, so a rerun with unchanged playbooks costs nothing.

    bash scripts/uv-run.sh env -u ANTHROPIC_API_KEY python scripts/evaluate_messages.py [--split validation]

`env -u` lets dualuse.config load the key from .env when WSLENV forwards an empty variable.
Writes data/processed/eval_messages.json and the results block of docs/evaluation.md.

Playbook wording is tuned on the training split (`--split train`) and checked on the validation split,
whose messages are not read while tuning; `--model claude-sonnet-5-5` asks a larger model the same
requests for comparison. Those runs write data/processed/eval_messages_<split>_<model>.json and leave
the app's results and the docs alone. From a worktree, add PYTHONPATH=. so Python imports that worktree's dualuse package rather than
the editable install of the main checkout.
"""

import argparse
import csv
import hashlib
import json
import random
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import pydantic
from anthropic.types import Message

from dualuse import evaluation, reception
from dualuse.config import ROOT, require
from dualuse.extract import EXTRACTION_MODEL
from dualuse.holdqueue import HoldQueue
from dualuse.live_surge import MESSAGES

MANIFEST = ROOT / "docs/datasets.manifest.json"
CACHE = ROOT / "data/processed/eval_messages_cache.jsonl"
DOC = ROOT / "docs/evaluation.md"
START = "<!-- results:start, written by scripts/evaluate_messages.py -->"
END = "<!-- results:end -->"
COLUMNS = {"english": "message", "original": "original"}
MAX_NORMAL_WAIT_S = 1800  # the desk's aging guard; irrelevant for a single first turn
SPLITS = {"test": MESSAGES, "validation": MESSAGES.with_name("disaster_response_validation.csv"),
          "train": MESSAGES.with_name("disaster_response_training.csv")}
# USD per million tokens (Haiku: prompts up to 100K); cache writes 1.25x and reads 0.1x input.
PRICES = {
    "claude-haiku-5-5": {"input_tokens": 0.10, "output_tokens": 0.50, "cache_creation_input_tokens": 0.125,
                         "cache_read_input_tokens": 0.01},
    "claude-sonnet-5-5": {"input_tokens": 2.0, "output_tokens": 10.0, "cache_creation_input_tokens": 2.5,
                          "cache_read_input_tokens": 0.20},
}
TOKENS = tuple(PRICES[EXTRACTION_MODEL])
REVIEW_KINDS = ("Unverified quotes dropped", "Location not in the caller's words",
                "Life threat reported without a verified caller quote", "Reply withheld because it made a promise",
                "Interview failed", "the offline English keyword mode cannot read it")


def label(split: str) -> str:
    return (f"Recorded 2010 Haiti and Pakistan SMS and Hurricane Sandy message-board posts (Munro {split} split, "
            "direct messages, CC BY 4.0, Robert Munro 2012) with proxy category labels, first message only; not 211 calls")


def cost(usage: dict, model: str) -> float:
    return sum(usage[name] * price for name, price in PRICES[model].items()) / 1e6


def outputs(split: str, model: str) -> tuple[Path, bool]:
    """Where a run's results go, and whether it is the published run that feeds the app and the docs."""
    if split == "test" and model == EXTRACTION_MODEL:
        return evaluation.RESULTS, True
    return ROOT / f"data/processed/eval_messages_{split}_{model}.json", False


def cache_for(model: str) -> Path:
    return CACHE if model == EXTRACTION_MODEL else CACHE.with_name(f"eval_messages_cache_{model}.jsonl")


def manifest_sha256(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["datasets"]
    return next(f["sha256"] for d in entries for f in d["files"] if f["path"] == relative)


def _flag(raw: dict, name: str) -> bool:
    if raw[name] not in ("0", "1"):
        raise ValueError(f"message {raw['id']}: {name} is {raw[name]!r}, expected 0 or 1")
    return raw[name] == "1"


def load_messages(path: Path, sha256: str, split: str = "test") -> list[dict]:
    """Distinct direct messages of one split with their proxy labels; the file must match the
    manifest. A row repeated verbatim (two Sandy posts in the test split) counts once."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        raise ValueError(f"{path} has SHA-256 {digest}, the manifest says {sha256}; see docs/datasets.md")
    seen: dict[str, dict] = {}
    rows = []
    with path.open(encoding="utf-8", newline="") as file:
        for raw in csv.DictReader(file):
            if raw["split"] != split or raw["genre"] != "direct":
                continue
            if raw["id"] in seen:
                if seen[raw["id"]] != raw:
                    raise ValueError(f"message id {raw['id']} appears twice with different content")
                continue
            seen[raw["id"]] = raw
            # One direct message each in the training and validation splits has no translation; it is judged
            # on its original only.
            if not raw["message"].strip() and not raw["original"].strip():
                raise ValueError(f"message {raw['id']} has no text")
            request = _flag(raw, "request")
            danger = any(_flag(raw, name) for name in ("search_and_rescue", "medical_help", "death"))
            rows.append({"id": raw["id"], "event": raw["event"], "message": raw["message"].strip(),
                         "original": raw["original"].strip(), "label": "needs" if request else "routine",
                         "subset": request and danger})
    return rows


def choose(rows: list[dict], per_class: int, seed: int) -> list[dict]:
    """A seeded sample of per_class messages from each class, plus every subset message."""
    rng = random.Random(seed)
    picked = set()
    for label in ("needs", "routine"):
        pool = [r["id"] for r in rows if r["label"] == label]
        if per_class > len(pool):
            raise ValueError(f"only {len(pool)} {label} messages; cannot sample {per_class}")
        picked.update(rng.sample(pool, per_class))
    return [{**r, "sampled": r["id"] in picked} for r in rows if r["id"] in picked or r["subset"]]


def _client() -> anthropic.Anthropic:
    # Longer than the desk's 20 s and with retries: this run measures tiers, not latency.
    return anthropic.Anthropic(api_key=require("ANTHROPIC_API_KEY"), timeout=60.0, max_retries=3)


class CachedClient:
    """Stands in for anthropic.Anthropic inside model_turn. A request seen before returns its saved raw
    response, so a rerun replays the same answers through the current code without API calls. With a
    model, every request goes to that model instead of the desk's, and is cached under it."""

    def __init__(self, path: Path, make_client=_client, model: str | None = None):
        self.path, self._make_client, self._client, self.model = path, make_client, None, model
        self.messages = self  # model_turn calls client.messages.create(...)
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._saved: dict[str, dict] = {}
        self._used: set[str] = set()
        self.sent = self.reused = 0
        if path.exists():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path} line {number} is not valid JSON; remove that line and rerun") from error
                self._saved[entry["key"]] = entry["response"]

    def create(self, **request) -> Message:
        if self.model:
            request = {**request, "model": self.model}
        key = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self._lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:  # identical concurrent requests (an original equal to its translation) reach the API once
            with self._lock:
                saved = self._saved.get(key)
                if saved is None and self._client is None:
                    self._client = self._make_client()
            if saved is None:
                saved = self._client.messages.create(**request).model_dump(mode="json")
                with self._lock:
                    self._saved[key] = saved
                    with self.path.open("a", encoding="utf-8") as file:
                        file.write(json.dumps({"key": key, "response": saved}, ensure_ascii=False) + "\n")
                    self.sent += 1
            else:
                with self._lock:
                    self.reused += 1
            with self._lock:
                self._used.add(key)
        return Message.model_validate(saved)

    def usage(self) -> dict:
        """Token totals of the distinct responses this run used, whether sent now or replayed."""
        totals = Counter({name: 0 for name in TOKENS})
        for key in self._used:
            totals.update({name: self._saved[key]["usage"].get(name) or 0 for name in TOKENS})
        return {"responses": len(self._used), **totals}

    def models(self) -> list[str]:
        return sorted({self._saved[key]["model"] for key in self._used})


def first_turn(text: str, mode: str, client: CachedClient | None = None) -> dict:
    """What a fresh desk stores after a caller's first message: tier, review notes, any failure, language."""
    queue = HoldQueue(MAX_NORMAL_WAIT_S, mode=mode)
    call = queue.add(origin="evaluation")
    seen = {}

    def respond(dialogue, mode, facts):
        turn = reception.model_turn(dialogue, facts, client=client) if mode == "model" else reception.receive(dialogue, mode, facts)
        seen.update(language=turn.language, distress=turn.distress)
        return turn

    error = ""
    try:
        queue.say(call.call_id, text, responder=respond)
    except (RuntimeError, pydantic.ValidationError) as failure:
        # model_turn's own failures: an incomplete or malformed answer. The desk made the call UNKNOWN
        # and flagged it, as it would live. API and network errors propagate and stop the run.
        error = f"{type(failure).__name__}: {failure}"
    call = queue.call(call.call_id)
    return {"tier": call.tier.value, "review": call.attention, "error": error, **seen}


def run_model(jobs: list[tuple[dict, str]], client: CachedClient, workers: int) -> list[dict]:
    done, lock = 0, threading.Lock()

    def one(job):
        nonlocal done
        row, text = job
        outcome = first_turn(row[COLUMNS[text]], "model", client)
        with lock:
            done += 1
            if done % 25 == 0 or done == len(jobs):
                print(f"model turns {done}/{len(jobs)}: {client.sent} sent, {client.reused} from the cache", flush=True)
        return outcome

    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        try:
            return [future.result() for future in futures]
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise


def replace_block(path: Path, block: str) -> None:
    doc = path.read_text(encoding="utf-8")
    start, end = doc.find(START), doc.find(END)
    if start < 0 or end < start:
        raise ValueError(f"{path} lacks the results markers {START} and {END}")
    path.write_text(doc[:start + len(START)] + "\n" + block + "\n" + doc[end:], encoding="utf-8")


METHODS = {"fifo": "FIFO (reference)", "rules": "Offline keyword rules", "model": f"Claude model mode ({EXTRACTION_MODEL})"}
TEXT_NAMES = {"english": "English translation", "original": "Original text"}


def _rate(p: dict | None, by_construction: bool = False) -> str:
    if p is None:
        return "n/a"
    if by_construction:
        return f"{100 * p['rate']:.0f}% by construction"
    return f"{100 * p['rate']:.1f}% ({p['k']}/{p['n']}; {100 * p['low']:.1f}-{100 * p['high']:.1f}%)"


def markdown(results: dict) -> str:
    """The results block of docs/evaluation.md."""
    s, sample, usage = results["source"], results["sample"], results["usage"]
    methods = {**METHODS, "model": f"Claude model mode ({', '.join(results['desk']['models_seen'])})"}
    lines = [
        f"Generated {results['generated_at']} by `scripts/evaluate_messages.py`. {results['label']}.",
        "",
        f"* Population: {s['messages']:,} distinct direct messages of the {s['split']} split: {s['needs']} needs a person, "
        f"{s['routine']} routine, {s['subset']} in the rescue, medical or death subset.",
        f"* Sample (seed {sample['seed']}): {sample['per_class']} needs-a-person and {sample['per_class']} routine "
        f"messages, plus every subset message; {sample['evaluated']} messages evaluated "
        f"({sample['subset_in_sample']} subset messages were already in the class sample). Events: "
        + ", ".join(f"{name} {count}" for name, count in sample["events"].items()) + ".",
        f"* English text exists for {sample['with_english']} and original text for {sample['with_original']} of them; "
        "Sandy messages have no original.",
        f"* Claude: {usage['responses']} distinct responses from {', '.join(results['desk']['models_seen'])} "
        f"({usage['sent_this_run']} sent in this run, the rest replayed from the cache); "
        f"{usage['input_tokens']:,} uncached input, {usage['cache_read_input_tokens']:,} cache-read, "
        f"{usage['cache_creation_input_tokens']:,} cache-write and {usage['output_tokens']:,} output tokens; "
        f"about ${usage['cost_usd']:.2f} at list price.",
        "",
        "Rates with 95% Wilson intervals, as rate (count/n; interval):",
        "",
        "| Method | Text | Miss: needs a person ranked NORMAL | False alarm: routine ranked IMMEDIATE or PRIORITY "
        "| Routine ranked ahead of NORMAL, UNKNOWN included | Rescue, medical or death ranked NORMAL "
        "| Review flag, needs a person | Review flag, routine | Failed turns |",
        "|---|---|---|---|---|---|---|---|---:|",
    ]
    for method, name in methods.items():
        for text in evaluation.TEXTS:
            m = results["summaries"][method][text]
            fixed = m.get("by_construction", False)
            review = (["n/a", "n/a"] if fixed else [_rate(m["review"]["needs"]), _rate(m["review"]["routine"])])
            lines.append(f"| {name} | {TEXT_NAMES[text]} | {_rate(m['miss'], fixed)} | {_rate(m['false_alarm'], fixed)} "
                         f"| {_rate(m['routine_ahead'], fixed)} | {_rate(m['subset_miss'], fixed)} "
                         f"| {review[0]} | {review[1]} | {'n/a' if fixed else m['failed']} |")
    lines += ["", "Tiers the desk stored after the first message:", "",
              "| Method | Text | Messages | n | IMMEDIATE | PRIORITY | UNKNOWN | NORMAL |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for method in ("rules", "model"):
        for text in evaluation.TEXTS:
            tiers = results["summaries"][method][text]["tiers"]
            for group, title in (("needs", "needs a person (sample)"), ("routine", "routine (sample)"),
                                 ("subset", "rescue, medical or death (all)")):
                counts = tiers[group]
                lines.append(f"| {methods[method]} | {TEXT_NAMES[text]} | {title} | {sum(counts.values())} | "
                             + " | ".join(str(counts[t]) for t in ("immediate", "priority", "unknown", "normal")) + " |")
    lines += ["", "Review notes in model mode (messages with at least one note of each kind, all evaluated messages):", "",
              "| Text | " + " | ".join(REVIEW_KINDS[:5]) + " |", "|---|" + "---:|" * 5]
    for text in evaluation.TEXTS:
        kinds = results["review_kinds"]["model"][text]
        lines.append(f"| {TEXT_NAMES[text]} | " + " | ".join(str(kinds[kind]) for kind in REVIEW_KINDS[:5]) + " |")
    languages = results["languages"]["original"]
    lines += ["", "Language codes Claude reported for the original text: "
              + ", ".join(f"`{code}` {count}" for code, count in languages.items()) + "."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate first-turn tiers on recorded disaster messages (proxy labels).")
    parser.add_argument("--per-class", type=int, default=150, help="messages sampled from each class")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=4, help="concurrent Claude requests")
    parser.add_argument("--split", choices=SPLITS, default="test",
                        help="train to tune the playbooks, validation to check them, test for the published run")
    parser.add_argument("--model", choices=PRICES, default=EXTRACTION_MODEL, help="the model that answers each turn")
    args = parser.parse_args(argv)

    source = SPLITS[args.split]
    rows = load_messages(source, manifest_sha256(source), args.split)
    chosen = choose(rows, args.per_class, args.seed)
    jobs = [(row, text) for row in chosen for text in evaluation.TEXTS if row[COLUMNS[text]]]
    print(f"{len(rows)} direct messages; {len(chosen)} chosen; {len(jobs)} turns per method", flush=True)
    client = CachedClient(cache_for(args.model), model=args.model)
    outcomes = {"rules": [first_turn(row[COLUMNS[text]], "rules") for row, text in jobs],
                "model": run_model(jobs, client, args.workers)}
    records = [{"id": row["id"], "event": row["event"], "label": row["label"], "sampled": row["sampled"],
                "subset": row["subset"], "method": method, "text": text, **outcome}
               for method in outcomes for (row, text), outcome in zip(jobs, outcomes[method])]

    def select(method, text):
        return [r for r in records if r["method"] == method and r["text"] == text]

    summaries = {"fifo": {}, "rules": {}, "model": {}}
    for text in evaluation.TEXTS:
        summaries["fifo"][text] = evaluation.fifo_summary(select("rules", text))
        for method in ("rules", "model"):
            summaries[method][text] = evaluation.summarize(select(method, text))
    usage = client.usage()
    results = {
        "label": label(args.split),
        "generated_at": datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%a %Y-%m-%d %H:%M PT"),
        "source": {"file": source.relative_to(ROOT).as_posix(), "sha256": manifest_sha256(source),
                   "split": args.split, "genre": "direct", "license": "CC BY 4.0",
                   "citation": "Robert Munro (2012), Processing short message communications in low-resource "
                               "languages, Stanford University",
                   "messages": len(rows), "needs": sum(r["label"] == "needs" for r in rows),
                   "routine": sum(r["label"] == "routine" for r in rows), "subset": sum(r["subset"] for r in rows)},
        "sample": {"seed": args.seed, "per_class": args.per_class, "evaluated": len(chosen),
                   "subset_in_sample": sum(r["subset"] and r["sampled"] for r in chosen),
                   "with_english": sum(bool(r["message"]) for r in chosen),
                   "with_original": sum(bool(r["original"]) for r in chosen),
                   "events": dict(Counter(r["event"] for r in chosen).most_common())},
        "desk": {"model": args.model, "models_seen": client.models(), "profile": "la-211",
                 "playbooks_sha256": hashlib.sha256(reception.system_prompt().encode()).hexdigest(),
                 "turn": "one caller message to a fresh desk; the desk's facts, checks and failure handling apply"},
        "definitions": {
            "needs": "request = 1", "routine": "request = 0",
            "subset": "request = 1 and any of search_and_rescue, medical_help, death",
            "miss": "needs a person ranked NORMAL (under FIFO, every message: nobody is ranked ahead)",
            "false_alarm": "routine ranked IMMEDIATE or PRIORITY",
            "routine_ahead": "routine ranked IMMEDIATE, PRIORITY or UNKNOWN; UNKNOWN shares PRIORITY's rank, "
                             "so the scenario simulator uses this as its false-alarm rate",
        },
        "summaries": summaries,
        "review_kinds": {method: {text: {kind: sum(kind in r["review"] for r in select(method, text)) for kind in REVIEW_KINDS}
                                  for text in evaluation.TEXTS} for method in outcomes},
        "languages": {text: dict(Counter(r.get("language") or "(failed turn)" for r in select("model", text)).most_common())
                      for text in evaluation.TEXTS},
        "usage": {**usage, "sent_this_run": client.sent, "replayed": client.reused,
                  "cost_usd": round(cost(usage, args.model), 4)},
        "rows": records,
    }
    path, publish = outputs(args.split, args.model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    block = markdown(results)
    if publish:
        replace_block(DOC, block)
    print(block)
    print(f"\nWrote {path.relative_to(ROOT)}" + (f" and the results block of {DOC.relative_to(ROOT)}" if publish else ""))


if __name__ == "__main__":
    main()
