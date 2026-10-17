# Acute shortages ranked PRIORITY, room for hidden thinking, accent-insensitive quote checks

* Type: implementation
* Scope: `dualuse/playbooks/core.md`, `dualuse/extract.py` (`needs_person_soon` description),
  `dualuse/reception.py`, `scripts/evaluate_messages.py`, `docs/evaluation.md`,
  `docs/architecture.md`, tests
* Related: [evaluation 013](2026-10-17-013-real-data-evaluation.md),
  [design 009](2026-10-17-009-reception-agent-design.md) (sample checks)

## Context

* The first recorded-message evaluation (record 013, test split, first message only, proxy
  labels) found three desk weaknesses:
  * Definition gap. `needs_person_soon` named no shelter tonight, medication or oxygen, a missing
    person and a dependent left alone, and `core.md` listed "where to find water or a shelter" as
    a routine question. Requests for food, water or supplies after a disaster ranked NORMAL:
    69 of 150 needs-a-person messages and 29 of 83 rescue, medical or death messages.
  * Failed turns. 4 of 340 original-text turns stopped at `max_tokens=1600`. Of the 739 cached
    answers, 625 carried a hidden thinking block; median output 851 tokens, 63 above 1,200.
  * Dropped quotes. Claude returns Creole quotes and place names with restored accents or
    corrected spelling (`Léogâne` for `leogane`, `manje` for `MANGE`), so the exact-word check
    dropped them; 8% of needs-a-person originals had a review flag.

## Decision

* Definition, in `core.md` and in the schema description that Claude also receives: needing a
  person soon now includes the caller or people with them lacking a basic need now or by tonight
  (no shelter tonight, no food or drinking water today, medication or oxygen running out, an
  injured or sick person without care), besides a missing person or a dependent left alone. A
  question about where or how to get help, from someone who does not say they lack it now, stays
  routine, and the routine examples now name food. The same words serve an ordinary day and a
  disaster; what differs is what callers say. The offline keyword rules already ranked "no food"
  and "no water" PRIORITY.
* Tokens: `model_turn` allows 4,000 output tokens (`reception.MAX_TOKENS`); the 20 s timeout and
  no retries stay. At the measured speed (about 175 output tokens per second) 4,000 tokens take
  about as long as the timeout, so the timeout bounds a turn. Not done: turning thinking off
  (`thinking: {"type": "disabled"}` is accepted at low effort on `claude-haiku-5-5`) would bound
  latency and cost too, but it changes the model's judgment and needs its own evaluation.
* Quotes and locations: the checks drop accents on Latin letters before matching (NFD, remove
  U+0300 to U+036F after a Latin letter, NFC), so `Léogâne` matches `leogane` and `niño` matches
  `nino`. Marks that make other letters stay (Cyrillic `й`, kana voicing), Hangul still takes the
  CJK path, and respellings such as `manje` for `MANGE` are still dropped and flagged: fuzzy
  matching would let invented words through.
* Evaluation script: `--split validation` reads `disaster_response_validation.csv` and writes
  `data/processed/eval_messages_validation.json`, never the docs block or the simulator's file.
  A blank translation (validation id 14428, `related == 2`) no longer stops the run: the message
  runs on its original text only, and the results count both texts.
* Procedure: the new definitions were written before any validation message was read; one
  validation run before and one after; then the test split once.

## Verification

* Tests first. Seven new tests failed for the intended reason before the code changed: the
  split filter, the validation run that must not touch the test results or the docs block, the
  blank translation, a location and two quotes with restored accents, and an answer with 2,400
  tokens of hidden thinking (cut off at 1,600). Five guard cases passed before and after: a
  Hangul location, a respelled Creole quote, a voiced kana, a Cyrillic `й`, and the live client's
  20 s timeout without retries. The results-block test fixture gained the `split` and
  `with_english` fields that real results carry. The suite result is under Final checks.
* Validation split, Claude model mode, before (Sat 2026-10-17 14:03 PT) and after (14:12 PT),
  English translation: misses 47.3% (71/150) to 25.3% (38/150); false alarms 3.3% (5/150) to
  5.3% (8/150); rescue, medical or death ranked NORMAL 36.1% (30/83) to 19.3% (16/83); failed
  turns 1 to 0. Original text: misses 45.9% to 26.7%, false alarms 6.4% to 7.8%, failed turns 4 to
  0. The three new English false alarms read as requests that the labels mark routine.
* Test split, once (14:28 PT) against record 013's run (13:32 PT): English misses 46.0% (69/150)
  to 28.7% (43/150), false alarms 1.3% (2/150) to 3.3% (5/150), subset ranked NORMAL 34.9%
  (29/83) to 24.1% (20/83), subset IMMEDIATE 14 to 11; original text misses 43.0% to 27.5%,
  failed turns 4 to 0. All rows: [evaluation.md](../evaluation.md).
* Accent rule alone: replaying 537 baseline validation answers (old playbook and schema rebuilt,
  every request served from the cache) through the new check left every tier unchanged and cut
  original-text messages with a dropped quote from 15 to 12; dropped locations stayed at 7.
* Real turns, `claude-haiku-5-5` through a fresh `HoldQueue` with the live client settings, 18
  team-written samples (simulated callers): 18 of 18 as expected. Record 009's checks held (210
  freeway, free drinking water in Mandarin, CalFresh, rent help in Spanish: NORMAL; insulin and
  oxygen: PRIORITY; smoke in the hallway and the neighbor not breathing: IMMEDIATE), and new
  where-to questions (food bank in English and Mandarin, shelter in Spanish) stayed NORMAL, while
  no food or water since a fire or an earthquake (English, Spanish, Mandarin) and an injured
  husband who cannot see a doctor became PRIORITY. Latency 1.7 to 5.6 s, at most 1,027 output
  tokens.
* API server on port 8070 (model mode, database `.tmp/desk-fixes.sqlite3`), four first messages
  through `POST /calls`: a where-to question for drinking water stayed NORMAL and the agent asked
  whether they had no drinking water today; no food or water in Spanish, no water in Mandarin and
  a Creole message without accents became PRIORITY; no review notes, location `Leogane` kept.
* Simulator data path: `GET /evaluation` and `POST /simulate` in process on the new test results
  returned the new playbook hash and both measured policies.
* Cost: about $0.32, $0.32 and $0.33 for the three runs, under $0.02 for the real turns.
* Shared cache: `data/` is a junction to the main checkout. While the validation baseline ran,
  another session's run sent 154 of the same requests, so the cache holds two answers for those
  keys and a replay of that baseline uses the later one. The reported baseline is the run's own
  output; the attribution above skipped those keys. The test-split run has one answer per request.
  The other session was told and stopped its overlapping run.
* Not verified: 211 calls, whole conversations, latency under a surge, `claude-sonnet-5-5`, and
  the Scenario simulator page in a browser (its code is unchanged and its tests pass).

## Final checks

* Sat 2026-10-17 14:32 PT, `bash scripts/uv-run.sh python -m pytest tests -q`: 267 passed, 12 of
  them new in this change; no test calls the API.

## Follow-ups

* The schema description of `enough_information` ("said enough to judge the two risk fields")
  differs from `core.md`, and 60 of 150 routine English test messages stay UNKNOWN, which ranks
  with PRIORITY; changing it needs its own validation run.
* About a third of the remaining validation misses state a current need for food, shelter or a
  doctor that the new definition covers.
* The response cache should refuse or flag a second, different answer for the same request.
