# Evaluation on recorded disaster messages

Results for the desk as changed in [record 016](changes/2026-10-17-016-desk-tier-definitions-and-checks.md),
Sat 2026-10-17 PT, next to the first run ([record 013](changes/2026-10-17-013-real-data-evaluation.md)).
The question: given a caller's first message, how often
does the desk rank someone who needs a person as routine, and how often does it put a routine
message ahead of others? The messages are SMS sent after the 2010 Haiti earthquake and Pakistan
floods and Hurricane Sandy message-board posts, scored against proxy labels. They are not 211
calls, so these numbers are not 211 accuracy.

## Data and labels

* Source: Munro disaster response messages, test split only, `genre == "direct"` (messages, not
  news headlines): 1,069 rows. Two Sandy posts appear twice, so 1,067 distinct messages. Per the
  dataset README, the Haiti and Pakistan messages are SMS sent to disaster reporting services in
  2010 and the Sandy messages are posts on an online disaster message board. CC BY 4.0; cite Robert Munro (2012),
  *Processing short message communications in low-resource languages*, Stanford University.
  Provenance and checksum: [datasets.md](datasets.md). The script refuses a file whose SHA-256
  differs from the manifest.
* Proxy labels from the dataset's categories:
  * needs a person: `request == 1` (421 distinct messages);
  * routine: `request == 0` (646);
  * rescue, medical or death subset: `request == 1` and any of `search_and_rescue`,
    `medical_help` or `death` (83), the closest proxy for danger the labels offer.
* Each message exists as `message`, the published English translation, and `original`, the text
  as sent (mostly Haitian Creole, some French; romanized Urdu for Pakistan; Sandy messages have no
  original). The README notes that the translations are not all literal: some summarize, add
  exposition or write out categories.
* Validation split, used to check desk changes before the test split runs: the same filter and
  labels give 1,047 distinct direct messages (342 needs a person, 705 routine, 83 in the subset).
  One of them (id 14428, `related == 2`, "unsure") has a blank translation; like a Sandy message
  without an original, it runs only on the text it has.

## Method

* Sample, seed 7: 150 needs-a-person and 150 routine messages drawn at random from the distinct
  messages, plus every message of the rescue, medical or death subset. Class rates use only the class sample; subset rates use
  the whole subset.
* Each message joins a fresh desk (`HoldQueue`, LA 211 profile) and speaks once. The desk's own
  path runs: its facts for the turn, the quote and location checks, the tier rules and its
  failure handling. Methods:
  * FIFO: serves in arrival order, so nobody is ranked ahead. Its rates hold by construction.
  * Offline keyword rules: the desk's offline mode (`reception.receive` in `rules` mode, which
    calls `extract.classify_with_rules`).
  * Claude model mode: the desk's `reception.model_turn` with `claude-haiku-5-5` and the
    playbooks, as in the live demo. Its request allows 4,000 output tokens (1,600 in the first
    run), because hidden thinking counts against the limit.
* Both methods run on the English translation and on the original text.
* Desk changes are judged on the validation split (`--split validation`, same sampling), and the
  test split runs once afterwards. A validation run writes
  `data/processed/eval_messages_validation_claude-haiku-5-5.json`; only a test-split run with the desk model writes the results block
  below and `data/processed/eval_messages.json`, which the simulator reads.
* The script also supports `--split train` and `--model claude-sonnet-5-5` for comparisons. Non-published runs use `eval_messages_<split>_<model>.json` and each model has its own cache.
* Raw Claude responses are cached by request in `data/processed/eval_messages_cache.jsonl`, so a
  rerun with unchanged playbooks replays the same answers through the current code for free. The
  evaluation client allows 60 s and three retries per request (the live desk: 20 s, none); latency
  is not measured.
* An incomplete or malformed Claude answer counts as a failed turn, which the desk ranks UNKNOWN and
  flags, as it would live. An API or network error stops the run instead of becoming a result.

## Metrics

