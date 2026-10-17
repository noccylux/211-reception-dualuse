# Choose the Comms track and the hold-queue assistant

* Type: design
* Scope: `docs/problem/brief.md`, `docs/architecture.md`, `dualuse/`, `tests/`
* Related: [Twist 1 funding pathway](2026-10-17-004-twist-1-funding-pathway.md)

## Context

* Track 03 Communication asks how to tell who needs a person right now, what
  must never be automated, and what happens when someone does not pick up.
  211 LA's January 2025 wildfires after-action report shows the surge is
  real: on 2025-01-08, 7,815 contacts, 60.66% abandoned, 1 h 23 min average
  wait.
* The user's idea, refined with ChatGPT 6 Pro and Claude Code reviews on
  Fri 2026-10-16 night: an AI assistant for the hold queue that interviews
  waiting callers, tiers them, keeps FIFO inside a tier, never hangs up, and
  transfers with a summary the moment an operator is free.
* Existing products (Carbyne, Prepared, Aurelian) sit on 911 and PSAP
  non-emergency lines; automated calls into 911 are not accepted.

## Decision

* Seat: the overnight supervisor of a 211-type community and disaster
  assistance line. Decided by the user Sat 2026-10-17 00:40 PT. Rejected: a
  911 PSAP seat (crowded, legally heavier) and the brainstormed C1 Callback
  Ladder as the main build (kept as the escalation for callers who hang up).
* Four ordinal tiers (`IMMEDIATE`, `PRIORITY`, `UNKNOWN`, `NORMAL`), queue key
  `(rank, arrival time)`, `UNKNOWN` ranked with `PRIORITY`, an aging guard
  that promotes `NORMAL` after a maximum wait. No continuous score: it would
  invent precision the data cannot support.
* Invariants, listed in [architecture.md](../architecture.md): never hang
  up, never the final decision, immediate transfer, no autonomous contact
  with agencies, FIFO fallback when the model is down.
* Build order, set by the user Sat 2026-10-17 00:50 PT ("complete the whole
  demo, backend to frontend, by morning"): deterministic queue and
  discrete-event simulation first (no external dependency), then Claude
  extraction behind deterministic rules, then the API and the Streamlit
  supervisor board. The Retell voice agent waits for keys, a public tunnel
  and the Sat 10:30 PT Retell session. The LLM only extracts fields; rules
  decide.
* The first simulation inputs are a seeded synthetic surge with stated
  parameters, labeled as simulated. Austin APD arrival timestamps and Munro
  messages come later and are labeled by origin.

## Verification

Modules landed Sat 2026-10-17 between 01:00 and 02:00 PT on branch
`worktree-comms-211-demo` (worktree `.claude/worktrees/comms-211-demo`), each
written test-first:

* `bash scripts/uv-run.sh python -m pytest -q`: **70 passed** in WSL,
  Python 3.14 (triage 8, simulation 9, surge 10, extraction 14, hold queue
  12, API queue 13, plus the scaffold's 4).
* API and board started with the documented commands and exercised in the
  browser: a routine caller then a Spanish fire call; the tiered order put the
  fire call first while FIFO kept the routine caller first; the card showed
  source `model` (Claude `claude-haiku-5-5`, `ANTHROPIC_API_KEY` was set in
  `.env` by then), English fields, Spanish evidence quoted verbatim and the
  unknowns. The surge replay on the default scenario reported immediate-tier
  P95 wait 3.1 min against 11.6 min under FIFO, normal-tier P95 30.7 min
  against 15.6 min (the cost), 6 misses against 25 for the rules baseline.
  Simulated numbers from the stated parameters, not real calls.
* Not verified: the Retell voice path (not built); the model path's behavior
  on languages other than Spanish and English; any live-call latency.
* Observed and documented: with `--reload`, editing any `.py` file restarts
  the API and empties the in-memory queue.
