# 211 reception and hold-queue assistant

A local text demo for a community and disaster assistance line. A caller joins
an actual application queue and talks, in their own language, with an automated
reception assistant while waiting; the operator then gets the conversation,
evidence and summary. Claude writes the replies from editable playbooks and
extracts fields; code owns tiers, queue order, emergency referrals and handoff.
Line profiles cover Los Angeles 211 and a China 12345 hotline. English phone
calls can reach the desk through the separate Retell voice bridge
([docs/voice.md](docs/voice.md)); voice transfer to a person is not connected.

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
7. Languages: join and write "Mi mamá necesita oxígeno y se fue la luz hace dos
   horas." The assistant answers in Spanish; the operator card shows `es`.
8. Twist 2: in the sidebar switch **Line profile** to the 12345 hotline, join,
   and write "我家楼下被水淹了，我奶奶腿脚不方便，出不去，水还在涨". The welcome, the
   emergency line (110, 119, 120) and the replies are in Mandarin; the queue
   rules are unchanged. Switch back to Los Angeles afterwards.
9. Surge: on the operator desk open **Demo surge**, keep 20 callers, mixed
   content and Austin arrivals, and inject. Team-written scripts (simulated) and
   Munro disaster messages (recorded, labeled per call) fill the queue while
   life threats move to the top. The surge makes about 30 model calls.

SQLite saves calls, conversations, events and review tasks to
`.tmp/211-queue.sqlite3` by default (`DUALUSE_QUEUE_DB` overrides it). Reset explicitly
clears this desk. There is no authentication: use only local demo data.

## Verify and interpret

```powershell
.\scripts\uv-run.ps1 python -m pytest tests -q
```

Tests use isolated databases and no paid model calls; `tests/test_ui.py` drives
the Streamlit app with `AppTest` against the in-process API. The scenario
simulator still uses synthetic calls and assumed classifier error rates; it does
not measure Claude accuracy or real queue waits. A real-data evaluation is
separate work.

Details: [architecture](docs/architecture.md), change records
[008](docs/changes/2026-10-17-008-reception-agent.md) and
[009](docs/changes/2026-10-17-009-reception-agent-design.md),
[event](docs/hackathon.md), [submission](docs/submission.md).