* Miss rate: share of needs-a-person messages ranked NORMAL.
* False-alarm rate: share of routine messages ranked IMMEDIATE or PRIORITY.
* Routine ranked ahead: share of routine messages ranked IMMEDIATE, PRIORITY or UNKNOWN. UNKNOWN
  shares PRIORITY's queue rank, so for waiting times it acts like a false alarm.
* Rescue, medical or death ranked NORMAL: the miss rate on the subset.
* Review flag: the desk stored at least one review note for the operator, such as a dropped quote,
  a dropped location or a failed turn.
* Intervals are 95% Wilson score intervals.

## Results

<!-- results:start, written by scripts/evaluate_messages.py -->
Generated Sat 2026-10-17 14:28 PT by `scripts/evaluate_messages.py`. Recorded 2010 Haiti and Pakistan SMS and Hurricane Sandy message-board posts (Munro test split, direct messages, CC BY 4.0, Robert Munro 2012) with proxy category labels, first message only; not 211 calls.

* Population: 1,067 distinct direct messages of the test split: 421 needs a person, 646 routine, 83 in the rescue, medical or death subset.
* Sample (seed 7): 150 needs-a-person and 150 routine messages, plus every subset message; 355 messages evaluated (28 subset messages were already in the class sample). Events: haiti_earthquake 336, usa_sandy 14, pakistan_floods 5.
* English text exists for 355 and original text for 340 of them; Sandy messages have no original.
* Claude: 691 distinct responses from claude-haiku-5-5 (688 sent in this run, the rest replayed from the cache); 161,885 uncached input, 2,033,291 cache-read, 23,816 cache-write and 571,715 output tokens; about $0.33 at list price.

Rates with 95% Wilson intervals, as rate (count/n; interval):

| Method | Text | Miss: needs a person ranked NORMAL | False alarm: routine ranked IMMEDIATE or PRIORITY | Routine ranked ahead of NORMAL, UNKNOWN included | Rescue, medical or death ranked NORMAL | Review flag, needs a person | Review flag, routine | Failed turns |
|---|---|---|---|---|---|---|---|---:|
| FIFO (reference) | English translation | 100% by construction | 0% by construction | 0% by construction | 100% by construction | n/a | n/a | n/a |
| FIFO (reference) | Original text | 100% by construction | 0% by construction | 0% by construction | 100% by construction | n/a | n/a | n/a |
| Offline keyword rules | English translation | 1.3% (2/150; 0.4-4.7%) | 1.3% (2/150; 0.4-4.7%) | 99.3% (149/150; 96.3-99.9%) | 1.2% (1/83; 0.2-6.5%) | 0.0% (0/150; 0.0-2.5%) | 0.0% (0/150; 0.0-2.5%) | 0 |
| Offline keyword rules | Original text | 0.0% (0/149; 0.0-2.5%) | 0.0% (0/137; 0.0-2.7%) | 100.0% (137/137; 97.3-100.0%) | 0.0% (0/82; 0.0-4.5%) | 0.7% (1/149; 0.1-3.7%) | 0.0% (0/137; 0.0-2.7%) | 0 |
| Claude model mode (claude-haiku-5-5) | English translation | 28.7% (43/150; 22.0-36.4%) | 3.3% (5/150; 1.4-7.6%) | 43.3% (65/150; 35.7-51.3%) | 24.1% (20/83; 16.2-34.3%) | 0.7% (1/150; 0.1-3.7%) | 1.3% (2/150; 0.4-4.7%) | 0 |
| Claude model mode (claude-haiku-5-5) | Original text | 27.5% (41/149; 21.0-35.2%) | 4.4% (6/137; 2.0-9.2%) | 52.6% (72/137; 44.2-60.7%) | 22.0% (18/82; 14.4-32.1%) | 7.4% (11/149; 4.2-12.7%) | 5.1% (7/137; 2.5-10.2%) | 0 |

Tiers the desk stored after the first message:

