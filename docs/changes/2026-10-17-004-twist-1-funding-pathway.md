# Twist 1: federal funding pathway for the venture

* Type: twist
* Scope: `docs/problem/twists.md`, `docs/changes/`
* Related: [Repository scaffold](2026-10-16-001-repository-scaffold.md)

## Context

* Twist 1 (released Fri 2026-10-16 23:30 PT, due Sat 05:30 PT) asks each
  team to identify at least one US federal funding pathway, through an
  agency, program or military sector, as the primary or alternative source to
  launch the venture. Verbatim text in
  [twists.md](../problem/twists.md#twist-1).
* The venture at this point: an AI assistant for the hold queue of an
  overloaded 211-type or emergency line (Comms track) that talks to waiting
  callers, tiers them for human attention, never hangs up, and hands off to
  the operator with a summary. Track and seat are not yet recorded in
  `brief.md`; the response was written to hold for either a 211 line or a
  PSAP.

## Decision

* Primary pathway: DHS Science and Technology Directorate SBIR, because DHS
  S&T has funded NG911 topics before (FY20 topic DHS201-001, "NG 9-1-1
  Multimedia Content Analysis Engine") and SBIR/STTR were reauthorized on
  2026-04-13 through 2031-09-30, so Phase I is open again.
* Alternatives: AFWERX SBIR Open Topic (Department of the Air Force; dual-use
  requirement, Phase I about $75k over 3 months, needs an Air Force end
  user's Customer Memorandum; installation emergency communications centers
  are the end user) and NSF SBIR/STTR as the agency-agnostic route.
  Customer-side budgets named: FEMA Emergency Management Performance Grants
  and the federal 911 Grant Program (NHTSA/NTIA).
* Not used: DHS Silicon Valley Innovation Program and NIST PSCR, because no
  2026 open call was found in a quick search; DARPA and NASA, no fit.
* Build change planned to make the twist visible in the demo: a selectable
  line profile (211 disaster line, installation emergency line) in the same
  unchanged build. Deferred until the build exists; `architecture.md` is
  still the scaffold and was not changed here.
* The user pasted the response on the portal Sat 2026-10-17 about 00:35 PT;
  the submitted text is in `twists.md`.

## Verification

* Web checks Sat 2026-10-17 about 00:30 PT: SBIR/STTR reauthorization date
  and term (Mondaq summary of S. 3971); AFWERX Open Topic Phase I terms
  (afwerx.com/open-topic, 2025 cycle page); DHS FY20 SBIR topic list
  (MeriTalk). Not verified: the FY2026 DHS S&T topic list, the 2026 AFWERX
  Open Topic dates, the current NSF Phase I schedule, and the current 911
  Grant Program round. Check SAM.gov and the program pages before the pitch.
* Portal submission is user-reported; the portal confirmation was not seen
  by the agent.
* `bash scripts/uv-run.sh python -m pytest -q`: 4 passed in 1.00s (Sat
  2026-10-17 00:37 PT); docs-only change, no code touched.
