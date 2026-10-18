# Short welcome and fixed intake questions

* Type: implementation
* Scope: `dualuse/profiles.py`, `dualuse/holdqueue.py`, `dualuse/reception.py`,
  `dualuse/extract.py`, `dualuse/voice_bridge.py`, `dualuse/playbooks/`,
  `tests/`, `docs/architecture.md`, `docs/voice.md`
* Related: [Voice bridge](2026-10-17-010-voice-bridge.md),
  [Phone callers heard after their first word](2026-10-17-023-voice-partial-utterances.md)

## Context

* Mentor advice, relayed by the user on Sat 2026-10-17 evening: the phone
  opening was too long. It said the line was a hackathon demonstration, gave a
  queue count and a reordering notice, offered to skip questions, and ended
  with "This phone line works in English only". The mentor wanted it to say
  the caller is in the queue and let the agent start gathering information.
* The user asked that the opening still say the assistant is AI and that a
  human operator answers if the caller keeps waiting. The user also asked for
  a few fixed, 911-style questions: what is happening, where, how many people.

## Decision

* Welcome (en, es, zh): in the queue for the next available operator, stay on
  the line, AI assistant taking details for the operator, the emergency
  number, then "What is happening?". About 45 words instead of about 95 on
  the phone.
* The welcome no longer gives a queue position. That removes the reordering
  notice, which existed so a count would not mislead in tiered mode. The
  count stays in the agent's desk facts, so the agent can answer if asked.
* The voice bridge no longer speaks the demo-line notice and drops the
  Spanish and Chinese invitation from the welcome without a replacement. The
  UI and the docs still label the build as a demonstration.
* Fixed intake order in the playbook, the fallback questions and the keyword
  rules mode: situation, danger, location, how many people, need, then
  medical, disability or mobility needs. The agent skips questions the caller
  has already answered. New topic `people` and extraction field `people`
  (nullable, default null so stored calls still load); the handoff card shows
  "People: …".
* The playbook now says to repeat the emergency number only in the turn where
  danger is first reported. In the first live run the agent repeated it in
  three replies of a routine flooding call.
* Rejected: having the code ask the questions word for word. Replies would no
  longer acknowledge what the caller said, and life-safety turns already
  change the order (location right after danger).

## Verification

* Full `tests/`: **480 passed** through the WSL launcher. New tests: the fixed
  question order in the rules mode, the `People` line on the handoff card,
  welcome wording in three languages, and the phone welcome ending on its
  question.
* Live model run (`claude-haiku-5-5`, in-process `HoldQueue`, a local script
  in the git-ignored `.tmp/`). Routine flooding caller: the questions came
  in the fixed order, 1.6 to 5.1 s per turn, the schema was accepted, and
  `people` was "4, including a wife and two children". 911 was not repeated
  after the welcome. Fire with a person inside: tier IMMEDIATE, one 911
  referral, then the location and people questions.
* Not verified: a real phone call. The running desk (8000) and bridge (8010)
  still run the previous code until they are restarted.
