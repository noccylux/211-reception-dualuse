# Architecture: 211 reception desk

Current behavior of the integrated release for `main`,
released Sat 2026-10-17 after the user confirmed the campus demonstration finished.
A local prototype, not a telephone switch
or emergency dispatch system; English phone calls reach it only through the
Retell voice bridge ([voice.md](voice.md)), labeled origin `phone`. Design and history: change records
[008](changes/2026-10-17-008-reception-agent.md) and
[009](changes/2026-10-17-009-reception-agent-design.md).

## Dual-use story

- The seat: the supervisor of a 211-type community and disaster assistance line,
  not a 911 PSAP.
- Ordinary day: callers ask about benefits, housing, food or road status. While
  they wait, the assistant talks with them in their language, records the need
  and hands the operator a summary.
- Crisis: a wildfire or flood surge. 211 LA's after-action report for the January
  2025 wildfires lists, for 2025-01-08, 7,815 contacts offered, 60.66% abandoned
  and a 1 h 23 min average wait. The same build, unchanged, keeps every caller
  in a conversation, moves life threats ahead, sends people in danger to the
  emergency number and hands off with context.
- Global (Twist 2): a line profile switches language, emergency numbers and
  address conventions with the same queue rules. Built: Los Angeles 211 and
  China's 12345 government service hotline (110, 119, 120). The 12345 facts were
  checked Sat 2026-10-17 ([twists.md](problem/twists.md#twist-2)); 122 (traffic
  accidents) is not in the profile, and the operator summary stays English.
- Defense end user (Twist 1): an installation emergency communications line
  would be a third profile. Planned, not built.

## What is never automated

- The assistant never ends a call or places an outbound call.
- Code, not the model, decides tier, queue order and handoff. The model is told
  to restate only the desk facts it is given; a reply promising dispatch, a
  place in line or that no emergency call is needed is withheld for review.
- A reported danger is told to call the profile's emergency number, by the desk
  itself; immediate danger stays flagged until a person reviews it.
- Unknown information is ranked with priority, never as routine.
- Only a confirmed handoff completes a transfer; a failure keeps the original
  arrival time.
- No dispatch, verification or incident resolution. Reports are unverified.

## Components

| Component | Responsibility |
|---|---|
| `dualuse/reception.py` | One structured Claude call per caller turn: reply, extraction, language and distress. Checks the extraction against the caller's words. English offline baseline. |
| `dualuse/playbooks/*.md` | The agent's editable behavior: core rules, intake, calming, life safety, waiting, handoff. Loaded in name order (core first) into a cached system prompt. |
| `dualuse/profiles.py` | Line profiles and the desk's own lines (welcome, emergency, handoff, silence, failures) in English, Spanish and Mandarin. |
| `dualuse/holdqueue.py` | Call lifecycle, ordering, reservations, desk facts for the agent, review flags, callback tasks, persistence. |
| `dualuse/extract.py` | Fields, deterministic tier mapping, English keyword baseline, operator summary. |
| `dualuse/live_surge.py`, `surge_scripts.py` | Labeled batch of callers injected into the live desk. |
| `dualuse/storage.py` | SQLite snapshot of the desk. |
| `dualuse/api.py` | Validated HTTP boundary; one persistent desk per process. |
| `dualuse/ui.py` | Caller conversation (a text line that plays no sound), operator desk (one compact queue table, one details panel for the caller picked in **Caller details**, a reply box after takeover), incident reports, incident map, scenario simulator, about page. Panels refresh every 2 s. |
| `dualuse/triage.py`, `simulation.py`, `surge.py` | Queue policies and the offline policy simulation, with assumed error rates or measured tier shares. |
| `dualuse/evaluation.py`, `scripts/evaluate_messages.py` | First-turn evaluation on recorded disaster messages with proxy labels: each sampled message through a fresh desk in offline and Claude modes; Wilson intervals; measured tier shares for the simulator ([evaluation.md](evaluation.md)). |
| `dualuse/voice_bridge.py` | Separate process connecting Retell phone calls to the desk through the REST API only; see [voice.md](voice.md). |
| `dualuse/mapview.py` | Copies the active line's calls (caller words, stated location or test-data coordinates, tier and scorer band as display labels) into the map plugin once a second, with a new revision only when content changes. In memory; rebuilt after a restart and replaced on reset or profile switch. A task in the API's event loop asks the plugin once a second to look up the next new place the desk extracted ([record](changes/2026-10-17-024-automatic-map-location.md)). |
| `crisisfusion_map/` | Vendored CrisisFusion map plugin 1.0.0, mounted at `/plugins/map/` and shown in the UI's "Incident map" workspace. The service area comes from the line profile (`MapArea` in `profiles.py`): LA County with NWS + USGS, or Shanghai as an example city (OSM boundary) with USGS; both geocode with OpenStreetMap Nominatim. World-wide base map with a "Show all calls" control; calls can come from anywhere, and those located outside the area are dashed grey and flagged for transfer. The place the desk extracts from a call is looked up automatically, inside the service area only, and only that text is sent, never the call text. A single match is drawn as an unverified hollow diamond, and a street or area match carries its extent as the uncertainty circle. Several matches stay candidates for the operator. Official feeds and operator lookups run only on button press. It never changes a tier. See its [README](../crisisfusion_map/README.md). |
| `dualuse/shadow.py`, `crisisfusion_scoring/` | Shadow second opinion: the vendored CrisisFusion scorer reads each call's caller-only transcript (English/Spanish; other languages shown as "human check") and the operator desk shows its score, band, open needs and a disagreement flag next to the tier. It never changes a tier or the queue order. |

## Conversation turn

Each call opens with the desk's fixed welcome (`WELCOME` in
[profiles.py](../dualuse/profiles.py)): the caller is in the queue for the next
operator, the assistant is AI and takes details while they wait, the emergency
number, then "What is happening?". It states no queue position. The intake
playbook then asks fixed questions in a fixed order, skipping answered ones:
danger, location, how many people, need, medical or mobility needs. The same
questions in the caller's language are the fallback replies, and the offline
keyword mode asks them in the same order.

