# Persistent multi-turn reception for the 211 demo

* Type: implementation
* Scope: reception, hold queue, storage, API, UI and tests in the 211 worktree
* Related: [track choice](2026-10-17-005-track-and-idea.md)

## Context and decision

* The user requested a waiting-line assistant that gathers information over
  multiple turns, updates priority and retains reports through human handoff.
* Backed up commit `f257017` to remote branch
  `codex/backup-211-before-agent-20261017` before editing. The current work remains
  on `worktree-comms-211-demo`; main and the 911 checkout were not edited.
* Reused FastAPI, Streamlit, existing tiers and queue policies. Added standard
  library SQLite rather than a new service or dependency.
* Claude extracts fields and plans a contextual follow-up. Program state controls
  recording and transfer announcements. Inference runs outside the queue lock;
  call versions discard stale replies after operator intervention.
* Added explicit reserve/confirm/fail handoff, durable history, report association,
  silence events and manual callback review. Immediate risk is retained for human
  review; a duplicate report never automatically lowers someone's priority.
* Kept this iteration to a local text workflow. Voice, automatic callbacks,
  trained classifiers and real-data evaluation remain separate work.

## Verification

* Final existing and new tests: 83 passed, using WSL through
  the project launcher, isolated databases and no model API calls.
* Real Claude smoke check: a smoke report prompted a location question; a stated
  address prompted a safety question; a subsequent trapped-person disclosure
  changed the call to Immediate. These were team-written test inputs.
* Browser check at localhost:8521: contextual conversation, Immediate escalation,
  operator reservation, failed-transfer return and confirmed human takeover passed.
* Restarted the real API: three caller turns, the confirmed handoff and nine audit
  events recovered. HTTP checks also exercised two reports at one location,
  repeated silence events, disconnect and creation of one callback-review task.
* A Chinese evacuation/shelter message was classified Priority and received a
  Chinese location question through the final model path. This was a written
  smoke-test example, not a dataset evaluation.
* No claims of measured accuracy or response-time improvement.
