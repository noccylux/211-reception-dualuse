English · [中文](README.zh-CN.md)

# Standalone call scorer · crisisfusion-scoring 1.0.0

This is a standalone plugin that can be dropped into another Python / web host. It provides deterministic text extraction, a 0–100 human-attention index per call, open needs, revision history, deduplication, a queue and an audit trail of human actions; it ships with a lightweight UI that can be embedded through an iframe. **It does not depend on the original CrisisFusion project, the map plugin, the voice plugin or any API key.**

## Installation and standalone run

Requires Python 3.11+. Install into the host's virtual environment, using one of the following:

```powershell
# 安装打包的 wheel（把路径换成实际解压路径）
python -m pip install .\wheels\crisisfusion_scoring-1.0.0-py3-none-any.whl

# 或在本目录从源码安装
python -m pip install .

python -m crisisfusion_scoring --host 127.0.0.1 --port 8811 --db work/scoring.sqlite3
```

Open <http://127.0.0.1:8811/>. Press Ctrl+C to stop the process. `--db` is the path of this plugin's own database; the directory is created on demand, and `:memory:` suits throwaway testing. The source directory and the database can live in different places. Do not pass this plugin a database that the original system or another plugin is using.

Runtime dependencies are FastAPI and Uvicorn; the wheel itself does not bundle these third-party packages, so the first pip install needs them already present in the environment or downloadable from the package index. All scoring runs locally.

## Option 1: Call from Python directly

```python
from crisisfusion_scoring import ScoringPlugin, extract_call, get_policy

with ScoringPlugin("work/scoring.sqlite3") as scorer:
    result = scorer.ingest({
        "call_id": "call-001",
        "revision": 1,
        "text": "I am trapped in a fire.",
        "language": "en",
        "location": {"label": "123 Main St, Los Angeles, CA"},
    })
    print(result["call"]["priority_assessment"])
    print(scorer.snapshot()["queue_calls"])

print(extract_call("Library hours please.", language="en"))
print(get_policy())
```

Public entry points: `ScoringPlugin`, the compatible `Engine`, `extract_call`, `assess_call`, `get_policy`, `create_app`. `ScoringPlugin` is the recommended way to manage the full lifecycle; `Engine` is equivalent to the original, mature lifecycle implementation. The underlying pure function `assess_call(call, needs, *, as_of, wait_by_need, overdue_after_seconds=120)` works on existing evidence and need structures and does not accept arbitrary model scores as a substitute for the rules. Importing the package or the CLI never creates a database or starts a server; state is created only when the plugin is instantiated or `create_app` is called.

Each update to the same `call_id` uses a higher positive integer `revision`; `text` carries the caller's **cumulative transcript**. Different content under the same revision is rejected; redelivering the same event does not create duplicate needs. `event_id` may be supplied by the host; the same event ID must not stand for different content. A correction or a harmless new sentence does not automatically resolve an earlier danger need; that requires an explicit human action.

## Option 2: Mount into an existing FastAPI host

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from crisisfusion_scoring import create_app

scoring = create_app("work/scoring.sqlite3")

@asynccontextmanager
async def lifespan(app):
    yield
    scoring.state.plugin.close()

app = FastAPI(lifespan=lifespan)
app.mount("/plugins/scoring", scoring)
```

Embedding in a host page:

```html
<iframe src="/plugins/scoring/" title="通话打分器"
        style="width:100%;height:900px;border:0"></iframe>
```

The UI's scripts, styles and API all use relative URLs, so any mount prefix works; keep the trailing `/` on the entry URL. Mounting a sub-application does not run its lifespan automatically, so the host should call `scoring.state.plugin.close()` when it shuts down. Do not close the same instance more than once. The UI does not depend on the host's navigation or DOM; after the host writes data, click "Refresh" to see the latest queue.

By default only the Hosts `127.0.0.1`, `localhost` and `::1` are accepted. A production host can pass `allowed_hosts=["your-host.example"]`; this is only a Host allowlist and **provides no accounts, roles, TLS or user isolation**. Place the plugin behind the host's existing authentication and authorization; do not expose this demo instance directly to the internet. For multi-tenancy, the host isolates instances and databases.

## Option 3: Hosts in other languages via HTTP

Node, Java, .NET and other hosts can start it as a local sub-service or mount it through a same-origin reverse proxy. The browser cannot write cross-origin directly; the host backend should make the calls, or use a same-origin proxy. Even when called from the backend, write requests must carry the token.

1. GET `/api/scoring/status` and read `csrf_token`, `csrf_header` and `store_id`.
2. On POST requests set `Content-Type: application/json` and `X-CrisisFusion-Scoring: <token>`.
3. The browser's `Origin` must match the scheme, hostname and port of the actual request; the mount path is not part of the Origin. Plain backend requests may omit Origin. The token changes after a restart; just read it again.

`store_id` is a UUID stored inside this plugin's database (`plugin.store_id` in Python); it stays the same across restarts of the same database and changes when a new database is created or `ScoringPlugin.reset()` is called. A reliable relay should bind its consumption cursor to the source event stream, the target URL and this consumer identity together. When the identity changes, stop and let the host decide from which event to re-import; the old cursor must not be reused to skip history. An ordinary file backup keeps the original identity; rolling back to an older backup of the same identity still requires the host to roll back or rebuild its cursor in step.

Example:

```python
import httpx

with httpx.Client(base_url="http://127.0.0.1:8811") as client:
    status = client.get("/api/scoring/status").json()
    headers = {status["csrf_header"]: status["csrf_token"]}
    response = client.post("/api/scoring/calls", headers=headers, json={
        "call_id": "call-001", "revision": 1,
        "text": "I am trapped in a fire.", "language": "en",
        "event_id": "caller-final-001", "input_mode": "text"
    })
    response.raise_for_status()
    result = response.json()
    print(result["call"]["priority_assessment"]["score"])  # 初始 80