1. The caller's message is saved; the desk computes this turn's facts: line,
   address format, emergency number in the caller's language, callers ahead in
   the active order, tier so far, transfer status.
2. Claude (`claude-haiku-5-5`, structured output, low effort) receives the
   playbooks as a cached system prompt, the conversation as user (caller) and
   assistant (everything said to the caller) turns, and the facts as a final
   system message.
3. Quotes and the location are checked against the caller's words after
   normalizing case, quotes, whitespace and accents on Latin letters (callers
   often type `leogane` where Claude writes `Léogâne`); a respelled word still
   fails. Unverified quotes or locations are
   dropped and flagged for review; a life threat without a verified quote stays
   IMMEDIATE with a flag. An empty or oversized reply becomes a fixed question
   in the caller's language.
4. Rules map fields to a tier. On a new IMMEDIATE the desk says the emergency
   line, then the agent's reply follows. The caller's language is kept, so all
   later desk lines use it.

The offline keyword mode reads English only. A detected unsupported language
gets a review flag and cannot be ranked NORMAL using earlier routine keywords.
The call stays UNKNOWN unless the transcript already supports PRIORITY or
IMMEDIATE. FIFO mode records messages without classifying them.

## Lifecycle and concurrency

`waiting -> connecting -> handed_off -> completed`; `waiting` or `connecting`
can also end as `hung_up` or `disconnected`.

- Claude runs outside the desk lock. An operator can reserve a call during a
  turn; a call version discards the late reply. A reservation, hang-up, mode
  change or restart that interrupts a turn flags the unread caller message for
  review and raises a NORMAL call to UNKNOWN.
- Reservation is atomic within the one API process. A failed transfer returns
  the call with its original arrival. Reservations do not expire yet.
- Messages during `connecting` or `handed_off` are saved without another model
  interview and flagged for operator review; NORMAL becomes UNKNOWN. The bridge
  forwards buffered speech in both states. The handoff history remains a snapshot
  at confirmation; the call's full conversation includes later messages.
- After a confirmed takeover, the operator holding a typed call replies through
  `POST /calls/{call_id}/operator-message`. The reply is saved as an `operator`
  turn in the conversation, which the caller view shows within one refresh; it is
  never classified and never enters the caller-only transcript. Another
  operator, a call not yet confirmed and a phone call get 409: a phone caller
  cannot see text, and voice transfer is not connected.
- The voice bridge marks a call ended only after the desk acknowledges departure
  or reports that it already left the queue. Failed webhook requests remain
  retryable and do not cancel the pending disconnect grace task.
- Hang-ups and disconnects keep the conversation. Disconnects, silent hang-ups
  and IMMEDIATE, PRIORITY or UNKNOWN callers who leave get a callback review
  task; no number is collected and nothing is dialed.
