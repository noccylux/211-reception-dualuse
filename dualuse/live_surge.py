"""Inject a batch of callers into the live desk to show a congested queue.

Every caller is labeled: team-written scripts are simulated; Munro messages are recorded
disaster messages (2010 Haiti earthquake, Sandy, Pakistan floods; English translation as
published, CC BY 4.0, Robert Munro 2012) used as first messages, not 211 calls. The
"austin" pattern time-compresses real Austin APD 911 dispatch timestamps.
"""

import csv
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from dualuse.config import ROOT
from dualuse.holdqueue import Conflict, HoldQueue
from dualuse.surge_scripts import SCRIPTS

MESSAGES = ROOT / "data/raw/rmunro/disaster_response_messages/disaster_response_test.csv"
AUSTIN_DAY = ROOT / "data/processed/austin_busiest_day.json"
PAUSE_S = 1.5  # between a scripted caller's lines, after the assistant replied


@dataclass(frozen=True)
class Caller:
    lines: tuple[str, ...]
    origin: str


def load_messages(path: Path, count: int, seed: int) -> list[Caller]:
    """First-person messages from the test split only; the training split is never used."""
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; see docs/datasets.md")
    with path.open(encoding="utf-8", newline="") as file:
        rows = [row for row in csv.DictReader(file)
                if row["split"] == "test" and row["genre"] == "direct" and row["message"].strip()]
    chosen = random.Random(seed).sample(rows, min(count, len(rows)))
    return [Caller((row["message"].strip(),), f"recorded: Munro disaster message {row['id']} ({row['event']})")
            for row in chosen]


def plan_surge(count: int, source: str, seed: int, messages_path: Path = MESSAGES) -> list[Caller]:
    rng = random.Random(seed)
    scripts = [Caller(lines, "simulated: team-written script") for lines in SCRIPTS]  # authored order
    if source == "scripts":
        return [scripts[i % len(scripts)] for i in range(count)]
    if source == "messages":
        return load_messages(messages_path, count, seed)
    half = count // 2
    callers = [scripts[i % len(scripts)] for i in range(count - half)] + load_messages(messages_path, half, seed)
    rng.shuffle(callers)
    return callers


def arrival_offsets(count: int, span_s: float, pattern: str, seed: int, austin_path: Path = AUSTIN_DAY) -> list[float]:
    """Seconds after the start at which each caller joins."""
    if pattern == "even":
        return [span_s * i / (count - 1) for i in range(count)] if count > 1 else [0.0]
    if not austin_path.exists():
        raise FileNotFoundError(f"{austin_path} is missing; run scripts/preprocess_austin.py on the 911 branch")
    seconds = sorted(row["seconds"] for row in json.loads(austin_path.read_text(encoding="utf-8"))["rows"])
    if count > len(seconds):
        raise ValueError(f"the Austin day has only {len(seconds)} arrivals")
    start = random.Random(seed).randrange(len(seconds) - count + 1)
    window = seconds[start:start + count]
    gap = window[-1] - window[0]
    return [(t - window[0]) * span_s / gap if gap else 0.0 for t in window]


def start_surge(queue: HoldQueue, callers: list[Caller], offsets: list[float], status: dict | None = None,
                sleep=time.sleep, workers: int = 4) -> threading.Thread:
    """Run the batch in the background; progress and every failure land in `status`."""
    status = {} if status is None else status
    status.update(planned=len(callers), joined=0, turns=0, errors=[])
    lock = threading.Lock()

    def converse(caller: Caller):
        call = queue.add(origin=caller.origin)
        with lock:
            status["joined"] += 1
        for text in caller.lines:
            try:
                queue.say(call.call_id, text)
            except Conflict:
                return  # an operator reserved the call or it ended; the caller stops talking to the assistant
            except Exception as error:  # the desk already flagged the call; report the failure here too
                with lock:
                    status["errors"].append(f"{call.call_id}: {type(error).__name__}: {error}")
                return
            with lock:
                status["turns"] += 1
            sleep(PAUSE_S)

    def run():
        previous = 0.0
        with ThreadPoolExecutor(workers) as pool:
            for offset, caller in sorted(zip(offsets, callers), key=lambda pair: pair[0]):
                sleep(max(0.0, offset - previous))
                previous = offset
                pool.submit(converse, caller)

    thread = threading.Thread(target=run, daemon=True, name="live-surge")
    thread.start()
    return thread
