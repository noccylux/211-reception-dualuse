# 211 reception and hold-queue assistant

A local text demo for a community and disaster assistance line. A caller joins
an actual application queue, talks to an automated reception assistant while
waiting, and passes to an operator with the conversation, evidence and summary.
Claude proposes contextual follow-up questions and extracts fields; code owns
queue order, recording and handoff. Telephone service is not connected.

## Run

Run from this checkout, using WSL and the shared `.venv_wsl` as described
in [the environment rules](docs/agents/environment.md). No new dependencies
are required by the reception upgrade. Two terminals:

```powershell
.\scripts\uv-run.ps1 uvicorn dualuse.api:app --host 127.0.0.1 --port 8000
.\scripts\uv-run.ps1 streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Open <http://localhost:8501>. For an isolated demo alongside the original ports:

```powershell
.\scripts\uv-run.ps1 env DUALUSE_QUEUE_DB=.tmp/reception-demo.sqlite3 uvicorn dualuse.api:app --host 127.0.0.1 --port 8020
.\scripts\uv-run.ps1 env DUALUSE_API_URL=http://127.0.0.1:8020 streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8521 --server.headless true
```

Keep one API process per database: do not use multiple workers. `ANTHROPIC_API_KEY`
selects the Claude interview; the sidebar also offers explicitly labeled English
keyword mode and FIFO without interviewing. Model failures remain visible and
retain the caller's message for human review. They do not silently switch models.

## Demonstrate

Use two browser tabs, one on **Caller conversation**, one on **Operator desk**.
The following is a team-written scenario, not a real call:

1. Join as a routine caller and ask about FEMA assistance. Join another caller
   and say "I see smoke coming from a building."
2. Answer the assistant's question with "It is at 12 Oak Street. I am outside."
   Then disclose "Someone on the second floor is shouting for help and cannot
   get out." See the risk evidence, tier change and report in the operator desk.
3. A third caller can report smoke at the same address. **Incident reports**
   associates matching kind and location without downgrading any person's risk.
4. Reserve the next caller as `operator-1`. Confirm human takeover, or mark the
   transfer failed to return the call with its original arrival time. Reserving
   works during a model request; late replies cannot change a transferred call.
5. Complete the operator-held call to free the seat. The transcript and summary
   remain in history. Restart the API to verify persistence.
6. Under **Demo call events**, send two no-response events, or disconnect a call.
   Review the resulting attention flag or callback task from the operator desk.
   These buttons simulate connection events; no silence detector or dialer exists.

SQLite saves calls, conversations, events and review tasks to
`.tmp/211-queue.sqlite3` by default (`DUALUSE_QUEUE_DB` overrides it). Reset explicitly
clears this desk. There is no authentication: use only local demo data.

## Verify and interpret

```powershell
.\scripts\uv-run.ps1 python -m pytest tests -q
```

Tests use isolated databases and no paid model calls. The scenario simulator
still uses synthetic calls and assumed classifier error rates. It does not
measure Claude accuracy, real queue waits or trained-model performance. Real-data
training/evaluation and Retell voice integration remain next steps.

Details: [architecture](docs/architecture.md), [change record](docs/changes/2026-10-17-006-reception-agent.md),
[event](docs/hackathon.md), [submission](docs/submission.md).
