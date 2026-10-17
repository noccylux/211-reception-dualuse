# Twists

Log of the three official problem changes and our responses. The procedure
is in [../agents/twist-response.md](../agents/twist-response.md). The
"Due" column shows the original six-hour rule; the organizers lifted it
(reported by the user, Sat 2026-10-17 09:50 PT), so all three responses go
with the final submission.

| Twist | Released (PT) | Due (PT) | Response submitted | Record |
|---|---|---|---|---|
| 1 | Fri 2026-10-16 23:30 (scheduled; text in hand by Sat 00:28) | Sat 05:30 | yes, by the user, Sat 2026-10-17 about 00:35 PT | [2026-10-17-004](../changes/2026-10-17-004-twist-1-funding-pathway.md) |
| 2 | Sat 2026-10-17 04:30 (announced) | Sat 2026-10-17 10:30 | no; draft below | [2026-10-17-006](../changes/2026-10-17-006-twist-2-global.md) |
| 3 | Sat 2026-10-17 07:00 (announced) | Sat 2026-10-17 13:00 portal response under the standing rule; poster Sat 2026-10-17 22:00 | no; draft below | [2026-10-17-007](../changes/2026-10-17-007-twist-3-poster.md) |

## Twist 1

Official text (verbatim, as received by the team):

> Twist #1: Identify the government funding pathway for your venture.
>
> Many startups find their first funding through government agencies like
> NASA, DHS, USDA, etc. They also find them through different funding
> programs such as DARPA and NSF project funding platforms.
>
> Identify at least one federal funding pathway in the US government whether
> through an agency, program, or military sector as your primary or
> alternative funding source to launch your venture.

Impact on the build:

- A venture twist, not a technical one. It changes the pitch and the
  "feasibility and impact" story; the triage design itself is unchanged.
- The one build-visible change we plan: the demo gets a selectable line
  profile (a 211 disaster line and an installation emergency line) so the
  same unchanged build shows the civilian customer and the defense end user
  that the AFWERX pathway requires. This is planned, not built; it goes into
  [../architecture.md](../architecture.md) with the code.
- Facts checked Sat 2026-10-17 00:30 PT: SBIR/STTR were reauthorized on
  2026-04-13 through 2031-09-30 after a six-month lapse, so SBIR routes are
  open again. DHS S&T SBIR has run NG911 topics before (FY20 topic
  DHS201-001, "NG 9-1-1 Multimedia Content Analysis Engine"). AFWERX Open
  Topic Phase I is about $75k for a 3-month feasibility study and needs an
  Air Force end user's Customer Memorandum. Not verified: the FY2026 DHS
  topic list, the 2026 AFWERX Open Topic dates, and the current NSF Phase I
  schedule; check SAM.gov and the program pages before the pitch.

Response (as submitted by the user on the portal, Sat 2026-10-17 about
00:35 PT):

