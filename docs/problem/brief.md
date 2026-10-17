# Problem brief

The official problem as revealed on Fri 2026-10-16, its four tracks and how
it is judged, followed by our reading. Status: revealed; track and idea
chosen Sat 2026-10-17 00:45 PT (see [Our track choice](#tracks)). Twists go in [twists.md](twists.md); general event facts are in
[../hackathon.md](../hackathon.md).

Sources, saved in [../information/](../information/):

- Participant Hub, section "Problem Statement", headed "Preparing for
  Disaster: The Reveal Page" and "MYSTERY PROMPT @ Friday 6.15 PM". Saved
  Fri 2026-10-16 18:54 PT.
- Kickoff deck (`Dual-Use Hackathon Kickoff Deck.pdf`), shown in MCB 101 on
  Fri 2026-10-16 from 17:30 PT.

Not yet in our saved sources: the "Extended Card" with the "Harbor Night"
scenario that the prompt refers to. Get it from the portal and add it here.

## Official statement

Kickoff deck, slide "Mystery prompt: Preparing for disaster":

> Build a dual-use solution to prevent shutdowns in crisis
>
> Resilient systems in the face of disaster
>
> Think efficiency, effectiveness, & cost

Participant Hub, verbatim:

> As automation takes centre stage in the systems we depend on, more of them
> act on their own, and sometimes they stop behaving as expected. Something
> is where it shouldn't be, doing what nobody authorized, or has gone quiet
> when it should be talking. It could be a vehicle, a grid, a phone line, a
> shipment, a hospital ward.
>
> The usual answer is a bang: shut it down, cut it off, call everyone. A bang
> works, and it often costs more than the problem.
>
> Your challenge: Help someone prepare for disaster, how can you be
> pre-emptive rather than reactionary? Pick any person who has to decide,
> and find the gentlest response that still works: cheap enough to use
> widely, safe around people, and useful on an ordinary day too. This is
> decision making with a dual-use twist.
>
> We won't tell you what to build. Three times this weekend, we'll tell you
> the problem has changed with twists, you are encouraged (but not required)
> to incorporate them.
>
> NEW TO "DUAL-USE"? THIRTY SECONDS.
>
> A dual-use tool leads two lives. On an ordinary day it earns its keep, so
> people keep it around. In a crisis it matters, and it is already in place.
> It serves everyday people and people in a hurry, such as responders,
> operators and defenders.
>
> GPS began as military navigation and now sits in every phone.
>
> The microwave oven grew out of radar.
>
> Android phones use their motion sensors to spot earthquakes and warn
> people nearby.
>
> Here it does not mean weapons. It means a tool worth owning before the
> emergency, so that it is there when the emergency comes.
>
> HOW TO START
>
> Between doing nothing and the bang there is a ladder: watch, ask, slow,
> hold, hand to a person. Your build lives on one or two rungs. Four choices
> make a project:
>
> A person who has to decide.
>
> A moment when they have to decide it. Use the Harbor Night in the Extended
> Card, or your own.
>
> A second customer who would use it on an ordinary Tuesday.

The Hub announces "Four choices" but lists three; the fourth is presumably
the track. Ask the help desk if it matters.

Key constraints, as we read the statement:

- Be pre-emptive: act before the "bang" (shut down, cut off, call
  everyone), choosing the gentlest rung that still works.
- The response ladder is watch, ask, slow, hold, hand to a person. The build
  covers one or two rungs.
- Cheap enough to use widely, safe around people, useful on an ordinary day.
- The build supports one named person who has to decide, at a named moment,
  and has a named second customer for an ordinary Tuesday.

## Tracks

There are four tracks. There is no fifth track revealed on Friday, as the
earlier event material suggested: the Hub's "five lenses" are these four plus
IBM SkillsBuild's Best Build with IBM Bob, a prize open to every track that
stacks with a track prize.

| # | Track (reveal page) | Lens (Hub) | Partner | The seat | The blunt move to avoid |
|---|---|---|---|---|---|
| 01 | Marine: Under the Water | Crisis Mitigation | NULL Systems (Hub: NULL Labs) | Harbor watch officer | Shutting the harbor down |
| 02 | Energy: On the Grid | Energy & Grid Hardening | Base Power | Dispatcher of a home-battery fleet | Shedding load |
| 03 | Communication: On the Line | Resilience Comms | Retell AI | Overnight supervisor of a call line | Alerting everyone, or sending everything to an absent human |
| 04 | Ports: At the Gate | Ports & Logistics | Terminal49 | Terminal planner | Holding everything or closing the terminal |

The deck's advice: "Pick the track that matches the seat you want to sit in,
not the technology you already know."

Track text from the Hub, verbatim:

> **01. Marine, with NULL Systems: Under the Water**
>
> The seat: the harbor watch officer. An unauthorized autonomous vehicle is
> in a working harbor. Detecting small underwater vehicles is getting easier.
> Handling one safely is not. What sits between "seen" and "handled"? What
> should a small, low-cost platform decide alone, and what must a person
> approve? What does it do for a living on a quiet Tuesday, like finding a
> lost research vehicle? Cost, safety and scale all count. Elegant beats
> loud. Your work stops at the handoff to a human. How a vehicle is
> physically halted is out of scope this weekend.

> **02. Energy, with Base Power: On the Grid**
>
> The seat: the dispatcher of a home-battery fleet. Homes full of automated
> batteries are now part of the grid, and the harbor, the phones and the
> cold rooms all run on it. When something strains or goes odd, the blunt
> move is shedding load. What sits between "normal" and "shed"? Whose power
> can wait, and how would you know? When a battery goes silent, is it
> broken, tripped or just not talking? How does the same battery earn its
> keep on an ordinary day?

> **03. Communication, with Retell AI: On the Line**
>
> The seat: the overnight supervisor of a call line. A surge of calls and
> alerts no one can fully verify, and too few people to answer them.
> Residents are your earliest sensor and your biggest flood. The blunt move
> is to alert everyone, or send everything to a human who isn't there. How
> do you tell who needs a person right now? What must never be automated?
> What happens when someone doesn't pick up?

> **04. Ports, with Terminal49: At the Gate**
>
> The seat: the terminal planner. One box, four stories. The carrier says
> it's empty, the terminal scale says it's heavy, customs has a hold on it,
> and the refrigeration plug says it's warming. A hundred more boxes need the
> same gate, half the lanes are down, and the clock on charges is running.
> The blunt move is to hold everything or close the terminal. What can you
> slow, reroute, inspect or release? Which source do you trust? Which box
> can't wait?

Our track choice, decided Sat 2026-10-17 00:45 PT: **03 Communication (Resilience
Comms, Retell AI)**. The seat is the overnight supervisor of a 211-type
community and disaster assistance line, not a 911 PSAP. The build is a hold-queue
assistant: while callers wait for an operator, a voice agent interviews them,
deterministic rules put the ones who need a person now ahead (FIFO within a
tier, insufficient information stays priority, bounded delay for everyone
else), and the call transfers with a summary the moment an operator is free.
It never hangs up and never makes the final decision. Design in
[../architecture.md](../architecture.md); reasoning in
[../changes/2026-10-17-005-track-and-idea.md](../changes/2026-10-17-005-track-and-idea.md).
Rejected: a 911 PSAP seat (Carbyne, Prepared and Aurelian already sit there
and automated calls into 911 are not accepted), and the brainstormed C1
Callback Ladder as the main build (kept as the escalation path for callers
who hang up while waiting).

## Judging

The five criteria, the two rounds and the open awards are in
[../hackathon.md](../hackathon.md#judging). What matters for the problem:

- Each criterion scores 1 to 5: dual-use fit, technical execution,
  feasibility and impact, adapting to twists, demo and pitch. Dual-use fit
  breaks ties.
- The Hub's hint: "The easiest way to show dual-use fit is to name your
  second customer and the day they would use it."
- Twists are encouraged, not required, but adapting to them is a criterion
  and decides Best Shift Adapter, scored from the three twist responses:
  "The best adapters change the build, not just the slides."
- The deck's three tests: who pays on a calm Tuesday and why; what the build
  does at 3 AM with the network down and the staff gone; optionally, whether
  it works with a tenth of the budget (place, network, language, price,
  trust).
- The Devpost project needs a responsible-use note: two lines on how the
  tool could be misused and how we limit that.

Track prize criteria from the Hub, judged with each sponsor. A team enters a
track by picking its lens at submission; only finalists win track prizes.

| Lens | Technical depth | Feasibility | Impact | Dual-use |
|---|---|---|---|---|
| Crisis Mitigation (NULL) | Detects, warns and responds, not just displays data | Responders could use it during a real incident | How many people are safer, and how much faster | Useful on a normal day and when a wildfire, flood or port threat hits |
| Energy & Grid (Base Power) | A working model, data flow or prototype, not a concept | A utility, city or homeowner could deploy it | How many homes or hours of outage it protects | Saves energy or money every day and keeps power on during outages |
| Resilience Comms (Retell AI) | A working voice, text or messaging flow; Retell voice agents encouraged | Works when networks are weak or people speak different languages | Who it reaches that today's alerts miss | Useful for everyday service and still works in a crisis |
| Ports & Logistics (Terminal49) | Built on real container data from the Terminal49 API, not mock data | A shipper, port or trucker could use it next week | Delays, cost or emissions cut | Smooths daily freight flow and holds up when the port is disrupted |
| Best Build with IBM Bob (any lens) | How central IBM Bob was to the build; say how on Devpost | The code is clean and runs | The problem it solves | Fit with the chosen lens |

## Our reading

- Who uses it on an ordinary day (civil use), and what job it does for them.
- Who uses it in a crisis or contested setting, and what changes for them.
- Why the same build serves both without modification.
- Constraints and assumptions we are making; open questions for mentors.

## Data and partner resources

From the Hub and the kickoff deck. What each gives a demo, as researched on
Fri 2026-10-16, is in [Facts behind the ideas](#facts-behind-the-ideas).

- NULL Systems: a run in their autonomy sim (track prize).
- Base Power: no data or API announced yet.
- Retell AI: $10 in free credits per innovator for voice agents; build
  session Sat 2026-10-17 10:30 PT.
- Terminal49: real container data via the Terminal49 API; the track requires
  it instead of mock data.
- IBM: IBM Bob free 30-day trial at <https://ibm.biz/university-bob>; IBM and
  NASA open geospatial models on Hugging Face (flood mapping, burn scars,
  weather and climate).

## Candidate ideas

Brainstormed Fri 2026-10-16 between 19:30 and 20:00 PT by five research
subagents: one per track and one cross-track pass. The team has not
discussed them yet. "Real" data comes from a public or partner source the
subagents found; "simulated" data must be labeled as such in the demo. The
facts behind the ideas, with the unverified ones marked, are in
[Facts behind the ideas](#facts-behind-the-ideas).

| Idea | Civil use (Tuesday customer) | Crisis use (decider, moment, rungs) | Demo in 24 h? | Track fit |
|---|---|---|---|---|
| **M1 Slow, Don't Shut** (01 Marine, top pick): the smallest time-boxed set of holds and slow-downs that keeps people clear of a contact, instead of closing the harbor | Port harbor department: the same planner for a whale in the channel, a container overboard or dredging | Harbor watch officer, 0–5 min after an unidentified contact is confirmed near a channel; the area it could be in grows while it is silent. Slow, hold | Yes. Real: one recorded day of LA/LB AIS. Simulated: harbor outline, the contact. Greedy planner; a map compares full closure with the plan | Attacks the named blunt move; reports movements saved and people kept clear |
| **M2 Subsurface Registry** (01, alternate): dives, hull cleanings and AUV surveys are filed; each contact is matched against the filings, an unmatched one gets a hail, then a person | Dive, hull-cleaning and survey operators; warns divers when a vessel is arriving at their berth | Watch officer in the first 60 s: is the contact permitted, lost or unknown? Watch, ask | Yes. Simulated: filings, contacts, hail. Real: AIS for conflict checks. May read as a forms app | Makes "unauthorized" decidable; best used as a part of M1 |
| **M3 Lost & Found** (01, alternate): a drift probability map tells one boat with a dipping hydrophone where to listen next | Oceanographic institutes and survey firms recovering a lost AUV or glider, the track's own Tuesday example | Recovery lead, 0–6 h after a vehicle goes silent; in a crisis, where an intermittent contact is now. Watch, hand to a person | Partly. Getting current data in is the risk. Simulated: the vehicle loss, listening results | Strong Tuesday story, weaker crisis story |
| **E1 Reserve Ledger** (02 Energy, top pick): per-home backup hours decide how many MW the fleet can sell without leaving a vulnerable home short if rotating outages follow | Base trading desk or a utility VPP program: per-home reserve floors instead of one flat floor sell more MW every day | Fleet dispatcher, 18:00 on a cold-snap evening at the price cap: how deep to discharge? Slow, hold | Yes. Real: ERCOT Feb 2021 prices, NREL ResStock loads. Simulated: fleet, feeders, critical-care flags. A linear program and an MW slider, compared with a flat-floor policy | Hits the sponsor metrics: homes × hours protected and money earned per day |
| **E2 Silent Battery Triage** (02, alternate): classify silent batteries as broken, tripped or not talking, with hours of charge left | Base field service: fewer truck rolls, early warning of modem or firmware clusters | Operations-center operator at 03:00 when 18% of a county's units go silent. Watch, ask, hand to a person | Yes, but all telemetry is simulated and accuracy is measured on our own simulator | Answers the track's literal question; a twist absorber for E1 |
| **E3 Dispatch Governor** (02, alternate): an interlock that slows or quarantines fleet commands that make no physical or market sense | Base risk and trading teams: catches fat-finger and stale-price commands | On-call dispatcher at 02:10 when a fleet-wide 100% discharge order arrives at low prices. Slow, hold | Yes. Real: ERCOT prices. Simulated: a command stream with injected anomalies | "Doing what nobody authorized"; impact is hard to show |
| **C1 Callback Ladder** (03 Comms, top pick): call at-risk residents in their language before a shutoff; when nobody answers, climb retry, voicemail, alternate contact, then a ranked door-knock list | Home-care agencies, senior living and meal-delivery services buying daily check-in calls; utilities cutting door-knock costs | Overnight supervisor of a utility public-safety power shutoff line, 03:00 before a 06:00 shutoff, 400 medical-baseline homes and 2 technicians: who gets a knock? Ask, hand to a person | Yes. Real: Retell outbound calls to consenting team and judge phones. Simulated: the resident roster. A judge's phone rings live | Answers "what happens when someone doesn't pick up"; reaches landline-only and non-English residents |
| **C2 Same-Fire Filter** (03, alternate): overflow calls are matched to known incidents; only new incidents or people in danger reach a person | LA 311 or a utility outage line merging duplicate reports | Line supervisor at 02:40 with 40 calls queued and 2 call-takers. Ask, hand to a person | Yes. Real: live calls. Simulated: the replayed surge | Likely crowded; 911 vendors already sell surge deduplication |
| **C3 Ask-a-Neighbor** (03, alternate): before alerting anyone on one unverified report, call 3 to 5 opted-in night watchers nearby with one question | Utilities checking how far an outage reaches; 311 confirming a hazard before sending a truck | Supervisor at 03:10 with one report of water rushing down a street: alert 10,000 phones or not? Watch, ask | Yes. Simulated: the watcher roster | Strong on unverified alerts; who signs up is an open question |
| **P1 Trust-weighted Gate Triage** (04 Ports, top pick): rank boxes for the remaining gate capacity by cost of delay and trust in each source; a source conflict becomes a question, not a hold | Drayage dispatcher or customs broker: catches a terminal LFD earlier than the headline `pickup_lfd`, and "available" boxes that still have holds | Terminal planner when lanes drop from 8 to 4 with about 100 boxes due. Watch, ask, slow | Yes, if API access arrives. Real: holds, LFDs, availability, fees, equipment type, carrier weight. Simulated: scale weight, reefer temperature, lane capacity | Answers all three track questions and meets the real-data requirement |
| **P2 Gate Line** (04 Ports with 03 Comms, cross-track): a phone line answers "can I pick up box X?" from Terminal49 data and turns a call flood into a ranked worklist | Truckers and importers asking about availability, holds and free days | Planner at 01:00 with half the lanes down and 300 calls an hour. Ask, slow, hand to a person | Yes, but two integrations plus a public tunnel. Build P1 first; add voice after the Retell session | Ports lens; the same build could be entered under Comms |
| **P3 Plug Priority** (04 Ports with 02 Energy, cross-track): reefer and gate triage when shore power is also short | Terminal or cold-storage operator pre-cooling off-peak to cut demand charges | Planner when the grid asks the terminal to shed 200 kW. Slow, hold, hand to a person | Partly. Reefer temperatures and plug load are simulated | A reserve for a grid twist |
| **P4 Cold Clock** (04, alternate): a time-to-spoil clock per reefer | Produce or pharma importer | Reefer supervisor when a box with a USDA hold starts warming. Watch, hand to a person | Partly. The core signal is simulated, which is weak against the real-data rule | Weak on its own |

Considered and set aside:

- Marine: acoustic detection at the edge and camera confirmation. There is no
  harbor UUV data, and access to NULL's imagery is unknown.
- Energy: a feeder rotation planner (the utility's seat, no public feeder
  data) and a pre-storm charge planner (Tesla Storm Watch already does it).
- Comms: a never-automate guardrail (middleware on its own; keep it as a rule
  inside any Comms build) and an SMS text line (US texting needs A2P 10DLC
  registration).
- Ports: a go/no-go check for truckers, which is close to existing tracking
  alerts.

All top picks share one shape: collect signals, reconcile conflicting
sources, recommend the gentlest rung, and require a person to approve
anything above "slow", with an audit log. Rules run offline at 3 AM; an LLM
only parses input and explains decisions.

Brainstorm recommendation, not a team decision: P1 if Terminal49 read access
and real container numbers are confirmed tonight, with P2's voice line as a
stretch; otherwise C1. M1 is the alternative with the highest prize upside.

Checks before choosing:

- Terminal49 sponsor: an API key with read access, and real container or BL
  numbers or a pre-loaded account.
- The "Harbor Night" Extended Card from the portal.
- NULL mentors: what input their sim accepts (for M1).
- Retell: confirm the credits; set up a public tunnel to FastAPI early (C1,
  P2).

### Facts behind the ideas

The subagents read these sources on Fri 2026-10-16; the team has not
rechecked them. **Unverified** marks claims the subagents could not confirm,
took from third-party pages or gave from memory.

Marine (NULL):

- NULL Labs (<https://n0labs.com>, YC Fall 2025) sells physics-accurate
  electro-optical sensor simulation and software-in-the-loop testing,
  including maritime surface-vessel perception. Underwater and sonar work
  are not mentioned.
- MarineCadastre publishes 2024 daily AIS files (position, speed, course,
  vessel type) for US waters, including LA/LB
  (<https://github.com/ocm-marinecadastre/ais-vessel-traffic>).
- No open dataset of small UUV acoustic signatures was found, so any
  detection in a demo is simulated.
- **Unverified:** that "NULL Systems" and "NULL Labs" are the same company;
  what input format their sim accepts; that the Marine Exchange of Southern
  California co-runs LA/LB vessel traffic; HF-radar current coverage inside
  the breakwater; OpenDrift on Python 3.14; AIS type-21 encoding in `pyais`;
  a research AUV costing $100k to $1M.

Energy (Base Power):

- Base Power is a Texas retail electricity provider that owns home batteries
  (25 or 50 kWh) and bids the fleet into ERCOT
  (<https://learn.basepowercompany.com/learn/how-virtual-power-plants-work>).
  No public developer API was found.
- Anti-islanding rules (IEEE 1547, PUCT §25.211) forbid export to the grid
  during an outage, so a battery backs up only its own home.
- Texas critical-care customers are not exempt from rotating outages
  (PUCT notice).
- Tesla Storm Watch already charges batteries to 100% ahead of severe
  weather.
- **Unverified:** Base's fleet size (about 20,000 homes, 500 MWh) and a 40 MW
  Austin Energy deal; whether `gridstatus` historical ERCOT pulls need a key
  (the official ERCOT API needs a free key); Base's part in ERCOT's ADER
  pilot; truck-roll costs; per-feeder outage odds (not public, so they would
  be simulated).

Comms (Retell AI):

- The Retell API places outbound calls (`POST /v2/create-phone-call`) with
  per-call variables, reports `dial_no_answer`, `dial_busy` and
  `voicemail_reached`, calls our HTTP functions mid-call and sends signed
  webhooks (`call_ended`, `call_analyzed`). Webhooks cannot reach localhost,
  so a public tunnel is needed. `create-web-call` allows browser calls
  (<https://docs.retellai.com>).
- US business texting needs A2P 10DLC registration, and a Twilio trial only
  texts verified numbers, so judges cannot text a demo number live.
- **Unverified:** the per-minute cost ($0.07 to $0.31, typically $0.11 to
  $0.13, from third-party guides), so $10 buys about 80 minutes; whether the
  hackathon credit is Retell's standard new-account credit; support for
  Tagalog, Armenian and Farsi; how reliable the multi-language mode is;
  Carbyne's "30% fewer redundant calls" is a vendor figure.

Ports (Terminal49):

- Terminal49 API v2 (JSON:API, token auth): start tracking with
  `POST /v2/tracking_requests` (BL, booking or container number plus SCAC),
  then read containers, shipments and transport events. Webhooks include
  `container.updated`, `container.pickup_lfd.changed` and
  `container.transport.available`. The API is read-only, allows 100 requests
  per minute, and its refresh, routing and map endpoints are paid
  (<https://terminal49.com/docs>).
- Real fields: `holds_at_pod_terminal`, `fees_at_pod_terminal`,
  `pickup_lfd` and the line, terminal and rail LFDs, `available_for_pickup`,
  `terminal_checked_at`, `equipment_type` (includes reefer) and the
  carrier-declared `weight_in_lbs`.
- Not provided, so simulated: terminal scale weight, reefer temperature,
  lane status and gate capacity.
- Conflicts in real data: `pickup_lfd` prefers the line's date and can hide
  an earlier terminal LFD; `available_for_pickup` and holds can disagree;
  data goes stale (`terminal_checked_at`).
- LA/LB coverage (Terminal49 snapshot dated 2026-10-13): 13 terminals; holds
  at nearly all; no terminal LFD at TraPac and limited at LBCT and TTI;
  pickup appointments only at APM and Everport, limited at LBCT.
- Terminal49 data is shipper- and trucker-side (your own BLs), not a
  terminal's internal system.
- **Unverified, and blocking for P1 and P2:** whether reading data needs a
  paid plan or the 7-day trial (entitlements page) or works with a free
  developer key limited to 10 containers (migration guide); whether the
  sponsor provides a key or a pre-loaded account (the Hub says "1M+
  containers"); where we get real container numbers.

Decision and reasoning: [2026-10-17-005-track-and-idea.md](../changes/2026-10-17-005-track-and-idea.md).
