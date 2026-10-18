# Phone callers heard after their first word

* Type: implementation
* Scope: `dualuse/voice_bridge.py`, `tests/test_voice_bridge.py`
* Related: [Voice bridge](2026-10-17-010-voice-bridge.md), [Reception and voice reliability](2026-10-17-012-reception-reliability.md)

## Context

* Team test calls on Sat 2026-10-17 (about 17:20 PT): the desk recorded only
  the caller's first word ("Hey,", "And"), and the agent stayed silent until
  the 10 s Retell reminder.
* Retell's public logs for calls `call_8069df4c…` and `call_049d22bf…` show
  the cause. Retell sends `response_required` when the caller pauses, then
  sends it again under a new response id with the same user utterance grown
  ("Hey," then "Hey, hey, hey—my building is blowing."). The bridge counted
  user utterances, so it saw nothing new in the grown one. It answered the
  newer id with an empty, complete reply. When the desk's reply arrived on
  that closed id, Retell logged `Current response Id: undefined` and did not
  speak it.
* The agent's speech and transcription settings did not cause this.

## Decision

* Forward caller speech by comparing words, not by counting utterances:
  `unheard()` sends only the words Retell added to an utterance that was
  already forwarded. Punctuation and case changes are ignored. If the
  recognizer revised earlier words, the whole utterance is sent again.
* While a turn is running, a request that brings no new words gets no
  reply. The running turn then answers on the newest response id.
* Rejected: holding each request for a short time before calling the desk.
  That would add delay to every turn and still fail when Retell asks again
  later.

## Verification

* Two added integration tests failed on the old code with the same empty
  reply seen in the logs, and pass with the fix. Six parametrized cases in
  the `unheard()` test use utterances taken from the logs.
* Full `tests/`: **478 passed**, run through the WSL launcher.
* Replay of call `call_8069df4c…`: its 8 requests at their logged times,
  sent through the bridge to an in-process desk with a temporary database
  and a simulated 1.5 s interview. The newest request got the desk's reply,
  and the desk transcript holds every sentence.
* Not verified: a real phone call on the fixed bridge. The running bridge
  (port 8010, started 16:01) still runs the old code until it is restarted.
