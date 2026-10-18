# Submission

Devpost project at <https://innovatela.devpost.com/>, due
**Sat 2026-10-17 22:00 PT**, no extensions. Aim to submit a complete draft
by 20:00 and only improve it after that.

## Checklist

- [ ] Devpost account for every teammate; teammates added to the project
- [ ] Project name, lens (track) and one-line description chosen; proposal in [Devpost text](#devpost-text)
- [ ] Description: problem, civil use, crisis use, how it works, twists adapted to; drafted in [Devpost text](#devpost-text)
- [ ] Responsible-use note (two lines); drafted in [Devpost text](#responsible-use)
- [ ] Deck, at most 10 slides ([hackathon.md](hackathon.md#rules)); finalists' deck due Sun 09:00
- [ ] Poster uploaded with Devpost by Sat 2026-10-17 22:00 PT: [poster.pdf](poster/poster.pdf) is produced (see [Poster](#poster)); check the live form for a poster field
- [ ] Demo video under 3 minutes that shows our prompts, as the Hub asks of Retell teams; script in [Demo script](#demo-script-3-minutes)
- [ ] Code: repository link, README quickstart works from a clean checkout. The repository returned 404 to an anonymous request on Sat 2026-10-17 13:15 PT: make it public or share it with the judges
- [ ] AI tools used, listed below and copied into Devpost
- [ ] All three twist responses submitted with the final submission; drafts in [problem/twists.md](problem/twists.md)
- [ ] Sunday demo rehearsed on the demo laptop, with an offline fallback

## AI tools used

Required by the rules. Add each tool when it is first used.

| Tool | Used for |
|---|---|
| Claude Code | Coding assistant for the repository: code review, the playbook agent, line profiles, surge injector, the recorded-message evaluation, operator text replies and the compact operator queue, tests and docs |
| OpenAI Codex | Dataset acquisition and integrity checks, the multi-turn reception implementation, tests, repository documentation, Twist 2/3 response drafts, staging branch integration, and the Devpost text update and code review for the mentor-feedback changes |
| ChatGPT (6 Pro) | Idea evaluation, competitor and dataset research before the build |
| Claude API (Anthropic SDK, `claude-haiku-5-5`; evaluation comparison with `claude-sonnet-5-5`) | The reception agent's replies in the caller's language from playbooks, and structured caller-field extraction; code controls tier rules, emergency referrals and handoff. The same calls ran on recorded disaster messages for the evaluation ([evaluation.md](evaluation.md)) |
| Retell AI | Phone numbers, speech-to-text and text-to-speech for voice callers; the desk's own logic produces every reply (branch `voice-retell-bridge`) |
| DeepSeek V4.1 Flash via OpenRouter (`deepseek/deepseek-v4.1-flash-1017`, Anthropic-compatible Messages API) | Compared with `claude-haiku-5-5` on the recorded-message evaluation only; the demo does not use it ([evaluation.md](evaluation.md)) |

Third-party code: `crisisfusion_map/` is the CrisisFusion map plugin 1.0.0,
written by a classmate as a separate demo. We translated its UI strings to
English and changed one test path; we then generalized its LA County
boundary into a host-chosen service area (boundary, view, geocoder, feeds),
added an OpenStreetMap Nominatim geocoder for areas outside the US and an
out-of-area marker. Leaflet 1.9.4 (BSD-2-Clause) ships inside it.

`crisisfusion_scoring/` is the CrisisFusion scoring plugin 1.0.0 by the same
classmate (deterministic English/Spanish rules, 0–100 Human Attention Index),
vendored unchanged. It runs as a shadow second opinion beside our tier and
never changes a tier or the queue order.

Before submitting, name the author of both plugins and list the AI tools they used.

Boundary data: Shanghai Municipality (the example city for the 12345 profile) from OpenStreetMap contributors (ODbL),
relation 913067 via Nominatim; LA County from LA County GIS.

## Pitch outline (5 minutes)

1. The problem in LA, in one concrete scene.
2. Civil use: the ordinary day, live in the demo.
3. Crisis use: the same build when things break, live in the demo.
4. How it works and why it is feasible.
5. How it adapted to the three twists.
6. Impact and next step (incubator path).

## Poster

Produced Sat 2026-10-17 by 13:30 PT for [Twist 3](problem/twists.md#twist-3).
Headline: **Turn hold time into context for the next operator.**

| File | What it is |
|---|---|
| [poster/poster.pdf](poster/poster.pdf) | The upload: one 24 × 36 in portrait page, vector text, screenshots embedded at full resolution, 0.4 MB |
| [poster/poster.png](poster/poster.png) | 3600 × 5400 px image (150 dpi at full size), 2 MB, for a gallery image or a quick look |
| [poster/poster.html](poster/poster.html) | The source: edit the text here, then export again |
| [poster/screens/](poster/screens/) | Screenshots of the running desk and the crops used on the poster |

- Format: the Participant Hub asks for "POSTER PDF", optional but
  recommended, and gives no size. 24 × 36 in is our choice; the PDF scales to
  any 2:3 print (12 × 18, 16 × 24 or 20 × 30 in).
- Figures: 211 LA's after-action report on the January 2025 Eaton and
  Palisades wildfires, Appendix D, p. 58
  (<https://211la.org/sites/default/files/2025-10/211-la-final-comprehensive-after-action-report-aar.pdf>).
  For 2025-01-08, agency-wide: 7,815 contacts offered, abandonment rate 60.66%
  as printed (the row's own counts, 3,067 answered, give 60.75%), average wait
  01:23:06. The 12345 facts and sources are in [Twist 2](problem/twists.md#twist-2).
- Screenshots: a separate local desk (API 127.0.0.1:8075, UI 127.0.0.1:8575,
  database `.tmp/poster-demo.sqlite3`) in model mode with `claude-haiku-5-5`,
  driven through README demo steps 1 to 9 with team-written messages on Sat
  2026-10-17 between 12:57 and 13:10 PT, captured at twice the pixel density
  with headless Edge, then cropped.
- Not on the poster: the team name and a repository link (the repository was
  not public when checked). Add them to `poster.html` and export again.

Export from the repository root (PowerShell, Edge on Windows). The page is
fixed at 2304 × 3456 CSS px and cuts off anything longer, so look at the PNG
after an edit.

```powershell
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$src = ([Uri](Resolve-Path docs\poster\poster.html).Path).AbsoluteUri
Start-Process $edge -Wait -ArgumentList '--headless=new', "--user-data-dir=`"$env:TEMP\poster-edge`"", '--no-pdf-header-footer', "--print-to-pdf=`"$PWD\docs\poster\poster.pdf`"", $src
Start-Process $edge -Wait -ArgumentList '--headless=new', "--user-data-dir=`"$env:TEMP\poster-edge`"", '--hide-scrollbars', '--window-size=2304,3456', '--force-device-scale-factor=1.5625', "--screenshot=`"$PWD\docs\poster\poster.png`"", $src
```

## Devpost text

Draft for the Devpost fields, originally written Sat 2026-10-17 13:30 PT and
reconciled with `codex/demo-integration-20261017`. Project name, one-liner and
lens are proposals for the team to confirm. The integration includes the map,
shadow scorer and recorded-message evaluation. The simulator can replay measured
tier shares as well as assumed rates. Neither is measured 211 accuracy or a
real-world wait-time effect; see [evaluation.md](evaluation.md) for results and limits.

- **Project name:** 211 Reception (the name in the app)
- **One line:** An AI reception desk for the hold queue of community and
  disaster lines: Claude talks with every waiting caller in their language,
  code decides who needs a person first, and the operator gets a summary.
- **Lens:** Resilience Comms (Retell AI), track 03.

### Inspiration

On 8 January 2025, during the Eaton and Palisades fires, 211 LA was offered
7,815 contacts in one day. 60.66% were abandoned and the average wait was
1 hour 23 minutes (211 LA after-action report, Appendix D). To a phone queue, a
question about FEMA forms and a report of someone trapped by smoke look the
same. Track 03 asks the overnight supervisor's question, how to tell who needs
a person right now, and what must never be automated. We wanted the hold time
itself to do useful work: keep every caller company, learn what they need, and
give the supervisor and the next operator an honest picture.

### What it does

211 Reception is an AI reception desk for the hold queue of a community and
disaster assistance line: a 211-type line, not 911.

- **Every waiting caller gets a conversation.** Callers join by typed chat or,
  through our Retell voice bridge, by an English phone call. The caller page
  is a silent browser text line for callers who cannot speak safely, not SMS.
  The desk greets them, says how many callers were already waiting, and tells
  them to call the emergency number if anyone is in danger right now.
- **Claude talks with them in their language.** The agent follows editable
  playbooks: acknowledge, calm, ask one question at a time, and never promise
  help, a callback or a place in line. In our demo it answers in English,
  Spanish and Mandarin.
- **The need is written down with evidence.** Each turn, Claude also returns
  the situation, need, location, danger and the caller's exact words behind
  the risk. Code checks every quote and the location against what the caller
  said and flags anything it cannot find.
- **Code, not the model, ranks the queue.** Immediate (life threat now),
  Priority (needs a person soon), Unknown (not enough information: ranked with
  Priority, never as routine), Normal (routine; moves up after 30 minutes).
  First come, first served within a tier. When a call turns Immediate, the
  desk itself tells the caller the emergency number.
- **The supervisor sees the whole floor.** One compact queue table shows
  tiered and arrival order, with one detail panel for the selected caller.
  The desk shows review flags, callback review tasks for dropped callers
  (nothing is dialed), and possible shared incidents at the same stated place:
  unverified, and never lowering anyone's priority.
- **A person takes over with context.** An operator reserves the next caller
  and gets a summary: tier, situation, need, location, the quotes behind the
  tier and what is still unknown. Only the operator's confirmation completes
  the handoff; a failed transfer returns the caller with the original arrival
  time. On a typed call, the operator and caller then exchange text messages
  in the desk. A phone caller still hears only a fixed handoff notice, with
  no operator text; voice transfer is not connected
  ([change 022](changes/2026-10-17-022-operator-replies-and-queue-view.md)).
- **It can be shown under load.** A labeled surge injector adds team-written
  callers (simulated) and real messages from past disasters (Munro disaster
  response messages: Haiti 2010, Pakistan floods 2010, Sandy 2012) on a
  time-compressed Austin 911 arrival pattern.
- **Line profiles (Twist 2).** Los Angeles 211 and China's 12345 government
  service hotline run the same rules; language, emergency numbers and address
  order change.

### How we built it

- **Backend:** FastAPI (`dualuse/api.py`) runs one desk per process. SQLite
  keeps calls, conversations, extractions, flags, reservations, handoffs and
  audit events, so the desk survives a restart.
- **Agent:** one Claude call per caller turn (`claude-haiku-5-5`, Anthropic
  SDK, structured output against a plain JSON schema, 20 s timeout). The
  playbooks (`dualuse/playbooks/*.md`) are a cached system prompt, the
  conversation goes in as real turns, and the desk's facts for that turn
  (callers ahead, transfer state, emergency number, address format) come last.
  The model may restate only those facts.
- **Rules:** tier mapping, ordering, reservations, the two-phase handoff and
  callback tasks are plain Python (`dualuse/holdqueue.py`, `dualuse/extract.py`).
  An English keyword mode and a FIFO recording mode are labeled fallbacks.
- **Interface:** Streamlit (`dualuse/ui.py`): caller view, operator desk,
  incident reports, scenario simulator.
- **Voice:** a separate bridge (`dualuse/voice_bridge.py`) serves Retell's
  custom-LLM WebSocket, verifies Retell's signed webhooks and reaches the desk
  only through its REST API, so a phone call is an ordinary desk call marked
  phone. Tested with Retell's dashboard test call through a Cloudflare quick
  tunnel.
- **Tests:** more than 200 pytest tests with stub model clients and no paid
  calls, including the Streamlit app driven by `AppTest` and the bridge played
  against the real desk API.

### Challenges we ran into

- **Keeping the model honest.** A model reply could promise dispatch or a
  place in line. Queue, emergency and handoff announcements are code-owned
  desk lines, and a reply that promises dispatch or a place in line is
  withheld for review.
- **Trusting extraction.** The model once appended a note to the location
  field and can quote words the caller never said. Code now checks quotes and
  locations against the caller's own words; a life threat without a verified
  quote stays Immediate and is flagged.
- **Races.** An operator can reserve a caller while Claude is still replying;
  call versions discard the late reply and flag the unread message.
- **Phone audio.** Short recognizer fragments such as "Yeah." made the caller
  hear the same desk line four times in a row; the bridge now replaces a
  repeated line with a short "I'm still here" notice. The phone line is
  English only because the Retell voice and recognizer are.
- **Honest data.** There are no public 211 call recordings, so the surge mixes
  team-written scripts with recorded disaster messages and labels every caller
  by origin.

### Accomplishments that we're proud of

- One unchanged build runs an ordinary-day queue, a crisis surge and, with a
  profile switch, a second country's line.
- The safety rules live in code we can test, not in a prompt we hope holds.
- In our demo runs, a reported life threat was ranked Immediate after the
  caller's first message, in English and in Mandarin (team-written test
  conversations, not a measured rate).

### What we learned

- Put the model where language matters and keep it away from the decisions
  that must be auditable.
- "Unknown" deserves priority: ranking unclear callers as routine is where
  harm hides.
- Localizing a line is mostly data: language, emergency numbers and address
  order. Deployment is the hard part: telephony, hosting, data rules, a
  partner.

### Dual use

- **Ordinary day:** a 211 line answering questions about benefits, rent help,
  food and road status. The assistant records each need while callers hold,
  nobody loses their place, and the operator starts with a summary. Second
  customer: municipal non-emergency and service lines that already run hold
  queues.
- **Crisis, same build:** a wildfire or flood surge. Life threats move up and
  hear the emergency number at once; unclear callers are not buried; silent
  callers are flagged; callers who drop become callback review tasks; matching
  reports are grouped for the supervisor. If the model is down, a supervisor
  can switch to the labeled keyword or FIFO mode; failed model turns are kept
  and flagged, never silently replaced.
- **Global (Twist 2):** the China 12345 profile. 12345 is the local-government
  line for non-emergency requests, it must pass emergencies to 110, 119, 120
  or 122, and it surges in disasters (over 33,000 rain-related calls in 72
  hours in Beijing, July 2023). Sources: [Twist 2](problem/twists.md#twist-2).
- **Defense end user (Twist 1):** an installation emergency communications
  line is a planned third profile, not built; it is the end user for the
  AFWERX pathway.

### What's next

Planned work, including the remaining [mentor suggestions](mentor-advice.md);
these additions are not built.

- Extend the completed first-turn recorded-message evaluation to whole conversations and consented 211 data before claiming operational accuracy or wait-time benefits.
- Voice transfer to a person and consented callbacks through Retell; a real
  phone number with in-call SMS for text and addresses.
- Operator-confirmed consolidation of reports about the same incident into
  one operator conversation, keeping each caller's needs.
- Dedicated incident kinds for demo scenarios, such as earthquake and flood,
  independent of urgency.
- One narrowly defined routine request the assistant can complete after the
  caller confirms, with an audit record.
- Distinguish background speech from the caller's own report, validated at
  the voice layer.
- Consented location sharing from the caller's device, kept distinct from
  the stated address.
- An operator-review flag for suspected prank or abuse calls that never
  silently discards a possible emergency.
- Spanish and Mandarin phone calls, once tested with a matching voice and
  recognizer.
- The installation line profile, a pilot with a 211 agency, and a local
  partner for telephony, hosting and data rules before any 12345 use.
- Reservation timeouts and an audit event for every tier change.
- Funding: DHS S&T SBIR, with AFWERX SBIR Open Topic and NSF SBIR as
  alternatives ([Twist 1](problem/twists.md#twist-1)).

### Responsible use

Misuse: a line could use the tiers to push people down the queue or to replace
staff instead of supporting them. We limit this: tiers come from fixed, tested
rules, unclear calls rank with priority, routine callers move up after 30
minutes, the assistant never hangs up, dispatches or completes a handoff, and
every change is in the audit trail.

### Built with

python, fastapi, streamlit, sqlite, pydantic, pandas, plotly, anthropic
(claude-haiku-5-5), retell-ai, cloudflare-tunnel, pytest.

### AI tools

Copy the [AI tools used](#ai-tools-used) table.

## Demo script (3 minutes)

Follows [README steps 1 to 9](../README.md#demonstrate); the Hub limits the
video to 3 minutes and asks teams that used Retell to show their prompts.
The original script was rehearsed on Sat 2026-10-17 12:57 to 13:10 PT on a
separate desk; observed reply time was a few seconds per caller turn. That
rehearsal predates the operator text exchange below.

Before recording: model mode, line profile Los Angeles 211, an empty desk
(sidebar, **Reset local demo**), the caller view in one tab and the operator
desk in another, messages ready to paste. Trim model waits in editing.

| Time | Screen and action | Say |
|---|---|---|
| 0:00 | Poster headline, then the caller tab | "On 8 January 2025, 211 LA was offered 7,815 contacts; 60.66% were abandoned and the average wait was 1 h 23 min. 211 Reception turns that hold time into context for the next operator." |
| 0:15 | Steps 1–2: join, ask about FEMA assistance. Join again: "I see smoke coming from a building." Then "It is at 12 Oak Street. I am outside." and "Someone on the second floor is shouting for help and cannot get out." | "Claude talks with every waiting caller. When there is danger, the desk itself says call 911, and code, not the model, moves the call up." |
| 0:45 | Operator tab: the queue (queue position against FIFO position), pick the smoke call in **Caller details**: evidence quotes, still unknown | "The operator sees why: the caller's own words." |
| 0:55 | Step 3: a third caller reports smoke at 12 Oak Street; open **Incident reports** | "Two reports at one address become a possible shared incident. Unverified, and nobody's priority drops." |
| 1:10 | Steps 4–5: reserve as `operator-1`, show the summary, **Confirm human takeover**. In **Reply to the caller**, type "This is the 211 operator. Is everyone out of the building?" Show it in the caller tab; the caller answers in **Type a message to the operator**. Then **Operator finished this call**. | "A person takes over in the same conversation." |
| 1:30 | Step 6: **Demo call events**, **No response event** twice (the panel closes after a click; reopen it), then the review flag on the operator desk | "Quiet callers get one check-in, then a person looks. Dropped callers become callback reviews; nothing is dialed." |
| 1:45 | Step 7: join and write "Mi mamá necesita oxígeno y se fue la luz hace dos horas." | "Callers are answered in their own language." |
| 2:00 | Step 8: switch **Line profile** to 12345, join, write "我家楼下被水淹了，我奶奶腿脚不方便，出不去，水还在涨", then switch back to Los Angeles | "Twist 2: the same code on China's 12345 hotline. Only what is local changes: Mandarin, 110, 119, 120, Chinese address order." |
| 2:20 | Step 9: **Demo surge**, 20 callers, mixed, Austin, **Inject surge**; cut to the filled queue | "A labeled surge: team-written callers and real disaster messages, not 211 calls. Life threats rise to the top; everyone keeps their place." |
| 2:40 | `dualuse/playbooks/core.md` and `life_safety.md` in an editor; if the voice bridge is live, a phone call marked 📞 phone | "These playbooks are the agent's prompt, for typed and Retell phone calls alike. The model never decides tier, order or handoff, never hangs up and never dispatches. Same build on an ordinary Tuesday and in a fire." |

Notes:

- In the live demo, one person plays the caller and another the operator,
  on two devices or two tabs (mentor point 9).
- Step 9 takes about 60 to 90 s and about 30 model calls; record it apart or
  speed it up. Switch the profile back to Los Angeles first: new callers,
  surge callers included, take the profile that is active when they join.
- The Retell agent has no prompt of its own: it is a custom-LLM agent
  (voice `11labs-Adrian`) whose every reply comes from the desk through the
  bridge, plus the bridge's fixed lines in `dualuse/voice_bridge.py`.
- Restarting the API (end of step 5) does not fit in 3 minutes; it was checked
  during the rehearsal, when calls, flags, the handoff and 24 audit events
  survived a restart.

## Scoring self-check

| Criterion | Our evidence |
|---|---|
| Dual-use fit (tie-breaker) | One build for an ordinary 211 day and a fire or flood surge ([architecture](architecture.md#dual-use-story)); the China 12345 profile; an installation line planned for the defense end user |
| Technical execution | Claude turns with code-checked evidence, deterministic tiers and two-phase handoff, SQLite persistence across restarts, Retell bridge with signed webhooks, labeled live surge; 470 tests pass on branch `mentor-quick-wins` (Sat 2026-10-17 17:25 PT) |
| Feasibility and impact | 211 LA's January 2025 figures show the surge; runs on one laptop; labeled fallbacks when the model is down; DHS S&T SBIR path; no accuracy or wait-time claims until measured |
| Adapting to twists | Twist 1 submitted; Twist 2 built as a line profile with checked facts; Twist 3 poster produced ([twists.md](problem/twists.md)) |
| Demo and pitch | Nine-step demo path with a two-person caller and operator text exchange, live surge, English phone calls through Retell, poster, 3-minute script above |