> Primary pathway: the DHS Science and Technology Directorate SBIR program.
> Our venture is an AI assistant for the hold queue of overloaded public
> service and emergency lines: it talks to callers while they wait, tiers
> them for human attention, never hangs up, and hands off to the operator
> with a summary. That sits in DHS S&T's first-responder and NG911 topic
> line (for example FY20 topic DHS201-001, "NG 9-1-1 Multimedia Content
> Analysis Engine"). SBIR/STTR were reauthorized on April 13, 2026 through
> FY2031, so a Phase I feasibility award with a 211 or PSAP partner is our
> launch funding; we will confirm the FY2026 topic list on SAM.gov.
>
> Alternative pathways: (1) AFWERX SBIR Open Topic (Department of the Air
> Force), which funds dual-use commercial technology with an Air Force end
> user. Installation emergency communications centers face the same surge
> problem; Phase I is a 3-month feasibility study that requires a Customer
> Memorandum from such a unit, and our demo already shows that profile.
> (2) NSF SBIR/STTR (America's Seed Fund) as the agency-agnostic route.
>
> Customer-side money: FEMA Emergency Management Performance Grants and the
> federal 911 Grant Program (NHTSA/NTIA) fund the agencies that would buy
> the tool, so pricing targets those budgets.

## Twist 2

Official text (verbatim, supplied by the user Sat 2026-10-17; HTML entities
decoded):

> **Twist 2: Let's make it global.**
> Dropped Sat 4:30 AM
>
> Your solution is good, see how it applies to a global application. How does the same solution hold up in another part of the world? For example, if you are solving for fire-fighters in Los Angeles, how can ones in China implement it?

Impact and proposed response; not implemented:

- The [chosen seat](brief.md#tracks) remains a community and disaster
  assistance line supervisor. A proposed second setting is a community
  assistance hotline in China, serving routine assistance requests and a
  flood-related surge. No local agency partnership is claimed.
- Keep the same queue policy and human decision boundary. Localize the
  interview language, address fields, service directory and operator
  summary. A US phone number or service directory must not be assumed to
  work in another country.
- Smallest visible demo: paired English and Mandarin synthetic requests
  with equivalent needs and arrival times, passing through extraction and
  the same deterministic rules. Show extracted fields, queue order and
  handoff summaries. Unclear language or location must remain explicit and
  receive human attention, rather than silently becoming a normal request.
- This tests language equivalence, not deployment readiness. Local
  telephony/provider access, hosting and data handling requirements,
  dialects, local service routing and operation during network loss remain
  unverified. Local text replay would not demonstrate offline voice.
- Prefer one second-region scenario over a broad country selector: it is
  faster to validate and gives the judges observable evidence. A production
  China deployment and additional languages are deferred.
- Current [architecture](../architecture.md) is still a scaffold. Record
  these capabilities there only when implemented and exercised.

Portal response draft (not submitted; describes the proposed adaptation):

> We are extending our hold-queue assistant from an LA community assistance
> line to a community assistance hotline in China. On an ordinary day it
> would gather routine assistance needs; during flooding, the same build
> would help the supervisor identify callers needing human attention.
> Our design keeps queue rules and human control unchanged, while adapting
> language, address capture, local service information and handoff summaries.
> Our planned demonstration pairs English and Mandarin synthetic requests
> with equivalent needs, compares their extracted fields and queue order,
> and flags uncertain information for human review. This is a prototype
> adaptation, not a deployed Chinese hotline: local telephony, hosting,
> data handling and dialect support still require validation with a local
> partner. We do not automate dispatch or the operator's final decision.

## Twist 3

Official text (verbatim, supplied by the user Sat 2026-10-17; HTML entities
decoded):

> **Twist 3: POSTER IT!**
> Dropped Sat 7:00 AM
>
> Visualization is a big part of how we communicate ideas better. Make a poster for your solution, doesn't have to be anything fancy and submit it with your Devpost submission today @ 10 PM. If you do, we'll get it printed for DEMO DAY on Sunday.
>
> Devpost will be modified to allow poster submission by 1.00 PM.
>
> Whether finalist or not, we have 4 open awards AND The Best Demo is one of them!

Impact and proposed response; poster not yet produced:

- Add a printable poster to the submission. Its purpose is to explain the
  caller-to-operator flow, ordinary-day and crisis uses, and the proposed
  global adaptation at a glance. Copy outline is in
  [submission.md](../submission.md#poster).
- Poster deadline is explicitly Sat 2026-10-17 22:00 PT; organizers say the
  upload field will be available by Sat 2026-10-17 13:00 PT. Availability
  has not been checked. Size, file format and upload limits were not given.
- The standing six-hour portal-response rule yields Sat 2026-10-17 13:00
  PT. The announcement does not explicitly waive that separate response;
  keep it distinct from the poster deadline pending organizer clarification.
- Use actual screenshots and measured results only when available. Label
  planned behavior and synthetic examples. Do not claim reduced wait times,
  reliable multilingual extraction or functioning voice transfer without
  evidence from the build.

Portal response draft (not submitted):

> We plan to submit a poster with our Devpost project by 10 PM PT today.
> It will show our hold-queue assistant's intended flow: interview waiting
> callers, identify who needs human attention, and hand context to the
> operator. We will contrast ordinary community assistance with a disaster
> surge and show how the same design can be adapted to a second region.
> The poster will distinguish verified prototype behavior from planned
> features and label all simulated examples. It will support our Sunday
> live demo, whether or not we are finalists.
