"""Shadow second opinion: the vendored CrisisFusion scorer reads each call beside our tier.

The scorer is a classmate's deterministic English/Spanish rule set. It sees only
the caller's own words (never what the desk said), as one cumulative transcript
with a revision that rises with each caller turn. Its 0-100 Human Attention
Index, band and open needs are shown to the operator; they never change a tier
or the queue order. The desk does not read anything back from it except for display.
"""
import re
import threading
import time
from datetime import datetime, timezone

from crisisfusion_scoring import ScoringPlugin

SYNC_INTERVAL_S = 1.0
UNSUPPORTED = "scorer covers English and Spanish only — human check"
# Our tiers and the scorer's policy bands, on one three-step scale.
TIER_LEVEL = {"immediate": 3, "priority": 2, "unknown": 2, "normal": 1}
BAND_LEVEL = {"IMMEDIATE_HUMAN": 3, "HUMAN_VERIFY": 2, "ROUTINE_HUMAN": 1, "AUTOMATION_ELIGIBLE": 1}
DISAGREE_RULE = ("Flagged when tier and band sit on different steps: immediate ↔ IMMEDIATE_HUMAN (80–100); "
                 "priority or unknown ↔ HUMAN_VERIFY (50–79); normal ↔ ROUTINE_HUMAN or AUTOMATION_ELIGIBLE (0–49).")
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯豈-﫿]")


def scorer_language(language: str, text: str) -> str:
    """The scorer accepts en, es, mixed or unknown; anything else, or CJK text, is unknown."""
    if _CJK.search(text):
        return "unknown"  # a mislabeled call must not get an English-rule number
    return language if language in ("en", "es") else "unknown"


def disagrees(tier: str, band: str | None) -> bool:
    return band is not None and TIER_LEVEL[tier] != BAND_LEVEL[band]


class ShadowScorer:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.engine = ScoringPlugin(":memory:")
        self.lock = threading.Lock()
        self.pushed: dict[str, int] = {}  # call_id -> revision sent
        self.opinions: dict[str, dict] = {}
        self.status = {"synced_at": None, "error": None, "calls": 0, "rule": DISAGREE_RULE}
        self._stop = threading.Event()
        self._thread = None

    def opinion(self, call_id: str) -> dict | None:
        return self.opinions.get(call_id)

    def sync_once(self):
        calls = self.snapshot()["calls"]
        with self.lock:
            rejected = []
            for call in calls:
                revision = len(call["transcript"])  # caller turns only; grows only when caller text changes
                if not revision or self.pushed.get(call["call_id"]) == revision:
                    continue
                text = "\n".join(call["transcript"])
                try:
                    self.engine.ingest({
                        "call_id": call["call_id"], "revision": revision, "text": text,
                        "language": scorer_language(call["language"], text),
                        "input_mode": "text" if call["origin"] in ("live", "phone") else "replay",
                        "timestamp": datetime.fromtimestamp(call["arrival"], timezone.utc).isoformat()})
                except ValueError as error:
                    rejected.append(f"{call['call_id']}: {error}")
                    continue
                self.pushed[call["call_id"]] = revision
            scored = self.engine.snapshot()
            needs: dict[str, list[str]] = {}
            for need in scored["needs"]:
                if need["unresolved"]:
                    needs.setdefault(need["call_id"], []).append(need["need_type"])
            tiers = {c["call_id"]: c["tier"] for c in calls}
            opinions = {}
            for row in scored["calls"]:
                call_id, assessment = row["call_id"], row.get("priority_assessment")
                if row["language"] not in ("en", "es"):
                    opinions[call_id] = {"supported": False, "score": None, "band": None, "needs": [],
                                         "disagree": False, "note": UNSUPPORTED}
                    continue
                band = assessment["category"] if assessment else None
                opinions[call_id] = {"supported": True, "score": assessment["score"] if assessment else None,
                                     "band": band, "needs": sorted(set(needs.get(call_id, []))),
                                     "disagree": call_id in tiers and disagrees(tiers[call_id], band),
                                     "note": "" if assessment else "no open need"}
            self.opinions = opinions
            self.status.update(synced_at=time.time(), calls=len(opinions),
                               error="; ".join(rejected) if rejected else None)
            if rejected:
                raise ValueError("Scorer rejected " + "; ".join(rejected))

    def reset(self):
        with self.lock:
            self.engine.close()
            self.engine = ScoringPlugin(":memory:")
            self.pushed.clear()
            self.opinions = {}

    def _run(self):
        while not self._stop.wait(SYNC_INTERVAL_S):
            try:
                self.sync_once()
            except Exception as error:
                # Surfaced in /state so the UI shows a stale second opinion instead of hiding it.
                self.status["error"] = f"{type(error).__name__}: {error}"

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="shadow-scorer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
