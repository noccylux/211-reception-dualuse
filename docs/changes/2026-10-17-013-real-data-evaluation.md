# Evaluation on recorded disaster messages, and measured tiers in the simulator

* Type: implementation
* Scope: new `scripts/evaluate_messages.py`, new `dualuse/evaluation.py`, `dualuse/surge.py`,
  `dualuse/api.py` (`/simulate`, new `GET /evaluation`), `dualuse/ui.py` (Scenario simulator,
  About, surge caption wording), new `docs/evaluation.md`, `docs/architecture.md`,
  `docs/README.md`, `README.md`, `docs/submission.md`, tests
* Related: [design 009](2026-10-17-009-reception-agent-design.md), section "P3: real-data
  simulation"

## Context

* The scenario simulator replayed assumed error rates only (Claude 5% misses, 10% false alarms;
  keyword rules 25% and 30%), and the About page said no real-data evaluation existed.
* No labeled 211 call data is available. The Munro disaster response messages (CC BY 4.0) are
  recorded messages (2010 Haiti and Pakistan SMS, Hurricane Sandy message-board posts) with
  category labels and the original text beside the English translation.

## Decision

* Evaluate the desk's first turn on the Munro test split only, direct messages: 1,069 rows,
  1,067 distinct (two Sandy posts are repeated verbatim; a repeated id with different content
  would stop the run). Proxy labels: `request == 1` needs a person (421), `request == 0` routine
  (646); `request == 1` with `search_and_rescue`, `medical_help` or `death` forms a
  closer-to-danger subset (83), reported separately. Sample: seed 7, 150 per class plus the whole
  subset, 355 messages.
* Run each message through a fresh desk (`HoldQueue`) rather than calling the classifiers
  directly, so the desk's facts, quote and location checks, tier rules and failure handling all
  apply: offline mode (`receive`, which wraps `classify_with_rules`) and model mode
  (`reception.model_turn`, `claude-haiku-5-5`), on the English translation and on the original.
  FIFO ranks nobody ahead; its rates hold by construction and are labeled so.
* Cache raw Claude responses by request (`data/processed/eval_messages_cache.jsonl`); identical
  concurrent requests reach the API once, and a rerun replays the same answers for free. API and
  network errors stop the run; an incomplete or malformed answer counts as a failed turn, ranked
  UNKNOWN and flagged as the live desk would.
* Report miss rate (needs a person ranked NORMAL), false-alarm rate (routine ranked IMMEDIATE or
  PRIORITY), routine ranked ahead of NORMAL (UNKNOWN included), subset misses, tier counts, review
  flags and failed turns, with 95% Wilson intervals.
* Simulator: two measured policies next to the assumed ones, on the same simulated calls. The
  brief asked for measured miss and false-alarm rates; the first results showed that two rates
  would misstate the measured desks, because UNKNOWN ranks with PRIORITY and few danger-proxy
  messages are ranked IMMEDIATE (keyword rules: 1 of 83). Measured policies therefore draw each
  simulated caller's tier from the tiers measured on its proxy class (IMMEDIATE from the subset,
  PRIORITY from the needs-a-person sample, NORMAL from the routine sample). The sliders keep the
  two-rate model for what-if questions.
* UI: the measured table carries its label (recorded 2010 Haiti and Pakistan SMS and Sandy posts,
  proxy labels, first message only, not 211 calls, not 211 accuracy); assumed bars are hatched;
  the headline metrics add immediate callers who hung up, since P95 waits count only callers who
  stayed; a caption warns that one replay has only a handful of immediate callers.
* Not done: Austin arrival timestamps in the simulator (optional in the brief); one day of police
  dispatch times would stand in for 211 arrivals. Skipped for scope.

## Verification

* Tests, Sat 2026-10-17 13:35 PT: `bash scripts/uv-run.sh python -m pytest tests -q`, 253 passed
  (main had 205). New: Wilson intervals against published values,
  metric definitions, sampling, checksum and duplicate handling, the response cache (replay,
  concurrency, corrupt line), the desk path in both modes, failure handling, the Markdown block,
  measured mixes in the simulator, `/simulate` and `/evaluation`, and the simulator page with and
  without an evaluation file. No test calls the API.
* Runs: the first run (13:00 to 13:20 PT) sent 691 Claude requests; it sampled one repeated
  message twice, so routine had 151 rows. After deduplication the second run sent 46 new requests
  and replayed the rest; a third run replayed everything (0 sent) with identical numbers. About
  740 requests in total, about $0.35 at list price.
* Results (English translation; [evaluation.md](../evaluation.md) has all rows): Claude misses
  46.0% (69/150; 38.2-54.0%) of needs-a-person messages, raises false alarms on 1.3% (2/150) of
  routine ones, ranks 46.7% of routine messages ahead of NORMAL (mostly UNKNOWN), and ranks 34.9%
  (29/83) of the rescue, medical or death subset NORMAL and 14 of 83 IMMEDIATE. The keyword rules
  rank 139 of 150 needs-a-person and 147 of 150 routine messages UNKNOWN. On the original text
  Claude's rates are similar (misses 43.0%); four turns hit the 1,600-token limit.
* Read-through of the 29 subset messages Claude ranked NORMAL: about 25 ask for information,
  supplies or services, or report deaths, without describing danger now. `core.md` lists "where
  to find water or a shelter" as a routine question, so supply requests read as routine.
* Browser, dev API 127.0.0.1:8060 and UI 8561 from this worktree (database
  `.tmp/eval-dev.sqlite3`): without the evaluation file the simulator warned and replayed the
  assumed policies only; with it, the labeled table, the replayed tier shares and five policies
  appeared. Default scenario, seed 7, English: the measured Claude policy left 2 of 7 immediate
  callers hanging up against 5 of 7 under FIFO, with P95 waits of 30.5 min (immediate), 18.6
  (priority) and 31.0 (normal) against 11.6, 12.9 and 15.6 under FIFO; the measured keyword rules
  stayed close to FIFO. One simulated draw, not a measurement.
* Not verified: multi-turn conversations, 211 calls, Spanish or Mandarin messages, and latency.
