# Operator text replies, a compact queue and a visible text line

* Type: implementation
* Scope: `dualuse/holdqueue.py`, `dualuse/api.py`, `dualuse/ui.py`, `tests/test_reception_desk.py`, `tests/test_api_queue.py`, `tests/test_ui.py`, `docs/architecture.md`, `docs/mentor-advice.md`, `docs/submission.md`, `README.md`
* Related: [mentor advice](../mentor-advice.md), [public map URL](2026-10-17-021-public-map-url.md)

## Context

* The mentor's feedback is mapped to the code in [mentor-advice.md](../mentor-advice.md). With the Devpost deadline at Sat 2026-10-17 22:00 PT, the team chose three small, local changes on Sat 2026-10-17 about 16:40 PT:
  * Point 9: show a real exchange between a caller and an operator. Before this change the operator could not send anything to the caller.
  * Point 8: the operator desk repeated each caller in a wide table and in an expander per caller.
  * Point 5: make the text option easy to find for a caller who cannot speak safely.
* The other points change the call lifecycle or need validation data. They are listed as next steps in the Devpost text.

## Decision

* Operator text replies:
  * `HoldQueue.operator_say` and `POST /calls/{call_id}/operator-message` (`operator_id`, `text`). Only the operator holding a confirmed (`handed_off`) call can reply. Other operators and calls not yet confirmed get 409.
  * A reply is an `operator` turn in the conversation, with an `operator_message` audit event. It is never classified and never enters the caller-only transcript that extraction, the shadow scorer and the map read.
  * Phone calls get 409: the caller cannot see text, and voice transfer is not connected.
  * The takeover card shows the latest six turns and a **Reply to the caller** box for typed calls. For simulated or replayed callers it says that nobody reads the replies.
  * The caller view shows operator turns with their own avatar and label. Its message box stays open while `connecting` and `handed_off`.
  * Caller messages after takeover keep the existing rule: saved without a model turn and flagged for review, and NORMAL becomes UNKNOWN. The flag also appears while the operator reads the exchange live. Changing the takeover rule was left out of this change.
* Compact queue:
  * One table: queue position, call, tier, wait, FIFO position, language, review flag, shadow score number and origin.
  * A **Caller details** selector opens one panel: the summary with evidence quotes, review flags, a possible shared incident from the report grouping, the scorer's explanation, the extracted fields and the conversation.
  * The selector is keyed, so the choice survives the 2 s refresh and a reordered queue. It falls back to the head of the queue when the chosen caller leaves.
  * Selector labels are the call ID, plus a phone mark, and never change while a call waits. The tier is shown in the panel instead. Streamlit 1.66 sends back the label the browser showed, so a label that changed with the tier would drop the choice.
* Review fixes after an OpenAI Codex review of the diff:
  * The caller's message box is keyed per call, so a draft survives the placeholder change at takeover.
  * A refused operator reply shows its error above the call cards, with the call ID, until the next reply or reservation. Before the fix, the error was shown inside the card, which closes when the call ends.
* Text line: the caller view says that the page plays no sound and can be used when speaking is unsafe. It is the existing browser text intake; there is no SMS and no silent phone flow.

## Verification

* New or changed tests:
  * Desk: only the operator holding a confirmed typed call can reply. The reply is saved and survives a restart, stays out of the transcript, and is refused after completion and for phone calls.
  * API: 409 before confirmation and for another operator, 422 for a blank message, 404 for an unknown call.
  * UI (AppTest): the operator's reply reaches the caller view, and the caller's answer reaches the desk. A phone call held by the operator has no reply box. The table has the compact columns, with no expander per caller. The chosen caller stays selected while the wait grows and the queue reorders, and selector labels stay the same when a tier changes. Two reports at one stated place show the shared-incident note. The caller view shows the text-line note. A reply refused after another tab completed the call still shows its error.
* Full suite in the branch worktree, `bash scripts/uv-run.sh python -m pytest tests -q` in WSL: **470 passed in 83.70 s** after the review fixes (463 before; one test replaced, seven added).
* Browser check on a separate desk, Sat 2026-10-17 about 17:00 PT: API port 8044 and UI port 8544 from the branch worktree, Claude model mode.
  * A caller reported smoke at 12 Oak Street. On a second tab, `operator-1` reserved the call and confirmed takeover.
  * Text typed in **Reply to the caller** kept its value and focus through two refreshes, then arrived.
  * The caller tab showed "Operator: …" and the caller answered. The assistant did not reply, and the operator's latest messages showed the answer.
  * A labeled 4-caller surge filled the compact table. Choosing call-4 in **Caller details** stayed selected across refreshes.
  * Moving the score column before origin was checked by test only.
* Browser check of the review fixes on the same desk, Sat 2026-10-17 about 17:20 PT:
  * With call-5 chosen in **Caller details**, a message through the API raised it from normal to immediate and moved it to the head of the queue. The panel still showed call-5 after several refreshes.
  * An unsent draft in the caller's message box stayed after `operator-2` reserved the call, while the placeholder changed to **Type a message to the operator**.
  * The refused-reply error was checked by test only.
* Deployment, Sat 2026-10-17 about 17:30 PT: committed as `a909348` on `mentor-quick-wins` and fast-forwarded `main`, not pushed.
  * API port 8000 and UI port 8501 were restarted with each old process's working directory, environment and command line. The API kept `DUALUSE_QUEUE_DB=.tmp/voice-main.sqlite3` and `DUALUSE_MAP_URL=https://demo.211deskdemo.site`; the UI kept `DUALUSE_MAP_URL`. Logs append to `.tmp/public-map-demo/`.
  * Local checks: API `/health` returned ok, and the stored desk came back (43 calls, 10 waiting, model mode). `POST /calls/no-such-call/operator-message` returned the new route's 404 "Unknown call". UI `/_stcore/health` returned ok.
  * Public checks, read only: `https://demo.211deskdemo.site/` returned 200 and showed the text-line note. The operator desk showed the compact table, **Caller details** and its panel, with no errors. The incident map frame loaded from `/plugins/map/?line=la-211`, and `/plugins/map/health` returned 200.
* Not verified: an operator reply on the public desk (it would add a call to the live desk), phone calls, and the voice bridge on port 8010 after the API restart.
