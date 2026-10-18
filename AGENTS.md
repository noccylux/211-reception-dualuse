# AGENTS.md

Always-on rules for coding agents in this repository: our team's build for
the Dual-Use Hackathon (InnovateLA × USC Viterbi, Los Angeles, Fri 2026-10-16
17:00 to Sun 2026-10-18 15:30 PT). Event facts, deadlines and judging are in
[docs/hackathon.md](docs/hackathon.md); the problem and its twists are in
[docs/problem/](docs/problem/).

Task-specific rules live in `docs/agents/`. Read the matching file when its
row applies; do not work from memory.

| Rule file | Use when |
|---|---|
| [docs/agents/twist-response.md](docs/agents/twist-response.md) | A twist (problem change) arrives, or when deciding how a change serves a twist. |
| [docs/agents/change-records.md](docs/agents/change-records.md) | Before reporting completion of a task, to decide whether and how to record it. |
| [docs/agents/documentation.md](docs/agents/documentation.md) | Creating or editing Markdown under `docs/` or a README. |
| `docs/local/environment.md` (git-ignored) | Present only on the authors' machines. If it exists, read it first: it describes that machine's Python environment, launcher, servers and push procedure, and it overrides the generic steps below. If it does not exist, you are on a fresh clone: use the generic steps below and do not create the file. |

## Hackathon constraints

- Building starts only after the problem reveal (Fri 18:00 PT). Code written
  before then is generic tooling, never problem-specific.
- Every AI tool used is listed in the Devpost submission. Keep
  [docs/submission.md](docs/submission.md) current.
- Hard deadline: Devpost submission Sat 2026-10-17 22:00 PT, no extensions.
  Twist responses are submitted together with the final submission; the
  organizers lifted the six-hour limit (user report, Sat 2026-10-17 09:50 PT).
- Judging: dual-use fit (breaks ties), technical execution, feasibility and
  impact, adapting to twists, demo and pitch. The build must serve a civil
  use on an ordinary day and the same build, unchanged, in a crisis or
  contested setting. Prefer work that improves these scores.
- Judges score what runs. Keep `main` demo-able at all times: the API and UI
  start and the demo path works after every commit.

## Python environment

Generic steps, for any machine without `docs/local/environment.md`. Python
3.14 and [uv](https://docs.astral.sh/uv/) are required; the lock file is the
source of truth for versions.

```text
uv sync --frozen                      # create .venv from uv.lock, once
uv run python -m pytest tests -q      # every Python command goes through uv run
```

Run from the repository root. Never run bare `python`, `pytest` or `pip`
against some other interpreter: the tests and servers must see the locked
environment. Server commands are in [README.md](README.md). The
`scripts/uv-run.sh` and `scripts/uv-run.ps1` launcher is the authors'
Windows + WSL equivalent of `uv run`; it needs `DUALUSE_WSL_DISTRO` in `.env`
and is not required elsewhere.

## Layout

| Path | Holds |
|---|---|
| `dualuse/` | The build. `api.py` is the FastAPI backend and webhook endpoint, `ui.py` the Streamlit demo, `config.py` reads secrets from `.env`. |
| `crisisfusion_map/`, `crisisfusion_scoring/` | Vendored plugins (incident map, call scorer), each with its own README. |
| `tests/` | Tests mirroring `dualuse/` and `scripts/`. |
| `scripts/` | The WSL launcher, `check_keys.py` (verifies the API keys in `.env`), the evaluation and Retell setup scripts. |
| `docs/` | Event facts, problem and twist log, architecture, submission material and change records; see [docs/README.md](docs/README.md). |

Secrets live only in `.env` (git-ignored); `.env.example` lists the names.

## Engineering rules

Design
- Scope for 48 hours: build the smallest thing that demonstrates the idea
  end to end, then deepen it. Reuse existing code and libraries before
  writing new abstractions.
- No speculative generality: no hooks, options, wrappers or layers the demo
  does not need. Keep modules small and their interfaces narrow.
- For a consequential design choice, compare the viable approaches briefly
  (correctness, time to build, demo value) and state the tradeoff.

Errors
- Fail loudly. Do not add try/except, fallbacks or defaults whose effect is
  to hide a failure. In the UI, show an error instead of silently wrong data.
- Validate external inputs (partner APIs, uploads, user input) at the
  boundary.

Data honesty
- Never present fabricated data as real. Simulated, sample or recorded data
  is allowed for the demo, but is labeled as such in the UI and the docs.
- No hardcoded results in place of computation the demo claims to perform.

Verification
- Add focused tests for core logic. Test observable behavior.
- Before reporting a change complete or committing it, run `tests/` and say
  what ran and what passed. Never skip or weaken a failing test to pass.
- For UI or API changes, also start the server and exercise the changed path.
- Draw no performance conclusions from ordinary runs on a shared machine.

Scope and reporting
- Change only what the task needs, including callers, tests and docs.
  Report worthwhile follow-ups in one or two lines instead of doing them.
- Add a dependency only when it removes substantial work, and say why.
- Comments explain why or a non-obvious constraint. No change-log comments.
- Ask when uncertainty materially affects correctness, scope or the demo.
  Otherwise state the assumption and continue.
- When finished, report what changed, what was verified and how,
  assumptions made, and anything left undone.
- Commit or push only when the user asks.
