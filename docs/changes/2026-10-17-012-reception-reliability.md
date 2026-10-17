# Reception and voice reliability fixes

* Type: implementation
* Scope: `dualuse/reception.py`, `holdqueue.py`, `voice_bridge.py` and regression tests
* Related: [Voice bridge](2026-10-17-010-voice-bridge.md)

## Context

Review of integration commit `4a837c5` reproduced three defects: a new unreadable
message could retain NORMAL priority, speech during reservation was discarded,
and a failed end-call request prevented later webhook retries from updating the desk.

## Decision

* An unsupported-language update marks the extraction as insufficient. Existing
  risk evidence still retains PRIORITY or IMMEDIATE.
* Reuse `/say` to save messages during reservation and operator handling without
  model inference. The operator sees the full conversation and a review flag;
  a failed transfer keeps the text. This avoids a separate buffering API or
  database schema change. Completed and departed calls still reject messages.
* Serialize end-call requests per voice call and mark completion only after the
  desk acknowledges it. Cancel disconnect compensation only after a successful
  webhook. No background retry framework or new dependency was added.
* Changes are in `claude/sharp-roentgen-001abb`. The running public services and
  their databases were not changed; integration into main and deployment remain separate.

## Verification

* Full `tests/` suite: **205 passed** through the root WSL launcher, with the
  integration worktree selected as the import and test directory. The 12 added
  cases cover unsupported-language updates, operator-held message persistence,
  buffered speech, transfer outcomes, 503s, timeouts, lost responses, duplicate
  end notifications and disconnect compensation after a failed webhook.
* Temporary localhost API and voice-bridge processes used an isolated SQLite
  database, offline rules and fake Retell credentials. HTTP and WebSocket checks
  passed for unreadable text, recording during reservation, failed-transfer
  return, signed duplicate end notifications and persisted conversation contents.
  The temporary servers were stopped after the check.
* No real Retell call, live model request, public deployment or map integration
  was performed in this task.
