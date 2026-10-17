# Architecture: 211 reception desk

Current behavior of the text reception demo on `worktree-comms-211-demo`,
updated Sat 2026-10-17 PT. This is a local prototype, not a connected telephone
or emergency dispatch system. Ordinary community assistance and disaster
surges use the same interview, queue and handoff path.

## Components and data flow

| Component | Responsibility |
|---|---|
| `dualuse/ui.py` | Caller conversation, operator seats, incident reports, audit history and labeled scenario simulation. Active panels refresh every two seconds. |
| `dualuse/reception.py` | Claude structured extraction plus one contextual follow-up question. Full role-labeled history is provided each turn. English offline mode uses keywords and a bounded question sequence. |
| `dualuse/extract.py` | Shared fields, deterministic tier mapping, English baseline and operator summary. |
| `dualuse/holdqueue.py` | Call lifecycle, ordering, reservations, history, human review tasks and synchronization. |
| `dualuse/storage.py` | Atomically commit the desk snapshot to SQLite. |
| `dualuse/api.py` | Validated HTTP boundary and single persistent desk. |
| `dualuse/triage.py`, `simulation.py`, `surge.py` | Existing queue policies and synthetic scenario comparison. |

Each caller message is saved before inference. The model receives prior caller
and assistant turns, but only caller words may support extracted evidence and
location. The provider output is schema-validated and the quoted evidence and
location are checked against caller text. These checks do not prove that a report
is true or that the classification is correct.

The model chooses a follow-up topic and question. The program announces queue,
recording and handoff facts only after the associated state transition succeeds.
Question content is guided by the prompt; medical, rescue and dispatch advice is
out of scope. This is not a validated safety-critical conversation system.

## Lifecycle and concurrency

`waiting -> connecting -> handed_off -> completed`

- Joining adds a welcome identifying the automated assistant and the current
  number ahead. Queue position is a snapshot, not a promised service time.
- A caller may disclose new facts throughout waiting; every turn updates fields
  and records any tier change with its supporting evidence.
- Claude requests run outside the desk lock. The operator can reserve a call
  immediately, including during inference. A call version invalidates replies
  after handoff, disconnect, mode change or reset.
- Reservation is atomic inside the single API process. One operator cannot hold
  two calls and two operators cannot reserve the same call.
- Confirmation completes transfer. Failure returns the call with its original
  arrival and information. The UI requires explicit confirmation; no telephony
  provider acknowledgement is connected yet.
- Caller hang-up and connection loss retain the conversation and reports.
  Disconnects, silent hang-ups and calls still marked immediate/unknown create
  callback-review tasks. A human records the disposition; no number is collected
  and no outbound call is placed in this text prototype.
- No-response events first ask for a check-in, then mark human attention. They
  do not classify silence as routine or remove the call. Events are simulated
  through UI/API controls, not an audio or elapsed-time detector.
- On restart, unfinished inference and pending transfers are flagged for review;
  pending transfers return to waiting. Confirmed transfers remain operator-held.

SQLite stores calls, dialogue, extraction, tier, status, reservations, handoffs,
departures and audit events. The database defaults to `.tmp/211-queue.sqlite3`.
Use one API process per database. The current snapshot store is sized for a small
local demo; multi-process dispatch, authentication, retention management and
production telephony recovery require further work.

## Ordering and incident reports

| Tier | Scheduling rank |
|---|---:|
| Immediate: reported life threat now | 0 |
| Priority: needs a person soon | 1 |
| Unknown: insufficient information | 1 |
| Normal: routine request | 2 |

FIFO applies inside a rank. A normal caller waiting 30 minutes receives rank 1
for scheduling, without changing the stored risk tier. This does not guarantee
an upper bound on wait during overload. Immediate danger is retained once flagged;
subsequent apparent de-escalation calls for human review and preserves the earlier
risk evidence in the audit trail. There is no arbitrary numeric urgency score.

Reports are associated by incident kind and an exact normalized stated location.
The grouping persists after handoff or disconnect and does not reduce any call's
priority. Matching is a candidate association, not geocoding or verified incident
identity. There is no automatic dispatch, verification or incident resolution.

## Failure behavior and limits

Model mode uses `claude-haiku-5-5`, a 20-second request timeout and no automatic
retries. A failure saves the message, displays an error and marks human review;
a non-immediate call becomes Unknown. Offline rules run only when explicitly
selected (or initially when no key exists). FIFO mode records messages without
classification or follow-up questions. Calls remain available to operators.

Each message is limited to 4,000 characters, with 32,000 total caller characters
per conversation. A second simultaneous turn on one call is rejected. The desk
is shared by all browser sessions, with no authentication; run on localhost.

## Evidence and next steps

Typed messages are live demo input; provided scenarios are team-written samples.
The simulator uses synthetic arrivals, handling/patience times and assumed error
rates. Its "model" curve does not call Claude. It is not a real-data evaluation.
No training or evaluation on the downloaded datasets has been added in this task.

Next: evaluate need extraction on the labeled disaster messages, separately
annotate urgency examples, then connect Retell voice, silence/disconnect events
and provider-confirmed human transfers to this lifecycle.

Reproducible startup and walkthrough: [README](../README.md).
Verification results: [change record](changes/2026-10-17-006-reception-agent.md).
