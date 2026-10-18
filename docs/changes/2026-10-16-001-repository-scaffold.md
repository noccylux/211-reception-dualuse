# Repository scaffold for the hackathon

* Type: ops
* Scope: `AGENTS.md`, `docs/`, `.claude/`, `.agents/`, `dualuse/`, `scripts/`, `tests/`, `pyproject.toml`

## Context

* The repository started as a copy of the autoalpha agent rules and
  launcher. The hackathon (Fri 2026-10-16 17:00 to Sun 2026-10-18 15:30 PT)
  forbids building before the problem reveal at Fri 18:00, so the scaffold
  holds only generic tooling and process.
* Corrections to the initial understanding, from the official sources in
  `docs/information/`: the problem changes through three scheduled twists
  (Fri 23:30, Sat 04:30, Sat 07:00), each answered within 6 hours, not a new
  problem every 8 hours; and the Devpost submission is due Sat 22:00, with
  Sunday reserved for demos, finalist pitches and awards.

## Decision

* Kept the WSL launcher, its self-test and the bare-Python
  guard hook; removed autoalpha-specific scripts, module tiers and the
  concept/contract design hierarchy, which are too heavy for 48 hours.
* Stack chosen by the user: FastAPI backend (also the webhook endpoint for
  Retell and Terminal49) and Streamlit demo UI, with the Anthropic SDK,
  Retell SDK, pandas, Plotly, pydeck and CUDA Torch preinstalled.
* Added hackathon process documents: event facts (`docs/hackathon.md`),
  problem and twist templates (`docs/problem/`), a twist-response procedure
  exposed as a skill, a submission checklist with the required AI-tool list,
  and a lighter change-record format.
* Added `scripts/check_keys.py` to verify partner API keys from `.env` with
  one read-only call each.

## Verification

* `uv lock` and `uv sync --frozen` with Python 3.14.7 succeeded; Torch
  2.14.1+cu132 reports CUDA available on the GPU.
* `scripts/check-launcher.sh` passed; `pytest`: 4 passed.
* Started both `.claude/launch.json` servers: `GET /health` returned
  `{"status":"ok"}` and the Streamlit page showed the API as ok.
* `scripts/check_keys.py` ran with no keys set; the authenticated calls for
  Anthropic, Retell and Terminal49 are not yet verified with real keys.
