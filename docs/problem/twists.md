# Twists

Log of the three official problem changes and our responses. The procedure
is in [../agents/twist-response.md](../agents/twist-response.md). The
organizers lifted the original six-hour rule, which made Twist 2 due Sat
10:30 and Twist 3 Sat 13:00 PT (reported by the user, Sat 2026-10-17 09:50 PT,
and stated in the Participant Hub update of Sat 2026-10-17), so all three
responses go with the final submission.

| Twist | Released (PT) | Due (PT) | Response submitted | Record |
|---|---|---|---|---|
| 1 | Fri 2026-10-16 23:30 (scheduled; text in hand by Sat 00:28) | Sat 05:30 | yes, by the user, Sat 2026-10-17 about 00:35 PT | [2026-10-17-004](../changes/2026-10-17-004-twist-1-funding-pathway.md) |
| 2 | Sat 2026-10-17 04:30 (announced) | with the final submission, Sat 2026-10-17 22:00 | no; final draft below, describes the built profile | [006](../changes/2026-10-17-006-twist-2-global.md), [017](../changes/2026-10-17-017-twist-2-final-response.md) |
| 3 | Sat 2026-10-17 07:00 (announced) | with the final submission, Sat 2026-10-17 22:00 | no; poster produced, draft below | [007](../changes/2026-10-17-007-twist-3-poster.md), [015](../changes/2026-10-17-015-poster-and-devpost.md) |

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

The first reading (a proposed China community assistance scenario, Sat
2026-10-17 morning) is in [record 006](../changes/2026-10-17-006-twist-2-global.md).
It was built the same day as a second line profile; design in
[record 009](../changes/2026-10-17-009-reception-agent-design.md), merged into
`main` in `dea860c`.

What is built:

- A line profile, chosen in the sidebar and stored on each call, changes only
  what is local. `la-211` is Los Angeles 211: English, Spanish and Mandarin;
  emergency number 911; US street addresses. `cn-12345` is China's 12345
  hotline: Mandarin and English; 110 (police), 119 (fire), 120 (ambulance);
  Chinese address order (district, road, number, compound, building, unit).
- With `cn-12345` the desk's own lines (welcome, emergency referral, handoff
  and failure notices) are in Mandarin, the agent replies in the caller's
  language and asks for the address in Chinese order. Tiers, queue order,
  handoff and the human decision are the same code in both profiles.
- Exercised Sat 2026-10-17 about 13:05 PT on a local desk in model mode
  (`claude-haiku-5-5`) with a team-written scenario. The first message,
  "我家楼下被水淹了，我奶奶腿脚不方便，出不去，水还在涨",
  made the call IMMEDIATE; the desk named 110, 119 and 120 in Mandarin; Claude
  asked for district, road, compound and building; the address
  "金水区花园路88号，3号楼2单元，她在一楼" was kept verbatim; the call ranked
  ahead of earlier Spanish PRIORITY and English NORMAL callers. Screenshots
  are in the [poster](../poster/).
- Not built or not verified: extraction fields and the operator summary are
  English by design (`dualuse/playbooks/core.md`), so a Chinese-speaking
  operator would need a localized summary; the phone path is English only;
  122 (traffic accidents) is not in the profile; the profile's English name
  says "citizen service hotline"; Mandarin quality is checked only in our own
  test conversations; local telephony, hosting, data-handling rules, dialects
  and a local partner are not covered.

Facts checked Sat 2026-10-17 between 13:00 and 13:20 PT against the sources
below (a research subagent, then direct reads of the quoted passages):

