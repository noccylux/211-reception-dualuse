# Architecture

What the build is now and the design it is growing into. Status: first
complete demo built Sat 2026-10-17 between 01:00 and 02:00 PT on branch
`worktree-comms-211-demo`: queue policies, simulation, Claude extraction behind
rules, the API and the Streamlit supervisor board. The Retell voice agent is
not built yet.
Rationale is in [changes/2026-10-17-005-track-and-idea.md](changes/2026-10-17-005-track-and-idea.md);
the problem and track text are in [problem/brief.md](problem/brief.md).

## Dual-use story

- The seat: the overnight supervisor of a 211-type community and disaster
  assistance line. Not a 911 PSAP.
- Civil use, the ordinary Tuesday: callers asking about housing, food,
  utility and benefits help wait in the hold queue. The assistant talks to
  them while they wait, records the need, and hands the operator a summary.
  Customer: a 211 operator or a community service center that already runs
  the line.
- Crisis use: a wildfire or earthquake surge. 211 LA's after-action report
  for the January 2025 wildfires lists, for 2025-01-08, 7,815 contacts
  offered, 60.66% abandoned and an average wait of 1 h 23 min. The same
  build, unchanged, keeps talking to the queue, puts the people who need a
  person now ahead, and hands off with a summary.
- Why one build serves both: the interview, the extraction and the queue
  rules are identical; only the call volume and the incident context change.
  A second line profile, an installation emergency communications line,
  shows the defense end user named in the Twist 1 response.
- Response ladder: watch (incident clusters formed from the summaries), ask
  (the interview while waiting), hand to a person (the transfer). Nothing
  above those rungs.

## What is never automated

These are product invariants; the UI shows them as a checklist.

- The assistant never ends a call. A caller leaves the queue only by being
  served or by choosing to hang up.
- It never tells a caller they are not urgent and never makes the final
  decision. It orders the hold queue; the operator decides.
- When an operator is free, the head of the queue transfers at once, even
  while the assistant is mid-sentence.
- Insufficient or conflicting information is ordered as priority, never as
  normal.
- A normal-tier caller is promoted after `max_normal_wait` (the aging guard),
  so the extra delay reordering can impose on anyone is bounded.
- It never contacts outside agencies on its own. The supervisor presses that
  button; the assistant drafts the content. With no operator seated, a
  life-threatening case pages the on-call human and the caller is told to
  call 911.
- If the model or the network is unavailable, the queue is plain FIFO,
  which is today's behavior.

## Tiers

Ordinal tiers, no continuous score. The queue key is `(rank, arrival time)`.

| Tier | Meaning | Rank |
|---|---|---|
| `IMMEDIATE` | Life-threatening now: trapped, fire at the location, medical emergency. On a 211 line this also means "tell the caller to call 911". | 0 |
| `PRIORITY` | Urgent, not life-threatening: an evacuee without shelter tonight, medication running out, a missing person. | 1 |
| `UNKNOWN` | Not enough information yet; every call starts here. | 1 |
| `NORMAL` | Information, non-urgent resource requests, recovery and financial aid, wrong numbers. | 2 |

## Components

