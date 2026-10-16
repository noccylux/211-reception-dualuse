# AGENTS.md

Always-on rules for coding agents in this repository: our team's build for
the Dual-Use Hackathon (InnovateLA × USC Viterbi, Los Angeles, Fri 2026-10-16
17:00 to Sun 2026-10-18 15:30 PT). Event facts, deadlines and judging are in
[docs/hackathon.md](docs/hackathon.md); the problem and its twists are in
[docs/problem/](docs/problem/).

Task-specific rules live in `docs/agents/` and are exposed as skills (Claude
Code: `.claude/skills/`, Codex: `.agents/skills/`) so they load only when
needed. Invoke the matching skill or read the file; do not work from memory.

| Rule file | Use when |
|---|---|
| [docs/agents/twist-response.md](docs/agents/twist-response.md) | A twist (problem change) arrives, or when deciding how a change serves a twist. |
| [docs/agents/change-records.md](docs/agents/change-records.md) | Before reporting completion of a task, to decide whether and how to record it. |
| [docs/agents/documentation.md](docs/agents/documentation.md) | Creating or editing Markdown under `docs/` or a README. |
| [docs/agents/environment.md](docs/agents/environment.md) | Adding dependencies, running servers, diagnosing the launcher, or checking CUDA. |

## Hackathon constraints

- Building starts only after the problem reveal (Fri 18:00 PT). Code written
  before then is generic tooling, never problem-specific.
- Every AI tool used is listed in the Devpost submission. Keep
  [docs/submission.md](docs/submission.md) current.
- Hard deadline: Devpost submission Sat 2026-10-17 22:00 PT, no extensions.
  Each twist must be answered within 6 hours on the portal.
- Judging: dual-use fit (breaks ties), technical execution, feasibility and
  impact, adapting to twists, demo and pitch. The build must serve a civil
  use on an ordinary day and the same build, unchanged, in a crisis or
  contested setting. Prefer work that improves these scores.
- Judges score what runs. Keep `main` demo-able at all times: the API and UI
  start and the demo path works after every commit.

## Python environment

Every Python command runs in the WSL distribution `WSL`, in the
project's `.venv_wsl` (Python 3.14), through the launcher. Never run bare
`python`, `pytest`, `pip`, `uv`, `streamlit` or `uvicorn`, the Windows Conda
environment, or `.venv_wsl\Scripts`. In Claude Code the PreToolUse hook
`.claude/hooks/block-bare-python.sh` blocks such Bash commands.

```text
bash scripts/uv-run.sh python -m pytest            # Git Bash or WSL
.\scripts\uv-run.ps1 python -m pytest              # PowerShell 7.3+ on Windows
```

Run from the repository root. The launcher uses the existing environment and
never creates, repairs or syncs it. Dependency sync, servers and CUDA checks
are in `docs/agents/environment.md`.

## Layout

| Path | Holds |
|---|---|
| `dualuse/` | The build. `api.py` is the FastAPI backend and webhook endpoint, `ui.py` the Streamlit demo, `config.py` reads secrets from `.env`. |
| `tests/` | Tests mirroring `dualuse/` and `scripts/`. |
| `scripts/` | Launcher (`uv-run.sh`, `uv-run.ps1`, `check-launcher.sh`) and `check_keys.py`, which verifies the API keys in `.env`. |
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
- The workstation is shared with other GPU/CPU workloads; draw no
  performance conclusions from ordinary runs. Before treating an OOM or
  slowdown as a defect, check `nvidia-smi` for other processes.

Scope and reporting
- Change only what the task needs, including callers, tests and docs.
  Report worthwhile follow-ups in one or two lines instead of doing them.
- Add a dependency only when it removes substantial work, and say why.
- Comments explain why or a non-obvious constraint. No change-log comments.
- Ask when uncertainty materially affects correctness, scope or the demo.
  Otherwise state the assumption and continue.
- When finished, report what changed, what was verified and how,
  assumptions made, and anything left undone.

## Git commit and push authorization

* The user is authorized to upload code for this project to https://github.com/noccylux/TheDualUseHackathon.git.
* When the user asks to "commit and upload," "push," or uses equivalent wording, you may stage all non-ignored changes, create a commit, and perform a normal push to the current branch of this repository without asking for confirmation again.
* Before pushing, verify the remote repository URL. If the remote URL has changed, ask for confirmation again.
* This authorization does not include force pushes, deletion of remote branches, or rewriting remote history.
* If the user only asks for code changes, do not automatically commit or push.
