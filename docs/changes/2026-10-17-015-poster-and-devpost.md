# Twist 3 poster, Devpost text and demo script

* Type: twist
* Scope: `docs/poster/`, `docs/submission.md`, `docs/problem/twists.md`,
  `docs/hackathon.md`, `docs/README.md`
* Related: [Twist 3 reading](2026-10-17-007-twist-3-poster.md),
  [Twist 2 final response](2026-10-17-017-twist-2-final-response.md)

## Context

* Twist 3 asks for a poster with the Devpost submission by Sat 2026-10-17
  22:00 PT, printed for Sunday. Record 007 outlined it; no poster existed.
* The Participant Hub (last updated Sat 2026-10-17, read 13:15 PT) asks for
  "POSTER PDF", optional and without a size; a demo video under 3 minutes that
  shows the prompts of teams that used Retell; a deck of at most 10 slides;
  a responsible-use note. It also moved the Sunday schedule.

## Decision

* The poster is one HTML page fixed at 24 × 36 in (2304 × 3456 CSS px),
  exported by headless Edge to a PDF with vector text and lossless screenshots,
  and to a 3600 × 5400 px PNG. The team can edit the text and export again with
  the command in `submission.md`. Rejected: drawing it with Pillow (manual text
  layout) and adding a PDF library (a new dependency).
* Screenshots come from a fresh desk driven through README steps 1 to 9; the
  crops keep the key turns, with a light band where turns are skipped. Every
  input is labeled: team-written scenarios, simulated scripts, recorded Munro
  messages. The surge caption says "disaster messages", not "SMS" as the UI
  does: the dataset README calls them direct messages, and the surge drew some
  from Sandy 2012, where the channel is not stated.
* Only checked facts: 211 LA's Appendix D figures (agency-wide; 60.66% as
  printed) and the 12345 facts from record 017. No accuracy or wait-time
  claims; the scenario simulator is not on the poster.
* `submission.md` gets the Devpost text, a 3-minute demo script that follows
  README steps 1 to 9 and ends on the playbooks (the agent's prompt; the Retell
  agent is a custom-LLM agent with no prompt of its own), and the scoring
  self-check. The AI tools table needed no new tool. `hackathon.md` records
  the Hub's submission requirements and the new Sunday times.

## Verification

* README steps 1 to 9 in the browser pane on the separate desk of record 017,
  Sat 2026-10-17 12:57 to 13:10 PT: the smoke report became IMMEDIATE with the
  desk's 911 line; Incident reports showed "fire · 12 oak street" with two
  reports; reserve, confirm and complete worked; two no-response events flagged
  the call (the Demo call events panel closes after each click); the Spanish
  oxygen report was PRIORITY with Spanish replies; the 12345 run is in record
  014; an API restart kept the calls, flags, handoff and 24 audit events; the
  surge joined 20 of 20 callers with 26 turns, no errors, five IMMEDIATE calls
  on top.
* Poster: rendered in headless Edge until it fit (the footer ends at 3456 px).
  The PDF has one page, MediaBox 1728 × 2592 pt (24 × 36 in), four images at
  native resolution, 441 KB; the PNG is 3600 × 5400 px, 1.97 MB. Zoomed checks
  of the Twist 2 panel and footer: text and Chinese glyphs are sharp.
* Poster figures checked against the 211 LA report PDF (Appendix D, p. 58)
  and the sources in record 017.
* `bash scripts/uv-run.sh python -m pytest tests -q`: 205 passed. No code
  changed.
* Not checked: the live Devpost form (a separate poster field or one shared
  upload), a full-size print, the Retell phone path, and team names (not in
  the repository). The repository returned 404 to an anonymous request at
  13:15 PT, so the poster carries no repository link.
