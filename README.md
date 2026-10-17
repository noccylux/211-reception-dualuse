# The Dual-Use Hackathon

Our team's build for the [Dual-Use Hackathon](https://www.innovatelosangeles.com/dual-use)
(InnovateLA × USC Viterbi, Los Angeles, 2026-10-16 to 18): a hold-queue
assistant for an overloaded 211-type community and disaster line. While
callers wait for an operator, an assistant interviews them, Claude extracts
structured fields, deterministic rules put the callers who need a person now
ahead (FIFO inside a tier, unknown stays with priority, bounded delay for
everyone else), and the call transfers with a summary the moment an operator
is free. It never hangs up and never makes the final decision.

- Event facts and deadlines: [docs/hackathon.md](docs/hackathon.md)
- Problem and twists: [docs/problem/](docs/problem/)
- What we built and why: [docs/architecture.md](docs/architecture.md), [docs/changes/](docs/changes/)
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

The API serves on <http://localhost:8000> (docs at `/docs`), the supervisor
board on <http://localhost:8501>. With `ANTHROPIC_API_KEY` set the board
starts in model mode (Claude extracts fields, rules decide the tier); without
it, the keyword-rules baseline runs and the board says so. The "FIFO" mode is
the degraded path: classification off, today's order.

## Demo path

1. Live hold queue: let a routine caller join ("Is the 210 freeway open towards
   Pasadena?"), then a Spanish fire call ("Mi casa se está quemando y mi hijo
   está adentro."). The FIFO and tiered orders differ; the call card shows the
   extracted fields, the quoted evidence and what is still unknown.
2. "An operator is free": the head of the tiered queue hands off with the
   summary card.
3. Surge replay (simulated): the same synthetic surge under FIFO, keyword
   rules and model tiers, with the urgent tier's wait next to the normal
   tier's cost and the misses.

Every panel labels its data as live, recorded or simulated; the sample
utterances were written by the team.

## Stack

Python 3.14, FastAPI, Streamlit, Anthropic SDK (`claude-haiku-5-5` for
extraction), Retell SDK (voice agent, planned), pandas, Plotly.
