# Architecture

What the build is now. Status: scaffold only; nothing problem-specific is
built before the reveal (Fri 2026-10-16 18:00 PT). Update this document with
the code; link change records for rationale.

## Dual-use story

- Civil use: (after the reveal)
- Crisis use: (after the reveal)
- Why one unchanged build serves both: (after the reveal)

## Components

| Component | Path | Role |
|---|---|---|
| API | `dualuse/api.py` | FastAPI backend; endpoint for partner webhooks. Currently only `GET /health`. |
| Demo UI | `dualuse/ui.py` | Streamlit front end; calls the API at `DUALUSE_API_URL`. |
| Settings | `dualuse/config.py` | Loads `.env`; `require(name)` fails loudly on a missing secret. |

## Data sources

Every source and whether it is live, recorded or simulated. Simulated data
is labeled as such in the UI.

| Source | Live / recorded / simulated | Used for |
|---|---|---|

## Demo path

The exact click-through shown to judges, and how to start it from a clean
checkout.
