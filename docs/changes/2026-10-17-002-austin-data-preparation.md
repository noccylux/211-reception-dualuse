# Prepare the Austin APD manual dataset import

* Type: ops
* Scope: `data/raw/austintexas/`, `docs/datasets.md`, `docs/datasets.manifest.json`
* Related: [Initial dataset downloads](2026-10-17-001-dataset-downloads.md)

Prepared a destination and source record for the user's manually downloaded
Austin APD dataset on 2026-10-17 PT.

## Decision

* Create `data/raw/austintexas/apd-911-calls-for-service-e687-fx2y/` under the
  existing Git-ignored data tree. Retain the user's original filename and format.
* Save official metadata locally and register a separate `manual_sources`
  entry. Keep the existing pinned download command limited to verified files
  from the first three sources.
* Record source coverage, schema, declared license and interpretation limits
  in the [dataset inventory](../datasets.md).

## Verification

* Retrieved official metadata for `e687-fx2y` and confirmed 25 published fields.
* `.\scripts\uv-run.ps1 python -m pytest tests/`: **4 passed** in WSL,
  Python 3.14.7.
* The user's export has not been placed or inspected. File size, row count,
  checksum and actual coverage remain unverified. No ingestion code changed.