| Component | Path | Role | Status |
|---|---|---|---|
| Tiers and queue policies | `dualuse/triage.py` | `Tier`, the FIFO policy and the tiered policy with the aging guard | done, tested |
| Simulation | `dualuse/simulation.py` | Discrete-event model: arrivals, operators, service times, caller patience, decision delay; metrics per true tier | done, tested |
| Surge scenarios | `dualuse/surge.py` | Seeded, labeled synthetic surge from stated parameters; the three-policy comparison | done, tested |
| Extraction | `dualuse/extract.py` | `classify_with_model` (Claude `claude-haiku-5-5`, structured output into `Extraction`), `classify_with_rules` (keyword baseline), `fields_to_tier` (the rules that decide), `handoff_summary` | done; rules tested, the model path checked by hand in the board |
| Live hold queue | `dualuse/holdqueue.py` | Who waits, what they said, both orders, operator handoff, caller hang-up, location clusters | done, tested |
| API | `dualuse/api.py` | `/state`, `/calls`, `/calls/{id}/say`, `/calls/{id}/hangup`, `/operator/free`, `/mode`, `/reset`, `/simulate`, `/samples`; in-memory, one queue per process | done, tested |
| Supervisor board | `dualuse/ui.py` | Live tab (join, both orders, call cards, handoff card, clusters), surge replay tab (three policies, P95 chart, cost), data provenance tab; mode switch and invariants in the sidebar | done, checked in the browser |
| Voice agent | Retell inbound agent; webhooks in `dualuse/api.py` | Interviews the caller during the hold; warm transfer with a whisper summary when told the operator is free | planned |
| Sample utterances | `dualuse/samples.py` | Written by the team; labeled as simulated callers in the board | done |
| Settings | `dualuse/config.py` | Loads `.env`; `require(name)` fails loudly on a missing secret | done |

## Data sources

Every source and whether it is live, recorded or simulated. Simulated data
is labeled as such in the UI.

| Source | Live / recorded / simulated | Used for |
|---|---|---|
| Synthetic surge (`dualuse/surge.py`) | simulated, labeled | Simulation inputs: arrivals, service times, patience, true tiers |
| 211 LA January 2025 wildfires after-action report, Appendix D | recorded, daily aggregates | Scenario parameters: offered volume, handle time, abandonment reference |
| Austin APD 911 Calls for Service 2023 to 2026 ([datasets.md](datasets.md)) | recorded | Planned: arrival timestamps and priority mix, labeled as Austin police dispatch records |
| Munro disaster response messages | recorded | Planned: extraction evaluation with proxy tiers; the `original` column for other languages |
| spikecodes 911 transcripts | recorded, edited by the publisher | Planned: demo utterances only, never evaluation |
| Retell calls | live | Planned: the live demo call |

## Evaluation

The simulation runs the same arrivals, operators, service times and patience
under three policies: FIFO, keyword rules with FIFO inside a tier, and the
model's tiers with FIFO inside a tier. It reports, per true tier, wait P50,
P95 and mean, abandonment and the number served; the share of calls in each
assigned tier; and misses (a true `IMMEDIATE` or `PRIORITY` call assigned
`NORMAL`). Before `arrival + decision_delay` a call is `UNKNOWN`. Oracle
tiers give the upper bound; a confusion matrix gives the realistic case.
Reordering only redistributes waiting time, so the normal tier's P95 is
reported next to the gains.

## Demo path

Start from a clean checkout (WSL launcher, see the README):

```text
bash scripts/uv-run.sh uvicorn dualuse.api:app --reload --host 0.0.0.0 --port 8000
bash scripts/uv-run.sh streamlit run dualuse/ui.py --server.port 8501
```

Click-through, checked in the browser Sat 2026-10-17 01:20 PT:

1. Live hold queue: a routine caller joins ("Is the 210 freeway open towards
   Pasadena?"), then a Spanish fire call ("Mi casa se está quemando y mi hijo
   está adentro."). Under FIFO the routine caller stays first; under the tiered
   order the fire call is first. The card shows source `model`, the fields in
   English, the evidence quoted in Spanish, and the unknowns (address, whether
   the child can be reached).
2. "An operator is free": the head of the tiered queue hands off with the
   summary card (tier, waited, situation, need, location, why, still unknown,
   language).
3. Surge replay (simulated): the default scenario under FIFO, keyword rules
   and model tiers; the immediate tier's P95 wait, the normal tier's P95 wait
   as the cost, and the misses, side by side.
4. Sidebar: switch to FIFO mode to show the degraded path; the invariants
   checklist stays on screen.

Caveat for the demo: the API keeps the queue in memory, and `--reload`
restarts it when any `.py` file changes. Do not edit code during the demo, or
run without `--reload`. The Retell live call is not wired yet; the board
takes typed utterances.
