English · [中文](README.zh-CN.md)

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

Requirements: Python 3.14 and [uv](https://docs.astral.sh/uv/). From a clean
checkout, create the locked environment, copy `.env.example` to `.env` and fill
in `ANTHROPIC_API_KEY` (the other keys are optional), then start the API and the
UI in two terminals:

```bash
uv sync --frozen
uv run uvicorn dualuse.api:app --host 127.0.0.1 --port 8000
uv run streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Open <http://localhost:8501>. For an isolated demo alongside the original ports,
set `DUALUSE_QUEUE_DB` for the API and `DUALUSE_API_URL` for the UI, for example:

```bash
DUALUSE_QUEUE_DB=.tmp/reception-demo.sqlite3 uv run uvicorn dualuse.api:app --host 127.0.0.1 --port 8020
DUALUSE_API_URL=http://127.0.0.1:8020 uv run streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8521 --server.headless true
```

In PowerShell, set the variable first, for example `$env:DUALUSE_QUEUE_DB = ".tmp/reception-demo.sqlite3"`.
The `scripts/uv-run.sh` and `scripts/uv-run.ps1` launcher that the change
records mention is the authors' Windows + WSL equivalent of `uv run`; it needs
`DUALUSE_WSL_DISTRO` in `.env` and is not needed elsewhere.

To show the incident map to visitors through a tunnel, route the public
hostname's `/plugins/map/` path to the API and start both API and UI with
`DUALUSE_MAP_URL` set to the public URL, for example
`DUALUSE_MAP_URL=https://demo.211deskdemo.site uv run uvicorn ...`
([architecture](docs/architecture.md#failure-behavior-and-limits)).

Keep one API process per database: do not use multiple workers. `ANTHROPIC_API_KEY`
selects the Claude interview; the sidebar also offers explicitly labeled English
keyword mode and FIFO without interviewing. Model failures remain visible and
retain the caller's message for human review. They do not silently switch models.

## Demonstrate

Use two browser tabs, one on **Caller conversation**, one on **Operator desk**.
The caller page is a silent text line for callers who cannot speak safely.
The following is a team-written scenario, not a real call:

1. Join as a routine caller and ask about FEMA assistance. Join another caller
   and say "I see smoke coming from a building."
2. Answer the assistant's question with "It is at 12 Oak Street. I am outside."
   Then disclose "Someone on the second floor is shouting for help and cannot
   get out." In the operator desk, pick the call in **Caller details** to see
   the risk evidence, tier change and report. In **Call records** (a third tab
   works well), the intake checklist fills in as the caller answers, and the
   answers the latest message changed carry an orange mark.
3. A third caller can report smoke at the same address. **Incident reports**
   associates matching kind and location without downgrading any person's risk.
4. Reserve the next caller as `operator-1`. **Confirm human takeover**, or mark the
   transfer failed to return the call with its original arrival time. Reserving
   works during a model request; late replies cannot change a transferred call.
5. In **Reply to the caller**, type "This is the 211 operator. Is everyone out
   of the building?" Show the reply in the caller tab and answer in **Type a
   message to the operator**. Then select **Operator finished this call** to
   free the seat. **Call records** keeps the finished call's checklist and full
   conversation. Restart the
   API to verify persistence.
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
   Mixed or message content and Austin arrivals read the downloaded datasets
   described in [docs/datasets.md](docs/datasets.md); without them the desk
   shows "Dataset missing", so choose scripts content and even arrivals.
10. Scenario simulator: the measured-rates table shows the offline rules and
    Claude on recorded 2010 Haiti and Pakistan SMS and Hurricane Sandy posts
    (proxy labels, first message only, not 211 calls). Run the replay to compare
    assumed error rates with the tiers measured there, on the same simulated surge.

SQLite saves calls, conversations, events and review tasks to
`.tmp/211-queue.sqlite3` by default (`DUALUSE_QUEUE_DB` overrides it). Reset explicitly
clears this desk. There is no authentication: use only local demo data.

## Verify and interpret

```bash
uv run python -m pytest tests -q
```

Tests use isolated databases and no paid model calls; `tests/test_ui.py` drives
the Streamlit app with `AppTest` against the in-process API. The scenario
simulator uses synthetic calls with assumed error rates and, once the evaluation
has run, tier shares measured on recorded disaster messages with proxy labels
([evaluation](docs/evaluation.md)). Neither is 211 accuracy or a real queue
wait. Rerunning the evaluation replays cached Claude responses for free:

```bash
env -u ANTHROPIC_API_KEY uv run python scripts/evaluate_messages.py
```

Details: [architecture](docs/architecture.md), change records
[008](docs/changes/2026-10-17-008-reception-agent.md) and
[009](docs/changes/2026-10-17-009-reception-agent-design.md),
[event](docs/hackathon.md), [submission](docs/submission.md).
