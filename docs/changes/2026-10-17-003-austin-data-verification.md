# Verify the supplied Austin APD export

* Type: ops
* Scope: `docs/datasets.md`, `docs/datasets.manifest.json`, `docs/datasets.austin-validation.json`
* Related: [Austin data preparation](2026-10-17-002-austin-data-preparation.md)

Verified the user's manually placed CSV on 2026-10-17 PT and replaced the
pending-import status with measured results. Raw data remains unchanged.

## Verification

* Parsed the entire 345,751,451-byte file using strict UTF-8 and CSV decoding:
  1,074,633 data rows, 25 fields matching the official schema in order,
  zero row-width failures, and valid nonempty numeric and datetime values.
* Python SHA-256 and independent PowerShell `Get-FileHash` agree. The manifest
  now records that checksum, size, row count and response date bounds.
* Official API aggregates match the local total, 1,074,608 distinct incident
  numbers, earliest/latest response timestamps and all 45 monthly counts.
  API queries and results are retained in the validation report.
* Found 25 pairs of differing records sharing an incident number, with no
  identical rows. Documented missing values and timestamp-order findings in
  the [data inventory](../datasets.md). No automatic cleaning was performed.
* `.\scripts\uv-run.ps1 python -m pytest tests/`: **4 passed** in WSL,
  Python 3.14.7.
* No publisher-provided export checksum was available. Aggregate agreement
  does not establish row-by-row equality with the live dataset. No UI or API
  behavior changed.