| Method | Text | Messages | n | IMMEDIATE | PRIORITY | UNKNOWN | NORMAL |
|---|---|---|---:|---:|---:|---:|---:|
| Offline keyword rules | English translation | needs a person (sample) | 150 | 2 | 7 | 139 | 2 |
| Offline keyword rules | English translation | routine (sample) | 150 | 1 | 1 | 147 | 1 |
| Offline keyword rules | English translation | rescue, medical or death (all) | 83 | 1 | 5 | 76 | 1 |
| Offline keyword rules | Original text | needs a person (sample) | 149 | 0 | 1 | 148 | 0 |
| Offline keyword rules | Original text | routine (sample) | 137 | 0 | 0 | 137 | 0 |
| Offline keyword rules | Original text | rescue, medical or death (all) | 82 | 0 | 0 | 82 | 0 |
| Claude model mode (claude-haiku-5-5) | English translation | needs a person (sample) | 150 | 8 | 77 | 22 | 43 |
| Claude model mode (claude-haiku-5-5) | English translation | routine (sample) | 150 | 0 | 5 | 60 | 85 |
| Claude model mode (claude-haiku-5-5) | English translation | rescue, medical or death (all) | 83 | 11 | 42 | 10 | 20 |
| Claude model mode (claude-haiku-5-5) | Original text | needs a person (sample) | 149 | 10 | 73 | 25 | 41 |
| Claude model mode (claude-haiku-5-5) | Original text | routine (sample) | 137 | 0 | 6 | 66 | 65 |
| Claude model mode (claude-haiku-5-5) | Original text | rescue, medical or death (all) | 82 | 15 | 37 | 12 | 18 |

Review notes in model mode (messages with at least one note of each kind, all evaluated messages):

| Text | Unverified quotes dropped | Location not in the caller's words | Life threat reported without a verified caller quote | Reply withheld because it made a promise | Interview failed |
|---|---:|---:|---:|---:|---:|
| English translation | 2 | 3 | 0 | 0 | 0 |
| Original text | 12 | 11 | 1 | 0 | 0 |

Language codes Claude reported for the original text: `ht` 292, `fr` 35, `en` 8, `es` 2, `ur` 2, `hi-Latn` 1.
<!-- results:end -->

## Before and after the desk fixes

The first run ([record 013](changes/2026-10-17-013-real-data-evaluation.md)) found three desk
weaknesses, which [record 016](changes/2026-10-17-016-desk-tier-definitions-and-checks.md) changed:

* Definitions. `needs_person_soon` named no shelter tonight, medication or oxygen, a missing person
  and a dependent left alone, and "where to find water or a shelter" was a routine question, so
  requests for food, water or supplies after a disaster read as routine. It now also covers the
  caller or people with them lacking food or drinking water today or care for an injured or sick
  person; a question about where or how to get help, without saying they lack it now, stays
  routine ([core.md](../dualuse/playbooks/core.md) and the schema description in
  `dualuse/extract.py`).
* Failed turns. Answers stopped at the 1,600-token limit, most of it hidden thinking; the desk
  now allows 4,000.
* Dropped quotes. Claude restores accents (`Léogâne` for `leogane`); the quote and location checks
  now ignore accents on Latin letters. Respellings (`manje` for `MANGE`) still fail.

"Before" is the desk of record 013 (playbook prompt SHA-256 `3b5a1cd383f3...`), "after" this desk
(`b6eceae00cf6...`). One run each on the same sample (seed 7): validation Sat 2026-10-17 14:03 and
14:12 PT, test 13:32 PT (record 013) and 14:28 PT. Recorded messages, proxy labels, first message
only; not 211 accuracy.

English translation:

| Claude model mode | Validation, before | Validation, after | Test, before | Test, after |
|---|---|---|---|---|
| Miss: needs a person ranked NORMAL | 47.3% (71/150) | 25.3% (38/150) | 46.0% (69/150) | 28.7% (43/150) |
| False alarm: routine ranked IMMEDIATE or PRIORITY | 3.3% (5/150) | 5.3% (8/150) | 1.3% (2/150) | 3.3% (5/150) |
| Routine ranked ahead of NORMAL, UNKNOWN included | 44.7% (67/150) | 46.7% (70/150) | 46.7% (70/150) | 43.3% (65/150) |
| Rescue, medical or death ranked NORMAL | 36.1% (30/83) | 19.3% (16/83) | 34.9% (29/83) | 24.1% (20/83) |
| Rescue, medical or death ranked IMMEDIATE | 16 of 83 | 13 of 83 | 14 of 83 | 11 of 83 |
| Review flag, needs a person | 1.3% (2/150) | 2.7% (4/150) | 2.0% (3/150) | 0.7% (1/150) |
| Review flag, routine | 2.0% (3/150) | 2.0% (3/150) | 2.0% (3/150) | 1.3% (2/150) |
| Failed turns | 1 | 0 | 0 | 0 |

