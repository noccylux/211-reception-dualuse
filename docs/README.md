English · [中文](README.zh-CN.md)

# Documentation layout

| Path | Holds | Changes |
|---|---|---|
| [hackathon.md](hackathon.md) | Official event facts: schedule, deadlines, rules, tracks, judging. | When organizers announce a change. |
| [problem/](problem/) | The revealed problem (`brief.md`) and the three twists (`twists.md`), verbatim, with our reading. | At the reveal and at each twist. |
| [architecture.md](architecture.md) | What the build is now: the dual-use story, components, data sources, demo path. | With the code. |
| [datasets.md](datasets.md) | Local dataset inventory, provenance, limitations and pinned download manifest. | When datasets change. |
| [evaluation.md](evaluation.md) | First-turn evaluation on recorded disaster messages with proxy labels: method, results, limits. | When the evaluation reruns. |
| [mentor-advice.md](mentor-advice.md) | Mentor feedback mapped to a pinned main commit, with implementation gaps and proposed follow-ups. | When feedback is reviewed against a new build. |
| [submission.md](submission.md) | Devpost checklist, AI tools used, pitch outline, Devpost text, demo script. | Until submission. |
| [poster/](poster/) | Twist 3 poster: HTML source, exported PDF and PNG, demo screenshots. Export command in [submission.md](submission.md#poster). | When the poster changes. |
| [changes/](changes/) | The timeline: one record per decision, twist response or feature. | Append-only. |
| [agents/](agents/) | Working rules for coding agents, indexed by the root `AGENTS.md`. | When a rule changes. |
| `local/` | Git-ignored, present only on the authors' machines: the local Python environment, launcher and publishing notes for their agents. Absent in a fresh clone, by design. | Locally. |
| `information/` | Git-ignored: saved organizer pages and PDFs that `hackathon.md` and `problem/` cite. | Never edited. |

Record format and naming: [agents/change-records.md](agents/change-records.md).
