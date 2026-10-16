# Documentation

Read before creating or editing repository documentation. Use concise English
in the repository; give Chinese explanations in chat when requested. Keep code
identifiers, paths, commands and domain terms exact. Do not maintain parallel
translations.

## Write for retrieval and verification

- Start with the document's purpose and whether it describes current
  behavior, a plan or a past event.
- Use short natural sentences, descriptive headings and bullets for
  independent facts. Avoid invented abbreviations and ornamental prose.
- State a fact in its owning document and link to it elsewhere instead of
  copying it. Use repository-relative links.
- Separate observations from expectations. Never present simulated or
  sample data, or an old test result, as a current measured fact.
- Give exact commands when they let the reader reproduce a result.
- Write times as Pacific time with the date, for example
  `Sat 2026-10-17 22:00 PT`.

## Document roles

- `docs/hackathon.md`: official event facts, sourced from
  `docs/information/`. Update when organizers announce a change, noting the
  source (WhatsApp, portal, in the room).
- `docs/problem/`: the official problem and twists, verbatim, plus our
  reading of them.
- `docs/architecture.md`: what the build is now; updated with the code.
- `docs/changes/`: dated decisions and outcomes under
  [change-records.md](change-records.md). Read as history.
- `docs/submission.md`: Devpost material, the AI tool list and the pitch.
- `docs/information/`: saved official sources. Never edit.
- README: entry point, quickstart and demo instructions.