```

| Method and relative path | Input / returns |
|---|---|
| GET `/health` | Plugin, API, extraction-rule and scoring-rule versions |
| GET `/api/scoring/status` | CSRF token, header name, persistent `store_id`, whether a key is required |
| GET `/api/scoring/policy` | The score bands, parameters and constraints actually in effect |
| POST `/api/scoring/calls` | Call JSON; returns `call`, `incident`, `needs`, `alerts`, `duplicate` |
| GET `/api/scoring/state` | `calls`, `needs`, `queue_calls`, `audit`, rules and metrics |
| GET `/api/scoring/calls/{call_id}/priority` | `assessment`, `revisions`, all `needs` of that call |
| POST `/api/scoring/needs/{need_id}/actions` | Explicit human action with actor, reason and optional event ID |
| POST `/api/scoring/settings` | Known settings fields, e.g. `{"available_agents": 2}` |
| POST `/api/scoring/recompute` | `{}` or `{"call_id":"call-001"}`; recomputes from stored evidence |
| GET `/api/scoring/metrics` | Locally observable metrics; the real call-handling success rate stays null |

Accepted call fields: `call_id`, `text` (at most 20000 characters), `language` (`en/es/mixed/unknown`), `location` (may contain `label/lat/lon/source`), `timestamp` (optional ISO time), `revision`, `event_id`, `input_mode` (`text/replay/simulated_voice/browser_voice`), `speaker`. Any other inference or "ground truth" fields are rejected. Chinese should be set to `unknown` and needs human review. When feeding real voice, send only the caller's final transcript; the host must not submit what the agent itself said as caller evidence.

Excerpt of a typical scoring output:

```json
{
  "call_id": "call-001",
  "score": 80,
  "category": "IMMEDIATE_HUMAN",
  "band": {"min": 80, "max": 100},
  "policy_version": "human-attention-2026-10-17-v1",
  "safety_floor_applied": false
}
```

The full `priority_assessment` also contains `components`, the verbatim evidence sentences, rule IDs, revision number, time, uncertainty, open need IDs, queue eligibility, wait time, overdue state and manual ordering records. Once everything is resolved, `assessment` is `null`; history is not lost.

Human resolution of a need:

```json
{"action":"resolve","actor":"operator-17","note":"已与来电者核实此项需求已经解决","event_id":"review-001"}
```

Human escalation:

```json
{"action":"escalate","actor":"operator-17","note":"核实到当前受困风险","target_category":"IMMEDIATE_HUMAN"}
```

Manual ordering within a category: `{"action":"override","actor":"operator-17","note":"人工排序依据","manual_order":-1}`. `manual_order` only takes effect within the current category; it cannot place a lower-priority call ahead of a higher-priority one.

The retained simulated call-handling actions are `request_transfer` → `simulate_dial` → `simulate_bridge`, plus `simulate_no_answer`, `simulate_failure`, `interrupted`, `request_callback`, `callback_no_answer`, `callback_connected` and `confirm_incident`. They exist to exercise the open-need and queue lifecycle and **do not dial, transfer or dispatch anyone**; the voice plugin and the telephony carrier are integrated separately by the host.

## Scoring and limitations

| Category | Score band | Meaning |
|---|---|---|
| IMMEDIATE_HUMAN | 80–100 | A rule for current explicit danger / entrapment etc. fired; immediate human attention |
| HUMAN_VERIFY | 50–79 | Danger cues, contradictions, unknown semantics etc. need human verification |
| ROUTINE_HUMAN | 20–49 | Routine human request |
| AUTOMATION_ELIGIBLE | 0–19 | The whole text matches an allowed service intent with no unexplained content |

The score is first constrained by the hard category, then adds +1 per minute of waiting (at most +15) and +5 per follow-up item, and is capped within its category. The queue is still ordered by category, explicit manual order within a category, longest cumulative wait, then stable ID; a single floating-point "risk probability" is never the sole sort key. A missing address, language identity, staff shortage or repeated reports are never used to reduce a danger priority.

This version migrates the scoring, extraction and lifecycle code from v0.5; the rule versions remain `prototype-2026-10-17-v4.1` / `human-attention-2026-10-17-v1`. It is a limited English/Spanish rule prototype, not a system certified against clinical or dispatch standards. The unit tests prove the behavior of the covered cases; they do not represent recognition accuracy on real calls, and no fabricated accuracy or mortality risk is reported.

SQLite stores the original text, revisions, locations, needs and audit records; it stores no audio and calls no external services. Data retention, access control, backup and deletion policies are configured by the host. The `ScoringPlugin` Python API is a trusted-host interface with no HTTP token check; do not turn untrusted input into arbitrary Python calls.

Each database is owned by **a single process / a single active Engine instance**. The in-process RLock supports concurrent calls, but there is no cross-process state merging; do not share the same file across multiple Uvicorn workers or multiple plugin instances. Scaling to multiple processes requires a host-side state service, not copies of the local database connection.

## Verification and rebuild

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build --wheel
```

The tests cover the original scoring arithmetic and evidence, retention of open needs, revision/event deduplication, concurrent persistence, human escalation and the queue, disconnect/callback simulation, cross-origin rejection, CSRF, different mount prefixes, instance isolation and import side-effect freedom. The machine-readable plugin entry is in the package's `plugin.json`. This plugin does not import the evaluation labels, the map, the voice plugin or the host's `app` package.
