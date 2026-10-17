# Download requested research datasets

* Type: ops
* Scope: `data/raw/`, `docs/datasets.md`, `docs/datasets.manifest.json`, `docs/submission.md`

Prepared the three requested datasets locally on 2026-10-17 PT. This does
not connect them to the application or establish their suitability for a demo.

## Decision

* Keep original files in the existing Git-ignored `data/raw/<owner>/<dataset>/`
  directories. Track a small manifest and [inventory](../datasets.md) instead
  of adding the data to the repository.
* Pin source revisions and retain all source files, including available
  license and descriptive material. No dependencies were added.
* Record the absent 911project audio and transcript schema anomalies without
  modifying upstream data. External audio links remain undownloaded.
* Add OpenAI Codex to the submission's AI tool disclosure.

## Verification

* All 12 files matched upstream byte sizes and Git blob SHA-1 values; local
  SHA-256 values are saved in the manifest.
* Parsed 518 JSONL conversations and all four CSV files. Observed 23,850
  disaster-message rows across the three splits and 742 metadata rows.
* A strict chat-schema check exposed nine nonstandard roles and one null
  content value in the source transcripts; details are in the inventory.
* `.\scripts\uv-run.ps1 python -m pytest tests/`: **4 passed** in WSL,
  Python 3.14.7. The sandbox denied initial WSL access; the authorized retry
  completed successfully.
* No UI or API code changed. No model training, source-authenticity audit or
  external audio availability check was performed.
