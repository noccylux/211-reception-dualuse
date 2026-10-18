# Public repository: local-only split and filtered mirror

* Type: ops
* Scope: `.gitignore`, `AGENTS.md`, `README.md`, `README.zh-CN.md`, `docs/README.md`, `docs/agents/documentation.md`, `docs/hackathon.md`, `docs/problem/brief.md`, `docs/changes/`, `scripts/uv-run.sh`, `scripts/uv-run.ps1`, `scripts/check-launcher.sh`, `pyproject.toml`, `uv.lock`, `.env.example`, `crisisfusion_map/README*.md`, `crisisfusion_scoring/README*.md`

## Context

* On Sat 2026-10-17 at about 19:10 PT the user asked to make the repository public without exposing secrets, machine details or agent-only tooling, while keeping the commit history readable, and to keep the authors' local tooling working unchanged.
* A scan of the working tree, all 64 commits and all branches found no API key, token or `.env` in the history. It found saved organizer pages and PDFs with people's photographs, email addresses and a participant-only document link under `docs/information/`; the authors' WSL distribution name, drive paths and GPU model in the environment rules, the launcher scripts and 17 change records; a Retell agent id in one change record; and the author's email addresses in commit metadata.
* GitHub cannot restrict a repository's history to collaborators. Rewriting the history of the private repository in place was rejected for the evening of the deadline: every clone and all 14 local worktrees would have to be rebuilt and GitHub keeps old commits reachable until support removes them.

## Decision

* Two repositories. The private `origin` keeps everything. The public repository is a filtered mirror of `main` rebuilt from a fresh clone with `git filter-repo`, which keeps every commit, message and date but drops the local-only paths from all commits and replaces the machine-specific strings. The procedure and the leak checks live only on the authors' machines, in the git-ignored `docs/local/`.
* Local-only layer in the working tree: `.claude/`, `.agents/`, `.codex/`, `docs/local/` and `docs/information/` are git-ignored and were removed from the index, not from disk. `docs/agents/environment.md` moved to `docs/local/environment.md`. `AGENTS.md` tells an agent to read that file when it exists and to use the generic `uv sync --frozen` and `uv run` steps when it does not, so a fresh clone needs nothing beyond `README.md`.
* The launcher scripts read the WSL distribution from `DUALUSE_WSL_DISTRO` (environment or `.env`) instead of a hardcoded name, and refuse to run without it. `.env.example` documents the variable as optional.
* The unused `torch` dependency and its CUDA-only package index were removed from `pyproject.toml` and `uv.lock`, so `uv sync --frozen` resolves on machines without that index.
* Redactions in tracked docs: organizer email removed from `docs/hackathon.md`; the Retell agent id removed from the voice bridge record; "WSL" replaced by "WSL" in change records; links to `docs/information/` replaced by text saying the sources are saved locally.
* READMEs are bilingual with English as the default: `README.md`, `docs/README.md`, `crisisfusion_map/README.md` and `crisisfusion_scoring/README.md` each have a `README.zh-CN.md` twin (the two plugin READMEs were Chinese before and are now translated to English). The documentation rule records this as the only translated files.

## Verification

* `bash scripts/check-launcher.sh` with the distribution read from `.env`: both checks passed. `scripts/uv-run.ps1 python -c ...` ran in WSL too.
* Full suite through the launcher: `python -m pytest tests -q`, **496 passed in 73.59 s**.
* `git grep` over the tracked tree for the distribution name, drive paths, email addresses and the agent id after the change: no matches outside `docs/local/`.
* Commit messages on all branches contain none of the replaced strings.
* Mirror build (private `main` to the filtered clone): the leak checks found nothing; one commit that only added a local note was pruned as empty; all commits carry the noreply author address.
* Clean-checkout check in the mirror clone with the generic README steps (`uv sync --frozen`, then the test suite): **495 passed, 1 failed**. The surge UI test asked for Austin arrivals, which read a downloaded dataset absent from a clone. The test now selects even arrivals (its subject is the origin label, not the arrival pattern) and passes here; the README says which demo options need the datasets. Rerun in the rebuilt mirror clone, same generic steps: **496 passed in 90.99 s**.
* Not done yet: the push to the public repository, which waits for the repository to be created on GitHub.