- No-response events (simulated by buttons) first prompt the caller, then flag
  the call. On restart, interrupted turns and pending transfers are flagged.

SQLite (`.tmp/211-queue.sqlite3` by default) holds calls, dialogue, extraction,
tier, profile, language, reservations, handoffs and audit events.

## Ordering and incident reports

| Tier | Scheduling rank |
|---|---:|
| Immediate: reported life threat now | 0 |
| Priority: needs a person soon | 1 |
| Unknown: not enough information yet | 1 |
| Normal: routine request | 2 |

Claude fills the fields that decide the tier; [core.md](../dualuse/playbooks/core.md)
and the schema descriptions in `dualuse/extract.py` define them. Needing a
person soon includes the caller or people with them lacking shelter tonight,
food or drinking water today, medication or oxygen, or care for an injured or
sick person; a question about where or how to get help is routine.

FIFO applies within a rank. A normal caller waiting 30 minutes is scheduled at
rank 1 without changing the stored tier; this is not a maximum wait guarantee.
Reports are grouped by incident kind and normalized stated location, as an
unverified candidate association that never lowers anyone's priority.

## Data sources

| Source | Live / recorded / simulated | Used for |
|---|---|---|
| Typed messages in the caller view | live | The demo conversation |
| `dualuse/surge_scripts.py` | simulated, team-written | Surge callers in English, Spanish and Mandarin |
| Munro disaster response messages, test split, English translation ([datasets](datasets.md)) | recorded, CC BY 4.0 | First messages of surge callers, labeled per call; not 211 calls |
| Munro test split, direct messages, English translation and original text, with the dataset's categories as proxy labels | recorded, CC BY 4.0 | First-turn evaluation of the offline and Claude tiers ([evaluation.md](evaluation.md)); not 211 calls, so not 211 accuracy |
| Munro validation split, same filter and labels | recorded, CC BY 4.0 | Checking desk changes before the test split runs (`--split validation`) |
| Austin APD 911 Calls for Service, busiest day 2026-06-06 | recorded | Time-compressed surge arrival pattern; police dispatch, not 211 |
| 211 LA January 2025 after-action report, Appendix D | recorded, daily aggregates | Crisis figures above; scenario simulator defaults |
| Scenario simulator | simulated calls; assumed error rates, plus tier shares measured in the evaluation when `data/processed/eval_messages.json` exists | Offline policy comparison; it does not call Claude |
| `POST /calls` with `origin: replay` and `location` | replayed test data, labeled synthetic | Calls with coordinates that land on the map directly |
| LA County GIS boundary; OpenStreetMap Shanghai boundary (relation 913067, ODbL) | recorded, sha256 in `crisisfusion_map/data/geo_sources.json` | Service area per line profile; the OSM outline is not an official boundary |

Dataset setup is documented in [datasets.md](datasets.md).

## Failure behavior and limits

- Public deployment: the caller desk and simulator are available at `https://demo.211deskdemo.site/`.
  The running API and UI use `DUALUSE_MAP_URL=https://demo.211deskdemo.site`; the tunnel's first
  route sends that hostname's `^/plugins/map/` path to port 8000, before the UI route to port 8501.
  The visitor's browser loads the incident map itself, so a public map needs two things: a tunnel
  route that sends `/plugins/map/` on the public hostname to the API, and `DUALUSE_MAP_URL` set to
  that public URL in the environment of both API and UI processes (the UI does not read `.env`).
  The UI then points the map frame there, and the map accepts
  that host in addition to loopback. Unset, the frame uses `DUALUSE_API_URL` and the map stays
  loopback only. Map buttons then work for any visitor, as the rest of the public desk does. See
  [public map URL](changes/2026-10-17-021-public-map-url.md).
- Model mode: 20 s timeout, no retries, up to 4,000 output tokens because
  hidden thinking counts against the limit. A failed turn keeps the message, shows
  an error, flags the call and makes a non-immediate call UNKNOWN.
- Each message is at most 4,000 characters, 32,000 per conversation. Caller
  text is escaped before display. No authentication: run on localhost only.
- Tier accuracy is measured only on recorded disaster messages with proxy labels, first
  message only ([evaluation.md](evaluation.md)), not on 211 calls or whole
  conversations. Not measured: latency under load, Mandarin
  and Spanish quality beyond the smoke checks in records 009 and 016.

Startup and the demo path: [README](../README.md).
