# The Dual-Use Hackathon

Our team's build for the [Dual-Use Hackathon](https://www.innovatelosangeles.com/dual-use)
(InnovateLA × USC Viterbi, Los Angeles, 2026-10-16 to 18). The problem is
revealed Fri 18:00 PT; until then this repository holds only the scaffold.

- Event facts and deadlines: [docs/hackathon.md](docs/hackathon.md)
- Problem and twists: [docs/problem/](docs/problem/)
- What we built: [docs/architecture.md](docs/architecture.md)
- Submission checklist: [docs/submission.md](docs/submission.md)

## Quickstart

Requires the WSL distribution `WSL` with uv; see
[docs/agents/environment.md](docs/agents/environment.md).

```bash
cp .env.example .env                               # then fill in API keys
bash scripts/uv-run.sh python scripts/check_keys.py
bash scripts/uv-run.sh python -m pytest
bash scripts/uv-run.sh uvicorn dualuse.api:app --reload --host 0.0.0.0 --port 8000
bash scripts/uv-run.sh streamlit run dualuse/ui.py --server.port 8501
```

The API serves on <http://localhost:8000> (docs at `/docs`), the demo UI on
<http://localhost:8501>.

## Stack

Python 3.14, FastAPI, Streamlit, Anthropic SDK, Retell SDK, pandas, Plotly,
pydeck, PyTorch (CUDA 13.2).
