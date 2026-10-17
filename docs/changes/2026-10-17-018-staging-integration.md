# Staging integration while the campus demo stays on main

* Type: ops
* Scope: `codex/demo-integration-20261017`, evaluation merge resolution, repository documentation
* Related: [map and scorer](2026-10-17-014-profile-map-and-shadow-scorer.md), [desk fixes](2026-10-17-016-desk-tier-definitions-and-checks.md), [poster](2026-10-17-015-poster-and-devpost.md)

## Context

* On Sat 2026-10-17, the user reported a configured website replacing the temporary URL and was waiting for campus testers. They requested integration on a separate branch before any promotion to main after the campus demo.
* Main and origin/main were `d6a1b85`. The main checkout had an existing uncommitted `.claude/launch.json` change. Its files, services, public URL and deployment were left in place.

## Decision

* Create `codex/demo-integration-20261017` from main in a separate managed worktree. Keep all integration commits local; no push or merge to main in this task.
* Merge the committed snapshots below. The tier-fix and evaluation-enhancement tips were local commits not yet on their corresponding remote branches when origin was fetched.

| Source branch | Tip | Included work |
|---|---|---|
| `claude/map-scorer-integration-6fa440` | `f84d0f6` | Profile maps and shadow scorer; includes `feature/map-plugin` |
| `claude/admiring-antonelli-3eb3bf` | `313c77f` | Priority definitions, token budget, accent checks; includes `claude/beautiful-davinci-e27ed8` and the recorded-message evaluation |
| `claude/eval-prompt-tuning` | `f8c399b` | Train/validation/test selection, model comparison and separate caches/output files |
| `claude/beautiful-morse-d174d7` | `7c7aea8` | Poster, final twist drafts and Devpost text |

* Leave `claude/demo-911-psap-0a5190` out: it is the older alternative 911 implementation, not an additive change to the current reception desk. The voice bridge, reception reliability branch and `worktree-comms-211-demo` were already ancestors of main. The remote backup is also already contained in main.
* Resolve architecture and documentation-index conflicts by retaining both features. Reconcile the overlapping evaluation script: preserve per-model outputs/caches, missing-translation handling and text counts. Retain both sets of behavior tests and rename a duplicate test function so neither is silently hidden. Adapt the validation-run fixture to the merged client signature and output filename.
* Rename the duplicate change-record number for the Twist 2 response from 014 to 017 and update links. Keep the map record as 014. Update current architecture, evaluation commands, submission status and AI-tool attribution. Poster artwork and exports stay as supplied by the poster branch.

## Verification

* Reuse the existing WSL `.venv_wsl` through the launcher with `PYTHONPATH=.` so the worktree's code is tested. Copy the Austin input, Munro CSVs and saved evaluation into this checkout's ignored `data/`; do not share its database or write into the live checkout's datasets.
* First map suite: 386 passed, one UI surge test failed because the new checkout lacked the local Austin data selected by the UI default. After copying that input, 387 passed. Subsequent integration suites: 447 passed after the desk/evaluation merge, 452 passed after the evaluation-script merge.
* Final full suite: `bash scripts/uv-run.sh env PYTHONPATH=. python -m pytest tests -q` — 452 passed in 74.96 s. This is a functional check, not a performance benchmark.
* Start a separate rules-mode API at `127.0.0.1:8088` using `.tmp/integration-smoke.sqlite3`, and UI at `127.0.0.1:8588`. Both health checks succeeded. Restart only this API after the code merge.
* HTTP checks: replayed LA coordinates appeared inside the LA map; after changing the test desk to `cn-12345`, replayed Beijing coordinates were marked outside Shanghai's example service area. Map and scorer reported no sync errors. `GET /evaluation` loaded the recorded 14:28 PT result; `POST /simulate` returned FIFO, assumed keyword/model and measured keyword/model policies. A malformed manual request was rejected with 422 before correcting its field names.
* Browser checks against these isolated servers: caller page loaded; Scenario simulator showed the saved evaluation and completed Run the replay; Incident map displayed the Shanghai example scope and loaded its map iframe. Tests also exercise UI actions and the voice-bridge contracts.
* Not verified here: campus-network access, the new public website, a new live Claude evaluation, real Retell calls or external map feeds/geocoders. The inherited map record notes the LA boundary provenance checksum discrepancy; resolve that before relying on that checksum for provenance. The saved evaluation is copied historical evidence, not a new model run.

## Promotion gate

* Wait for the user to confirm campus testing and the demonstration have finished before touching main or switching the public deployment. Then verify main has not advanced, rerun required checks against the intended merge, and deliberately switch the running services. Git integration and deployment are separate steps.
