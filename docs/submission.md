# Submission

Devpost project at <https://innovatela.devpost.com/>, due
**Sat 2026-10-17 22:00 PT**, no extensions. Aim to submit a complete draft
by 20:00 and only improve it after that.

## Checklist

- [ ] Devpost account for every teammate; teammates added to the project
- [ ] Project name, tagline and track chosen
- [ ] Description: problem, civil use, crisis use, how it works, twists adapted to
- [ ] Deck (also needed for the finalist tech check, Sun 09:00)
- [ ] Poster uploaded with Devpost by Sat 2026-10-17 22:00 PT (Twist 3; upload field announced for 13:00 PT)
- [ ] Demo video (record from a clean start; keep under the Devpost limit)
- [ ] Code: repository link, README quickstart works from a clean checkout
- [ ] AI tools used, listed below and copied into Devpost
- [ ] All three twist responses submitted on the portal (see [problem/twists.md](problem/twists.md))
- [ ] Sunday demo rehearsed on the demo laptop, with an offline fallback

## AI tools used

Required by the rules. Add each tool when it is first used.

| Tool | Used for |
|---|---|
| Claude Code | Coding assistant for the repository: code review, the playbook agent, line profiles, surge injector, the recorded-message evaluation, tests and docs |
| OpenAI Codex | Dataset acquisition and integrity checks, the multi-turn reception implementation, tests, repository documentation and Twist 2/3 response drafts |
| ChatGPT (6 Pro) | Idea evaluation, competitor and dataset research before the build |
| Claude API (Anthropic SDK, `claude-haiku-5-5`) | The reception agent's replies in the caller's language from playbooks, and structured caller-field extraction; code controls tier rules, emergency referrals and handoff. The same calls ran on recorded disaster messages for the evaluation ([evaluation.md](evaluation.md)) |
| Retell AI | Phone numbers, speech-to-text and text-to-speech for voice callers; the desk's own logic produces every reply (branch `voice-retell-bridge`) |

## Pitch outline (5 minutes)

1. The problem in LA, in one concrete scene.
2. Civil use: the ordinary day, live in the demo.
3. Crisis use: the same build when things break, live in the demo.
4. How it works and why it is feasible.
5. How it adapted to the three twists.
6. Impact and next step (incubator path).

## Poster

Content outline only; no poster file has been produced. The announcement and
deadline interpretation are in [Twist 3](problem/twists.md#twist-3). Confirm
the organizer's print size, accepted format and upload limits before export.

- Working headline: **Turn hold time into context for the next operator.**
- Problem: during a call surge, a supervisor needs to know who needs a
  person now while other callers remain in the queue.
- Central diagram, labeled as the proposed workflow until verified:
  waiting caller → interview → structured needs → deterministic queue
  rules → human operator with a summary.
- Two use cases: routine community assistance and disaster assistance
  during a surge, using the same queue and handoff design.
- Global inset: LA / China community assistance scenario; shared rules,
  localized language, addresses and service information. Mark Mandarin
  extraction and local deployment as unverified until tested.
- Human control: the operator makes the final decision; no autonomous
  dispatch. Clearly distinguish these design requirements from implemented
  behavior.
- Evidence panel: add an actual demo screenshot and reproducible results
  when available; label synthetic inputs and state limitations. No invented
  improvement percentages or unverified performance claims.
- Footer: final project name, team and verified demo/repository link once
  the team supplies them. Do not publish placeholder QR codes.

## Scoring self-check

| Criterion | Our evidence |
|---|---|
| Dual-use fit (tie-breaker) | |
| Technical execution | |
| Feasibility and impact | |
| Adapting to twists | |
| Demo and pitch | |