Original text:

| Claude model mode | Validation, before | Validation, after | Test, before | Test, after |
|---|---|---|---|---|
| Miss: needs a person ranked NORMAL | 45.9% (67/146) | 26.7% (39/146) | 43.0% (64/149) | 27.5% (41/149) |
| False alarm: routine ranked IMMEDIATE or PRIORITY | 6.4% (9/141) | 7.8% (11/141) | 4.4% (6/137) | 4.4% (6/137) |
| Routine ranked ahead of NORMAL, UNKNOWN included | 53.2% (75/141) | 51.8% (73/141) | 47.4% (65/137) | 52.6% (72/137) |
| Rescue, medical or death ranked NORMAL | 30.9% (25/81) | 18.5% (15/81) | 32.9% (27/82) | 22.0% (18/82) |
| Rescue, medical or death ranked IMMEDIATE | 12 of 81 | 16 of 81 | 15 of 82 | 15 of 82 |
| Review flag, needs a person | 14.4% (21/146) | 13.0% (19/146) | 8.1% (12/149) | 7.4% (11/149) |
| Review flag, routine | 4.3% (6/141) | 4.3% (6/141) | 5.8% (8/137) | 5.1% (7/137) |
| Failed turns | 4 | 0 | 4 | 0 |

The keyword rows did not change: the offline rules were not touched.

## Reading the results

* The offline keyword rules prioritize almost nothing on these messages. They rank 139 of 150
  needs-a-person and 147 of 150 routine English messages UNKNOWN, and nearly every original.
  Their misses are rare only because almost everyone shares PRIORITY's rank, which in the queue
  is close to FIFO. Their routine keywords (FEMA, CalFresh, freeway) are Los Angeles words.
* Claude now ranks 85 of 150 needs-a-person messages IMMEDIATE or PRIORITY (63 in the first run)
  against 5 of 150 routine ones (2), and 43 of 150 (28.7%) NORMAL (69, 46.0%). The validation
  split moved the same way (misses 47.3% to 25.3%), and its new definitions were written before
  any validation message was read. Requests for food, water, tents or care now read as lacking a
  basic need.
* What stays NORMAL, from a read-through of the 38 validation misses (this session, not a label):
  about a third state a current need that the new definition covers and Claude still ranked
  routine ("now I'm hungry. Please send me something to eat", "we need foods and tents", "WE NEED
  A DOCTOR IN ARCAHAIE"); the rest ask for information (passports, travel, which number to call,
  where to find a tent), jobs, documents or electricity, complain about aid, or offer help.
* The new false alarms on validation read as requests that the labels mark routine ("We need
  food, water, money, energy, please around Santo", police officers without a tent, a sick
  caller without money for the hospital).
* In the rescue, medical or death subset, NORMAL fell from 29 to 20 of 83 (English) and IMMEDIATE
  from 14 to 11; on the original text IMMEDIATE stayed at 15. Wording an injured or sick person
  without care as PRIORITY may pull some medical reports down from IMMEDIATE; with one run per
  desk this is not separable from run-to-run variation (validation: 16 to 13 English, 12 to 16
  original).
* Failed turns went from 4 to 0 on the test originals and from 5 to 0 on validation with the
  4,000-token limit. Original-text messages with a dropped quote fell from 15 to 12 on the test
  split. Replaying 537 baseline validation answers (old playbook, so the same answers) through the
  new check isolates the accent rule: original-text messages with a dropped quote 15 to 12,
  dropped locations unchanged at 7, English unchanged, no tier changed. The remaining drops are
  mostly respellings or translations, which the check still refuses.
