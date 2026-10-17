# DeepSeek V4.1 Flash through OpenRouter, compared on the recorded-message evaluation

* Type: implementation
* Scope: `scripts/evaluate_messages.py` (`--openrouter`), `scripts/check_keys.py`, `.env.example`,
  `tests/test_evaluate_messages.py`, `docs/evaluation.md`, `docs/submission.md`
* Related: [desk fixes 016](2026-10-17-016-desk-tier-definitions-and-checks.md),
  [staging integration 018](2026-10-17-018-staging-integration.md)

## Context

* The user asked, Sat 2026-10-17 about 15:15 PT, whether a cheaper model performs better: check the
  `OPENROUTER_API_KEY` they added to `.env`, call `deepseek/deepseek-v4.1-flash-1017` through
  OpenRouter's Anthropic-compatible Messages endpoint (`https://openrouter.ai/api/v1/messages`) and
  run the benchmark.
* `claude/admiring-antonelli-3eb3bf` was fast-forwarded to `codex/demo-integration-20261017`
  (`6217ccf`), which already merged commit 313c77f and the `--split train` and `--model` options, so
  this change builds on that design instead of conflicting with it.

## Decision

* `scripts/evaluate_messages.py --openrouter MODEL` sends the desk's unchanged request (playbooks,
  schema, 4,000 tokens, low effort) to MODEL through OpenRouter, with its own cache and results files
  (`/` in the id becomes `_`), never the docs block or the simulator's file. The cost is the one
  OpenRouter bills in each response's `usage.cost`.
* The OpenRouter client passes only `auth_token`, so the Anthropic SDK sends
  `Authorization: Bearer <OpenRouter key>` and never `ANTHROPIC_API_KEY` as `x-api-key`; OpenRouter
  treats `x-api-key` as an Anthropic credential.
* `scripts/check_keys.py` checks `OPENROUTER_API_KEY` with `GET /api/v1/key`, which spends no
  credits; `.env.example` lists the name.
* The desk keeps `claude-haiku-5-5`: see Verification.

## Verification

* Key: `check_keys.py` reported `OPENROUTER_API_KEY: ok` (and `TERMINAL49_API_KEY` failing with
  401, unrelated). A probe sent only the `Authorization` header; a minimal call answered in 1.7 s;
  two desk turns returned valid structured JSON (PRIORITY for no food or water since a fire, NORMAL
  for the freeway question).
* Tests first: three new tests failed before the code (`usage` without `cost`, no
  `_openrouter_client`, the OpenRouter run's files and labels); the validation-run test's fake now
  takes the client factory. `bash scripts/uv-run.sh python -m pytest tests -q`: 455 passed (452 on
  the integration tip before the change).
* Validation (15:34 PT) and test (15:45 PT) runs, one each, against Haiku's runs of record 016,
  English translation: misses 18.7% against 25.3% (validation) and 21.3% against 28.7% (test);
  routine ranked ahead of NORMAL 62.7% against 46.7% and 71.3% against 43.3%; one DeepSeek turn
  stopped at 4,000 tokens. All rows: [evaluation.md](../evaluation.md), section "Another model
  through OpenRouter".
* The ported code replayed the DeepSeek validation run from its cache with identical summaries,
  rows and cost, sending nothing (a placeholder key made any call fail).
* Simulated queue (default surge, 200 seeds, measured tiers): immediate callers who hung up, Haiku
  against DeepSeek, 19.7% against 28.2% on test English tiers and lower for Haiku in all four
  split and text combinations; FIFO 31.2%.
* Real turns, 18 team-written English, Spanish and Mandarin samples with the live client settings:
  18 of 18 as expected for both; median 3.3 s and at most 11.7 s for DeepSeek against 2.3 s and
  5.6 s for Haiku; DeepSeek billed $0.0057 for 19 turns.
* Cost: DeepSeek runs $0.25 and $0.24 as billed against Haiku's $0.32 and $0.33 at list price.
* OpenRouter chose the hosts: InferenceNet (fp8) 1,275 of 1,377 requests, Cloudflare 80, Parasail 16,
  DeepInfra 6.
* Not verified: playbook wording tuned for DeepSeek, other hosts or a pinned provider, latency under
  a surge, and 211 calls.