- 12345 is the local governments' hotline platform for non-emergency requests
  from businesses and the public (国办发〔2022〕12号,
  <https://www.gov.cn/zhengce/zhengceku/2022-05/16/content_5690655.htm>).
  The national name is 12345政务服务便民热线, a government service hotline;
  Beijing calls its line a citizen service hotline.
- A State Council General Office guideline merged local government service
  hotlines into the single number 12345 by the end of 2021, with 7×24 human
  service; 110, 119, 120 and 122 stay separate (国办发〔2020〕53号, dated
  2020-12-28, published 2021-01-06,
  <https://www.gov.cn/zhengce/content/2021-01/06/content_5577419.htm>).
- Requests that belong to 110, 119, 120 or 122 must be transferred to that
  line at once (国办函〔2025〕66号, dated 2025-06-23,
  <https://www.gov.cn/zhengce/content/202506/content_7029400.htm>). Since
  2022, 12345 and 110 pass calls to each other by one-click transfer
  (国办发〔2022〕12号).
- Policy fit, not an endorsement of AI triage: when call volume surges beyond
  what operators can handle, an intelligent customer-service system should
  answer frequent questions automatically and point people to online 12345
  (国办发〔2022〕12号). The 2025 guideline encourages careful use of AI large
  models for questions, form filling and follow-up, and asks for callbacks to
  missed calls and dialect seats (国办函〔2025〕66号).
- 12345 surges in disasters. Beijing's 12345 answered over 33,000
  rain-related calls from 15:00 on 29 July to 15:00 on 1 August 2023 (Beijing
  Daily, 2023-08-02, <https://news.bjd.com.cn/2023/08/02/10516308.shtml>).
  In Liaoning on 4 July 2026, flood-related requests were more than four times
  the normal level, and requests involving people trapped or electric shock
  were linked to 110, 119 and 120 at once (China News Service, 2026-07-07,
  <https://www.chinanews.com.cn/gn/2026/07-07/10654579.shtml>).
- Emergency numbers: 110 police (any emergency can be reported to 110), 119
  fire, 120 medical emergency, 122 traffic accidents (gov.cn emergency guide,
  <https://www.gov.cn/ztzl/yjzn/content_562406.htm>). Since the 2018 reform
  the fire service is a fire and rescue force that also handles other rescues
  (Fire Protection Law, art. 37); no official page was found that names 119
  as a general rescue number.
- Chinese addresses run from the largest unit (province) to the smallest
  (addressee), the reverse of the US order (Universal Postal Union addressing
  sheet for China,
  <https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/chnEn.pdf>).
- Not found: 12345 call volumes for the 2021 Zhengzhou floods; the State
  Council investigation report gives none.

Portal response draft (not submitted; submitting is the user's action):

> **Twist 2: the same desk on China's 12345 hotline.** Our build is an AI
> reception desk for the hold queue of a community and disaster line. While
> callers wait, Claude talks with them in their language and records what is
> happening, where, who is in danger and what they need; fixed code ranks the
> queue; a person takes over with a summary. For Twist 2 we added line
> profiles to the running demo. Next to Los Angeles 211 there is now a profile
> for China's 12345 government service hotline (12345政务服务便民热线), the
> local-government line for non-emergency requests. The profile changes only
> what is local: the desk's own lines and the agent's replies are in Mandarin
> (English stays available), callers in danger are told to call 110 (police),
> 119 (fire) or 120 (ambulance), and addresses are asked for in Chinese order
> (district, road, number, compound, building, unit). Tiers, queue order,
> handoff and the rule that a person makes every decision are the same code
> for both lines.
>
> Why it fits: 12345 must pass emergencies to 110, 119, 120 or 122 at once
> (国办函〔2025〕66号), and it surges in disasters: Beijing's 12345 answered
> over 33,000 rain-related calls in 72 hours in July 2023 (Beijing Daily).
> A 2022 State Council guideline (国办发〔2022〕12号) already asks 12345 to
> answer frequent questions automatically when calls outnumber operators.
>
> In the demo, a Mandarin caller reports a flooded ground floor and a
> grandmother who cannot get out. The desk names 110, 119 and 120, ranks the
> call Immediate ahead of earlier, less urgent callers, and Claude asks for the
> district, road, compound and building; the operator sees the caller's words
> and address verbatim. Limits: this is a prototype, not a deployed 12345
> service. Mandarin replies were checked in our own test conversations, not
> measured; operator summaries are in English; phone calls are English only;
> local telephony, hosting, data rules, dialects and a local partner are not
> covered. We do not automate dispatch or the operator's decision.

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

The first reading is in [record 007](../changes/2026-10-17-007-twist-3-poster.md).
The poster was produced Sat 2026-10-17 by 13:30 PT:

- Files: [poster.pdf](../poster/poster.pdf) (one 24 × 36 in portrait page)
  and [poster.png](../poster/poster.png) (3600 × 5400 px, 2 MB), exported from
  [poster.html](../poster/poster.html); the export command is in
  [submission.md](../submission.md#poster).
- Format: the Participant Hub (last updated Sat 2026-10-17) lists "Optional but
  recommended: POSTER PDF" and offers printing; it names no size. 24 × 36 in
  is our choice; the PDF scales to any 2:3 print size.
- Content: the 211 LA surge figures, the caller-to-operator flow with who
  decides each step (Claude, code, a person), four screenshots of the running
  desk captured Sat 2026-10-17 between 13:00 and 13:15 PT, the ordinary-day
  and crisis uses, the China 12345 profile, what is never automated, and what
  is not built or measured. Team-written scenarios and the simulated and
  recorded surge inputs are labeled; there are no accuracy or wait-time claims.
- The Hub's update of Sat 2026-10-17 says twists no longer need responses
  within six hours, so this response goes with the final submission.
- Not checked: the live Devpost form, including whether it has a separate
  poster field; print output at full size. The team name is not on the poster.

Portal response draft (not submitted; submitting is the user's action):

> **Twist 3: our poster.** We made a 24 × 36 inch portrait poster (PDF,
> submitted with our Devpost project) for printing on Demo Day. It explains
> the build in one pass: the problem (on 8 January 2025, during the Eaton and
> Palisades fires, 211 LA was offered 7,815 contacts; 60.66% were abandoned
> and the average wait was 1 h 23 min, per its after-action report), the flow
> from a waiting caller to a Claude interview, rule-based ranking in code and
> a human takeover, four screenshots of our running desk, the ordinary-day and
> crisis uses of the same build, and the China 12345 profile from Twist 2. The
> screenshots come from the live demo on Saturday; the conversations are
> team-written test scenarios and the surge mixes team-written scripts
> (simulated) with recorded disaster messages, and the poster labels them so.
> It also lists what is never automated and what is not built or measured
> yet: we claim no accuracy or wait-time gains.