* Ordinary day: in team-written samples (record 016), where-to questions for drinking water, a
  food bank, a shelter, CalFresh and rent help stayed NORMAL in English, Spanish and Mandarin,
  while callers without food or water since a fire or an earthquake became PRIORITY in all three
  languages. These are simulated callers, not a measurement.
* None of this is 211 accuracy. On recorded disaster messages a single first turn now leaves
  about a quarter of danger-proxy messages NORMAL, still far from the 5% miss rate the simulator
  assumed.

## Use in the scenario simulator

The Scenario simulator shows the table above and, next to the assumed policies, replays two
measured ones on the same simulated surge. Each simulated caller gets a tier drawn from the tiers
the desk gave recorded messages of the matching proxy class: a true IMMEDIATE caller from the
rescue, medical or death subset, PRIORITY from the needs-a-person sample, NORMAL from the routine
sample, using the English translation or the original text. This keeps UNKNOWN, which ranks with
PRIORITY, and IMMEDIATE callers who were not ranked IMMEDIATE, which a miss rate alone would hide.
The surge itself (arrivals, tier mix, patience) stays simulated. The headline metrics show
immediate callers who hung up beside P95 waits, because a wait only counts callers who stayed.

## Limits

* Proxy labels. `request` marks a message that asks for something; it is not a 211 urgency
  label. A desk that ranks "we need food" as a routine request counts as a miss. The rescue,
  medical or death subset is closer to danger but still includes hunger and illness reports.
* Routine messages include offers of help, relayed news and unrelated texts. Twelve messages
  with a rescue, medical or death tag but `request == 0` count as routine.
* One turn. The live desk asks follow-up questions; here a vague first message stays UNKNOWN.
  UNKNOWN ranks with PRIORITY, so these results overstate how many routine callers wait ahead
  of NORMAL ones, and they cannot show what a follow-up question would have revealed.
* Population. 92% of the direct test messages come from the 2010 Haiti earthquake, mostly with
  Haitian Creole originals. Not Los Angeles, not 211, not phone speech.
* Translations. Where a translator summarized or wrote out a category, the English text can be
  easier to rank than what the sender wrote; the original-text rows avoid that.
* Sample size. 150 messages per class give intervals up to about 8 points either side (at
  rates near 50%, less near 0% or 100%); the subset has 83 messages.
* The simulator maps true tiers to proxy classes. The rescue, medical or death subset stands in
  for IMMEDIATE callers although many of its messages describe no danger now, so the measured
  policies probably understate how often a real IMMEDIATE caller would be ranked IMMEDIATE. The
  assumed policies still use the two-rate model (misses and false alarms only).
* The keyword rules read English only. Their original-text rows show that limit; they are not
  a tuning target.
* Claude's answers can vary between runs. The cache fixes one set of answers; a run without it
  draws new ones. Each before or after figure above is one run.
* Desk changes. The fixes of record 016 were written from the first run's test-split errors,
  which two sessions read message by message, and were checked on the validation split before
  the test split ran again. The new definitions were written before any validation message was
  read, so the validation rows are the cleaner before-and-after comparison; the test rows are not
  a fully independent check.
* Replays. While the validation baseline ran, an overlapping run in another session sent 154 of
  the same requests. The cache keeps both answers and replays the later one, so a replay of that
  baseline differs from it on those turns; the reported baseline is the run's own output.

## Reproduce

```text
bash scripts/uv-run.sh env -u ANTHROPIC_API_KEY python scripts/evaluate_messages.py
bash scripts/uv-run.sh env -u ANTHROPIC_API_KEY python scripts/evaluate_messages.py --split validation
```

`env -u` lets `dualuse.config` read the key from `.env` when WSLENV forwards an empty variable.
The test run writes `data/processed/eval_messages.json` (summaries and one row per message, method
and text) and the results block above; the validation run writes only its own file. From a
worktree, add `PYTHONPATH=.` after `env` so the worktree's `dualuse` is imported. Run one
evaluation at a time: worktrees link `data/` to the main checkout, so every run appends to the
same cache file.
