"""HTTP service: the demo's backend and the endpoint for partner webhooks (Retell, Terminal49).

Run: bash scripts/uv-run.sh uvicorn dualuse.api:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI

app = FastAPI(title="Dual-Use Hackathon")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
