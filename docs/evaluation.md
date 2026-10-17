# Evaluation on recorded disaster messages

Results of one run, Sat 2026-10-17 PT. The question: given a caller's first message, how often
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
    playbooks, as in the live demo.
* Both methods run on the English translation and on the original text.
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
Generated Sat 2026-10-17 13:32 PT by `scripts/evaluate_messages.py`. Recorded 2010 Haiti and Pakistan SMS and Hurricane Sandy message-board posts (Munro test split, direct messages, CC BY 4.0, Robert Munro 2012) with proxy category labels, first message only; not 211 calls.

* Population: 1,067 distinct direct messages of the test split: 421 needs a person, 646 routine, 83 in the rescue, medical or death subset.
* Sample (seed 7): 150 needs-a-person and 150 routine messages, plus every subset message; 355 messages evaluated (28 subset messages were already in the class sample). Events: haiti_earthquake 336, usa_sandy 14, pakistan_floods 5.
* Original text exists for 340 of them; Sandy messages have none.
* Claude: 691 distinct responses from claude-haiku-5-5 (0 sent in this run, the rest replayed from the cache); 161,885 uncached input, 1,953,457 cache-read, 0 cache-write and 566,252 output tokens; about $0.32 at list price.

Rates with 95% Wilson intervals, as rate (count/n; interval):

| Method | Text | Miss: needs a person ranked NORMAL | False alarm: routine ranked IMMEDIATE or PRIORITY | Routine ranked ahead of NORMAL, UNKNOWN included | Rescue, medical or death ranked NORMAL | Review flag, needs a person | Review flag, routine | Failed turns |
|---|---|---|---|---|---|---|---|---:|
| FIFO (reference) | English translation | 100% by construction | 0% by construction | 0% by construction | 100% by construction | n/a | n/a | n/a |
| FIFO (reference) | Original text | 100% by construction | 0% by construction | 0% by construction | 100% by construction | n/a | n/a | n/a |
| Offline keyword rules | English translation | 1.3% (2/150; 0.4-4.7%) | 1.3% (2/150; 0.4-4.7%) | 99.3% (149/150; 96.3-99.9%) | 1.2% (1/83; 0.2-6.5%) | 0.0% (0/150; 0.0-2.5%) | 0.0% (0/150; 0.0-2.5%) | 0 |
| Offline keyword rules | Original text | 0.0% (0/149; 0.0-2.5%) | 0.0% (0/137; 0.0-2.7%) | 100.0% (137/137; 97.3-100.0%) | 0.0% (0/82; 0.0-4.5%) | 0.7% (1/149; 0.1-3.7%) | 0.0% (0/137; 0.0-2.7%) | 0 |
| Claude model mode (claude-haiku-5-5) | English translation | 46.0% (69/150; 38.2-54.0%) | 1.3% (2/150; 0.4-4.7%) | 46.7% (70/150; 38.9-54.6%) | 34.9% (29/83; 25.6-45.7%) | 2.0% (3/150; 0.7-5.7%) | 2.0% (3/150; 0.7-5.7%) | 0 |
| Claude model mode (claude-haiku-5-5) | Original text | 43.0% (64/149; 35.3-51.0%) | 4.4% (6/137; 2.0-9.2%) | 47.4% (65/137; 39.3-55.8%) | 32.9% (27/82; 23.7-43.7%) | 8.1% (12/149; 4.7-13.5%) | 5.8% (8/137; 3.0-11.1%) | 4 |

Tiers the desk stored after the first message:

