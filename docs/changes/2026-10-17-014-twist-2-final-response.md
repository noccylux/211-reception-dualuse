# Twist 2: final response for the built China 12345 profile

* Type: twist
* Scope: `docs/problem/twists.md`, `docs/architecture.md`
* Related: [proposal](2026-10-17-006-twist-2-global.md), [design](2026-10-17-009-reception-agent-design.md),
  [poster and Devpost text](2026-10-17-015-poster-and-devpost.md)

## Context

* Record 006 proposed a China community assistance scenario before anything
  was built. Record 009 built it as the `cn-12345` line profile, merged into
  `main` in `dea860c`, with the 12345 facts marked to be verified before the
  pitch.
* All three twist responses go with the final submission, due Sat 2026-10-17
  22:00 PT.

## Decision

* Replace the proposal in `twists.md` with what is built, the facts checked
  against primary sources, the limits and a final portal response draft.
  Submitting it is the user's action.
* Call 12345 by its national name, the government service hotline
  (12345政务服务便民热线); "citizen service hotline" is Beijing's usage.
* Claim only what the demo shows. The profile names 110, 119 and 120; 122,
  a localized operator summary and the profile's English name are left as
  follow-ups because this task changes documentation only.

## Verification

* Demo run Sat 2026-10-17 12:57 to 13:10 PT on a separate desk (API
  127.0.0.1:8075, UI 127.0.0.1:8575, `.tmp/poster-demo.sqlite3`), model mode
  with `claude-haiku-5-5`. The team-written Mandarin flood report became
  IMMEDIATE after the first message; the desk named 110, 119 and 120 in
  Mandarin; Claude asked for district, road, compound and building; the
  address was kept verbatim; the operator summary was English with the Chinese
  quote and address.
* Facts: a research subagent's report, then direct reads of the quoted
  passages in 国办发〔2020〕53号, 国办发〔2022〕12号 and 国办函〔2025〕66号 on
  gov.cn, Beijing Daily (2023-08-02), China News Service (2026-07-07) and the
  UPU addressing sheet for China. Not confirmed: an official page naming 119 a
  general rescue number; 12345 call volumes for the 2021 Zhengzhou floods.
* `bash scripts/uv-run.sh python -m pytest tests -q`: 205 passed on this
  branch, based on `81c9b21`. No code changed.
