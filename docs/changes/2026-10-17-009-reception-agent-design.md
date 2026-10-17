# Design: playbook reception agent, line profiles and live surge

* Type: design
* Scope: `dualuse/reception.py`, `dualuse/holdqueue.py`, `dualuse/extract.py`,
  `dualuse/api.py`, `dualuse/ui.py`, new `dualuse/playbooks/`,
  `dualuse/profiles.py`, `dualuse/live_surge.py`, `tests/`
* Related: [reception desk](2026-10-17-008-reception-agent.md),
  [track and idea](2026-10-17-005-track-and-idea.md), Twist 2 in
  `docs/problem/twists.md` (main checkout)

A plan, not current behavior. The user chose the approaches below in chat on
Sat 2026-10-17 09:55 PT; implementation follows in this order.

## Context

* User feedback, Sat 2026-10-17 09:40 PT: the assistant feels like fixed
  automation rather than a multi-turn agent. The user wants prompt- or
  skill-driven dialogue that guides callers to the needed facts and calms
  them, multiple languages, a batch of conversations that congests the live
  queue, and a simulation on real datasets. Handoff to an operator stays the
  first priority.
* Cause: `reception.SYSTEM` lets Claude return only one short question per
  turn; every other caller-facing line is fixed English text in
  `holdqueue.py`; offline mode has five fixed English questions.
* Twist 2 asks how the solution holds up in another country. The answer is a
  second line profile with the same queue rules.
* The review of Sat 2026-10-17 08:20-09:20 PT found safety defects to fix
  first (items under P0).
* Organizers lifted the six-hour twist response limit (reported by the user,
  Sat 2026-10-17 09:50 PT). All three twist responses go with the final
  submission.

## Decision

### P0: review fixes

* Operator desk: waiting-call expander labels drop the ticking wait time, so
  the 2-second refresh no longer collapses them.
* Life safety: when a call becomes IMMEDIATE, the desk itself tells the
  caller to contact the profile's emergency number (911 in LA). The welcome
  also says it. The validator accepts emergency referrals from the model.
* Validation never discards a turn: evidence quotes match after normalizing
  case, quotes and whitespace (also across turns); unverified quotes are
  dropped and flagged; a location is kept when all its tokens occur in the
  caller's words, otherwise dropped and flagged; a life threat without a
  verified quote stays IMMEDIATE with a review flag; a malformed question is
  replaced by the fixed question for its topic.
* Interrupted turns (reservation, hang-up, mode change, restart) flag the
  unprocessed caller message for review and raise NORMAL to UNKNOWN.
* Hang-ups of PRIORITY callers also create a callback review task.
* Offline keywords: restore `is inside`; match routine and hazard words on
  word boundaries (`fema` no longer matches `female`, `fire` no longer
  matches `fired`); keep `fire damage` as a routine phrase.

### P1: playbook agent (approach A)

* One structured Claude call per caller turn (`claude-haiku-5-5`). Output:
  `reply` in the caller's language, `language` and `language_code`,
  `distress` (`calm`, `worried`, `distressed` or `unknown`), `topic`, and the
  existing extraction fields. Rules in code still decide tier, order and
  handoff.
* The system prompt is the role and safety rules plus playbooks, one
  Markdown file each under `dualuse/playbooks/`: intake (situation, location,
  safety, need; acknowledge, then one question), calming (name the feeling,
  short sentences, only true reassurance), life safety (emergency number,
  brief, no rescue or medical instructions), waiting (keeps their place,
  invite updates) and handoff. The prompt is cached with `cache_control`.
* The conversation is sent as real turns (caller as `user`, assistant and
  desk lines as `assistant`). Each turn's desk facts (callers ahead in the
  active order, transfer state, profile, emergency number, flagged danger)
  go in a final mid-conversation `system` message, so the cached prefix
  stays stable. The model may restate only these facts.
* Desk-owned lines (welcome, emergency referral, handoff transitions) come
  from a localized table in `dualuse/profiles.py` for each profile language,
  with English as the fallback.
* Rejected: B, templates with model-filled slots, still reads as automation
  and needs templates per language; C, two calls per turn, doubles latency
  and cost. Anthropic API Skills need a code execution container, too slow
  for every caller turn; playbook files give the same editable behavior.

### P1: line profiles (Twist 2)

* `la-211`: English, Spanish and Mandarin; emergency number 911; US street
  addresses.
* `cn-12345`: a city 12345 citizen service hotline; Mandarin and English;
  emergency numbers 110 (police), 119 (fire) and 120 (ambulance); Chinese
  address order (district, road, number, compound). Verify these facts
  before the pitch.
* Tiers, queue policy and handoff are identical in both. The profile is
  chosen in the sidebar and stored on the desk and on each call.
* Offline mode stays English keywords. For other languages it keeps the call
  UNKNOWN with a review flag naming the detected script.

### P2: live surge injector

* `POST /demo/surge` adds a batch of callers to the live desk over a
  compressed span: team-written scripts in English, Spanish and Mandarin
  (labeled simulated, one to three caller lines each, the next line sent
  after the agent replies) and real messages from the Munro disaster
  messages test split (labeled recorded, one line each). Arrival offsets
  follow the Austin APD busiest-day pattern, time-compressed and labeled.
* Turns run through the normal `say()` path in a worker pool of four, so the
  operator desk shows interviews in progress while the queue grows.

### P3: real-data simulation

* Separate session (task card "Real-data evaluation for the 211 reception
  desk"): miss and false-alarm rates measured on Munro messages with proxy
  labels replace the simulator's assumed rates; Austin arrival timestamps.

## P0 verification, Sat 2026-10-17 10:00 PT

* Tests first: 27 new or changed tests failed for the intended reasons; a
  wildfire case was added with the word-boundary change. Then
  `bash scripts/uv-run.sh python -m pytest tests -q` gave 112 passed, no
  warnings. `tests/test_ui.py` drives `dualuse/ui.py` with Streamlit's
  `AppTest` against the real API in-process.
* Browser, model mode with `claude-haiku-5-5` (API on 127.0.0.1:8040, UI on
  127.0.0.1:8541, database `.tmp/dev-211.sqlite3`): the welcome said
  "Callers ahead of you: 0" and named 911; "My neighbor collapsed on the
  sidewalk and he's not breathing" (curly apostrophe) became IMMEDIATE, the
  desk told the caller to call 911, and Claude asked for the address; the
  operator-desk expander stayed open across refreshes.

## Verification plan

* Each P0 fix gets a failing test first; model behavior uses stub clients;
  tests make no paid calls.
* Manual: real Claude turns for paired English, Spanish and Mandarin
  requests; caller and operator views in the browser; a 30-caller surge.
* Unverified until run: Mandarin and Spanish quality, latency under surge,
  the 12345 hotline facts.