| Method | Text | Messages | n | IMMEDIATE | PRIORITY | UNKNOWN | NORMAL |
|---|---|---|---:|---:|---:|---:|---:|
| Offline keyword rules | English translation | needs a person (sample) | 150 | 2 | 7 | 139 | 2 |
| Offline keyword rules | English translation | routine (sample) | 150 | 1 | 1 | 147 | 1 |
| Offline keyword rules | English translation | rescue, medical or death (all) | 83 | 1 | 5 | 76 | 1 |
| Offline keyword rules | Original text | needs a person (sample) | 149 | 0 | 1 | 148 | 0 |
| Offline keyword rules | Original text | routine (sample) | 137 | 0 | 0 | 137 | 0 |
| Offline keyword rules | Original text | rescue, medical or death (all) | 82 | 0 | 0 | 82 | 0 |
| Claude model mode (claude-haiku-5-5) | English translation | needs a person (sample) | 150 | 9 | 54 | 18 | 69 |
| Claude model mode (claude-haiku-5-5) | English translation | routine (sample) | 150 | 0 | 2 | 68 | 80 |
| Claude model mode (claude-haiku-5-5) | English translation | rescue, medical or death (all) | 83 | 14 | 31 | 9 | 29 |
| Claude model mode (claude-haiku-5-5) | Original text | needs a person (sample) | 149 | 12 | 44 | 29 | 64 |
| Claude model mode (claude-haiku-5-5) | Original text | routine (sample) | 137 | 3 | 3 | 59 | 72 |
| Claude model mode (claude-haiku-5-5) | Original text | rescue, medical or death (all) | 82 | 15 | 26 | 14 | 27 |

Review notes in model mode (messages with at least one note of each kind, all evaluated messages):

| Text | Unverified quotes dropped | Location not in the caller's words | Life threat reported without a verified caller quote | Reply withheld because it made a promise | Interview failed |
|---|---:|---:|---:|---:|---:|
| English translation | 4 | 3 | 1 | 0 | 0 |
| Original text | 15 | 10 | 0 | 0 | 4 |

Language codes Claude reported for the original text: `ht` 288, `fr` 34, `en` 10, `(failed turn)` 4, `es` 1, `ur` 1, `ur-Latn` 1, `hi-Latn` 1.
<!-- results:end -->

## Reading the results

* The offline keyword rules prioritize almost nothing on these messages. They rank 139 of 150
  needs-a-person and 147 of 150 routine English messages UNKNOWN, and nearly every original.
  Their misses are rare only because almost everyone shares PRIORITY's rank, which in the queue
  is close to FIFO. Their routine keywords (FEMA, CalFresh, freeway) are Los Angeles words.
* Claude separates the classes in the right direction, but weakly on a first message: 63 of 150
  needs-a-person messages are IMMEDIATE or PRIORITY against 2 of 150 routine ones, yet 69 of 150
  (46%) are NORMAL, and 68 of 150 routine messages are UNKNOWN.
* In the rescue, medical or death subset Claude ranks 14 of 83 IMMEDIATE (people under rubble,
  "children and olders are dying from starvation") and 29 NORMAL. One read-through of those 29
  (this session, not a label): about 25 ask for information, supplies or services, or report
  deaths, without describing someone in danger now (one offers to donate a turkey); about four
  state urgency in general terms, such as "Leogane has totally collapsed. We need help urgently."
  The tier definitions in `dualuse/playbooks/core.md` name no shelter tonight, medication or
  oxygen running out, a missing person and a dependent left alone as needing a person soon, and
  list "where to find water or a shelter" as a routine question. Requests for food, water or
  supplies after a disaster therefore read as routine. That definition gap, more than misreading,
  drives the miss rate under this proxy.
* Claude's rates on the original text are close to those on the English translation (misses
  43% against 46%, subset ranked NORMAL 33% against 35%); it reported Haitian Creole (`ht`) for
  288 of 340 originals. The first-turn ranking did not depend on the translation.
* Review flags rise on the original text (8% and 6% against 2% and 2%), mostly dropped quotes
  and locations. Claude hands back Creole quotes and place names with corrected spelling or
  accents (`manje` for `MANGE`, `Léogâne` for `leogane`), and the checks require the caller's own
  words. Four original-text turns failed because the answer reached `model_turn`'s 1,600-token
  limit, with most tokens spent on hidden thinking; the live desk would rank those callers
  UNKNOWN and flag them.
* None of this is 211 accuracy. It says that, on recorded disaster messages, a single first turn
  ranks about one in six danger-proxy messages IMMEDIATE and leaves about a third NORMAL, far from
  the 5% miss rate the simulator assumed.

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
  draws new ones.

## Reproduce

```text
bash scripts/uv-run.sh env -u ANTHROPIC_API_KEY python scripts/evaluate_messages.py
```

`env -u` lets `dualuse.config` read the key from `.env` when WSLENV forwards an empty variable.
The run writes `data/processed/eval_messages.json` (summaries and one row per message, method and
text) and the results block above.
