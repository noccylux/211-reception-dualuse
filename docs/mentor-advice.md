# Mentor advice against the current main build

This note summarizes the nine points in the user-supplied `Advice.docx`,
including its three UI screenshots, against local `main` commit
`7c3daf1c28653f5aa76fe7e8233de28dc162b488` on Sat 2026-10-17 PT.
It describes current code and proposed follow-ups; it does not adopt the
suggestions as implementation decisions or claim that they are built.
The addendum below records the later hand-drawn notes and discussion about
native phone calls, text and location. Its options remain undecided.

**Follow-up status, Sat 2026-10-17 evening:** the "Current main" paragraphs
below still describe commit `7c3daf1`. Change
[022](changes/2026-10-17-022-operator-replies-and-queue-view.md) then added
operator text replies to typed callers (point 9), one compact queue with one
details panel (point 8) and a visible note that the caller page is a silent
text line (point 5). Voice transfer, SMS and a silent phone flow are still not
built. The other points are next steps in the Devpost text
([submission.md](submission.md#whats-next)).

The mentor's overall direction is to reduce repetitive operator work, make
intake more reliable, and demonstrate a clearer interaction between caller
and operator. The current build already supports interviewing, prioritization,
report grouping, a map and a phone bridge. The main gaps are reducing the
number of calls that need a person and completing the human communication path.

## 1. Consolidate reports about the same incident

**Mentor advice:** If five people report the same fire at the same place,
one operator conversation may be enough; reduce repeated handling.

**Current main:** `HoldQueue.clusters()` groups reports by `incident_kind`
and a lightly normalized location string. The incident view shows report
counts and caller IDs. Every caller remains an independent queue entry;
grouping does not merge calls, stop intake or remove anyone from the queue.
There is no time window or semantic address matching, so this is only a
candidate association, including reports from calls that have already ended.

**Suggested follow-up:** Give an operator one incident view with linked
callers, a representative report and any new information. Confirm which
reports concern the same event before consolidating work. Retain each
caller's danger, needs and ability to request help: five reports at one
address can include five different people needing assistance.

Code: [holdqueue.py](../dualuse/holdqueue.py),
[incident_panel in ui.py](../dualuse/ui.py).

## 2. Separate incident type from urgency

**Mentor advice:** Use more detailed categories, such as fire and earthquake;
the source calls these “tier.”

**Current main:** These are already separate concepts. `Tier` is
`immediate`, `priority`, `unknown` or `normal`, and controls queue order.
`Extraction.incident_kind` is `fire`, `medical`, `utility`, `crime`,
`other` or `none`. Earthquake and flood are not dedicated incident kinds.
The map's earthquake feed does not add an earthquake intake category.

**Suggested follow-up:** Extend incident kinds for the demo's actual scenarios,
and update extraction, offline rules, grouping and UI together. Keep urgency
independent: asking about earthquake assistance and reporting someone trapped
after an earthquake need different priorities.

Code: [extract.py](../dualuse/extract.py), [triage.py](../dualuse/triage.py).

## 3. Finish suitable routine requests without occupying an operator

**Mentor advice:** Ask a few questions, record non-urgent matters, and possibly
finish the AI conversation to reduce the queue and waiting time.

**Current main:** The assistant gathers information and stores a summary and
conversation. It cannot finish a routine request independently. The playbook
prohibits ending the call, and `HoldQueue.finish()` requires a call already
handed to an operator. `report_only` and a low shadow score do not authorize
automatic completion.

**Suggested follow-up:** Start with one narrowly defined routine workflow,
such as submitting a report without requesting further help. Give the caller
a confirmation and a choice to keep waiting for a person. Introduce an
explicit completion outcome and audit record only after deciding the policy;
do not treat silence, a NORMAL tier or an AI answer as proof of resolution.
This changes the product's current lifecycle, rather than just its prompt.

Code: [core.md](../dualuse/playbooks/core.md),
[holdqueue.py](../dualuse/holdqueue.py), [shadow.py](../dualuse/shadow.py).

## 4. Distinguish background speech from the caller's report

**Mentor advice:** Background audio saying “I am on fire” should not
automatically make the caller an emergency case.

**Current main:** The Retell bridge forwards text from transcript entries
marked `user`. The desk does not receive raw audio, speaker attribution beyond
that role, or speech-recognition confidence in this path. Evidence checking
can verify that a quote exists in the transcript; it cannot prove who said it.
Once assigned IMMEDIATE, a call stays IMMEDIATE in the current turn logic.

**Suggested follow-up:** Evaluate background television, nearby speech,
unclear audio and genuine distress separately. Where safe, clarify whether
the statement describes the caller's situation and flag uncertainty for a
person. Any audio filtering needs validation at the voice layer. Do not claim
that the current text model has solved background-noise recognition.

Code: [voice_bridge.py](../dualuse/voice_bridge.py),
[_checked in reception.py](../dualuse/reception.py),
[HoldQueue.say](../dualuse/holdqueue.py).

## 5. Offer text when speaking is unsafe or impossible

**Mentor advice:** Let people choose text or voice, including a caller who
cannot speak because an intruder is nearby.

**Current main:** Streamlit provides typed intake, while the separate Retell
bridge provides phone intake documented as English only. Both feed the same
desk. There is no caller-facing channel switch preserving one conversation,
SMS integration, or dedicated silent interaction flow. The typed input is
disabled after the call leaves `waiting`.

**Suggested follow-up:** Make the text option easy to find before intake and
provide a clearly silent flow. Switching an existing phone call into text
would require linking identities and preserving its history and queue place.
Present the existing browser text path as the capability available today.

Code: [caller_panel in ui.py](../dualuse/ui.py),
[voice_bridge.py](../dualuse/voice_bridge.py).

## 6. Ask permission to obtain location

**Mentor advice:** Ask whether location access is allowed, then use the
location to improve intake and the map.

**Current main:** The map plugin already has per-call consent controls and
browser geolocation, including accuracy and permission-failure handling.
It locates the device running that page. On an operator's computer, this is
the operator's device, not the remote caller. Device position is stored
separately from the reported incident address. The desk's `POST /calls`
accepts supplied coordinates only for labeled replay data; the main caller
conversation has no integrated location-sharing control.

**Suggested follow-up:** Connect the existing consent flow to the caller's
own browser and call ID. Keep device position, reported incident address and
their provenance distinct. Declining location should still allow typed address
entry and intake. The source's suggestion that the backend can directly obtain
location is not a capability of the current phone bridge.

Code: [geo.js](../crisisfusion_map/static/geo.js),
[geo.py](../crisisfusion_map/geo.py), [api.py](../dualuse/api.py),
[mapview.py](../dualuse/mapview.py).

## 7. Flag suspected spam or prank calls

**Mentor advice:** Investigate spam detection, potentially using an LLM or
a model from Hugging Face. The source leaves the technology open.

**Current main:** No dedicated spam classifier or abuse-rate control is
implemented in the desk. Input validation and Retell webhook signature checks
serve other purposes; neither establishes whether a caller is truthful.
The shadow scorer is a second opinion on attention needs, not spam detection.

**Suggested follow-up:** First define observable abuse examples and an
operator-review flag. Compare simple repetition/rate signals with a model
only if those examples justify it. Keep suspected abuse separate from urgency;
an unvalidated spam score should not silently discard a possible emergency.

Code: [api.py](../dualuse/api.py),
[voice_bridge.py](../dualuse/voice_bridge.py), [shadow.py](../dualuse/shadow.py).

## 8. Consolidate repeated operator information

**Mentor advice:** Merge repeated information in the UI. The attachment shows
a queue table, a table with shadow-score fields and expandable caller details.

**Current main:** `operator_panel()` renders one waiting table containing the
shadow-score columns, then an expander for every waiting call. Thus the
screenshots should not be read as proof that main renders two separate waiting
tables. Repetition between the table and detail cards is still present, and
incident reports and the map are separate workspaces.

**Suggested follow-up:** Keep one compact queue with the essential urgency,
wait, language and review fields. Selecting a caller should reveal one detail
panel with evidence, transcript, location and relevant incident. Keep the
shadow score visibly advisory, with its explanation in details. This reduces
scrolling without removing information needed for review.

Code: [operator_panel and workspace selection in ui.py](../dualuse/ui.py).

## 9. Demonstrate a caller and an operator interacting

**Mentor advice:** Have one person act as the caller and another as the
operator, with a real communication step in the demo.

**Current main:** Two browser tabs can already show intake and the shared
operator desk. The operator can reserve, confirm takeover and finish a case.
However, there is no operator reply box or operator-to-caller messaging API.
The phone bridge plays a fixed handoff notice; it does not connect the
operator's voice to the caller.

**Suggested follow-up:** Rehearse a two-person demonstration of the existing
intake, priority change, summary and takeover. Label the takeover as a workflow
transition. To meet the stronger request for real conversation through the
product, implement and verify either operator text replies or an actual voice
transfer. Operator text replies would build on the existing UI/API; voice
transfer would demonstrate telephone continuity but adds telephony integration.

Code: [ui.py](../dualuse/ui.py), [api.py](../dualuse/api.py),
[voice_bridge.py](../dualuse/voice_bridge.py).

## Suggested order of work

This ordering is an assessment based on the code, not a ranking supplied by
the mentor or an approved implementation plan.

| Order | Work | Reason |
|---|---|---|
| First | Rehearse the two-person flow; simplify the operator view | Makes the existing build easier to understand and demonstrate. |
| Next | Add the incident types used in the demo; connect caller consent to location sharing | Extends existing structures and clarifies intake. |
| Then | Add operator replies; develop operator-confirmed incident consolidation and one routine completion flow | Addresses actual workload reduction and closes interaction gaps, with lifecycle changes. |
| Separate validation | Background-speech handling and spam detection | Requires representative evidence and error analysis beyond a UI demonstration. |

For future evaluation, measure operator conversations per incident, routine
requests completed with caller confirmation, time to human takeover, and
missed urgent needs. None of those improvements was measured in this review.
Existing behavior and evaluation limits remain documented in
[architecture.md](architecture.md) and [evaluation.md](evaluation.md).

## Addendum: native phone calls, text and location

Recorded Sat 2026-10-17 PT. The user's additional photograph of the mentor
discussion shows a phone screen with **Location** and **Text** buttons in
the lower-right corner. This makes the interface idea more explicit than
`Advice.docx`. The user prefers callers to use their existing phone and
messaging apps, without opening our website or installing our app, and is
willing to consider buying a demonstration number.

**Status: discussion only.** Whether to build this, which approach to use,
and whether to purchase a number remain undecided. This note authorizes no
purchase or implementation. The feasibility assessment below is our analysis,
not additional advice attributed to the mentor.

### What a real number would enable

A Retell number bound to our inbound agent would support this path:

```text
Phone's native dialer -> Retell -> existing voice bridge -> desk API -> operator UI
```

The existing [voice bridge](../dualuse/voice_bridge.py) and
[setup script](../scripts/retell_setup.py) provide the integration foundation.
The bridge must be reachable over public HTTPS/WSS and the number must be
bound to the correct agent. Buying a number does not itself establish that
this complete path works. It also does not add human voice transfer; see
point 9 above.

[Retell's number documentation](https://docs.retellai.com/deploy/purchase-number),
checked Sat 2026-10-17 PT, lists ordinary US Twilio numbers at $2/month,
with usage charged separately. A regular US Twilio number is the candidate
to consider if testing the SMS capability below.

### Where the proposed buttons can appear

| Interface | Feasibility |
|---|---|
| Our own web calling interface | We can implement buttons, message handling and consented location sharing. This requires callers to open that interface. |
| Retell's hosted test interface | Our backend cannot arbitrarily add controls; available customization depends on Retell's supported features. |
| The phone's native cellular-call screen | Buying a number or changing the receiving backend cannot insert custom Location or Text buttons. |

The call screen belongs to the device's calling software. Apple's
[CallKit](https://developer.apple.com/documentation/callkit) supplies system
calling UI. Android allows a replacement calling UI through an installed
[default phone app](https://developer.android.com/reference/android/telecom/InCallService),
which requires the user's selection. Neither provides the proposed universal,
installation-free buttons just because the user calls our number.

### Text through the existing messaging app

[Retell's SMS documentation](https://docs.retellai.com/deploy/enable-sms),
checked Sat 2026-10-17 PT, distinguishes two capabilities:

- **Receive SMS/MMS during an active call:** documented as available on Retell
  Twilio numbers without an A2P application. A caller could switch to their
  messaging app and send information to the number while staying on the call.
- **Send from our own number and run two-way SMS:** requires SMS enablement;
  Retell quotes approximately 2–3 weeks for the A2P application, sometimes
  longer. Telnyx is not currently supported for this SMS feature.

This is platform support, not a verified feature of our build. Our Custom LLM
WebSocket bridge forwards caller transcript text. We have not verified how
Retell delivers in-call SMS to that integration or whether it reaches the
same desk call. Message delivery, conversation association and operator display
would need an end-to-end check and any necessary adapter changes.

Text input followed by a spoken phone reply is not a fully silent channel.
The intruder scenario needs a separately designed silent response path; in-call
SMS alone does not establish that requirement.

### Location without our own input form

An ordinary phone call does not give this bridge access to the caller's GPS.
Without opening our page, the caller could state an address or send an address
or map-sharing link through SMS. Parsing a shared link and associating its
location with the correct call would still require implementation and testing.

One-click location permission normally needs a page or app on the caller's
device. Our browser location code is a starting point, but opening it on the
operator's device locates that device instead. Browser geolocation requires
permission and a secure context; see the
[Geolocation documentation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation).
Device position must remain distinct from the reported incident address.

### Candidate demonstration and unresolved decisions

The candidate to discuss is **native dialing first, then in-call SMS**, with
spoken or texted addresses initially. It avoids a new caller input form while
reusing the voice bridge. Automatic location sharing and a fully silent
two-way text conversation are separate additions.

Before adopting this approach, decide whether the demo needs only voice,
text input during a call, or a fully silent exchange; then verify the chosen
Retell number's capabilities and Custom LLM delivery. Also decide whether
typed addresses suffice or location sharing justifies a browser step. No
live phone/SMS/location integration was tested for this assessment.
