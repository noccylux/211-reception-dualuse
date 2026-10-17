# Local datasets

Inventory of downloaded files verified as of 2026-10-17 PT. These are local
research inputs; the API and UI do not use them yet. Raw files are unchanged
and stored under the existing Git-ignored `data/` directory.

## Inventory

| Source | Local directory | Downloaded data |
|---|---|---|
| [spikecodes/911-call-transcripts](https://huggingface.co/datasets/spikecodes/911-call-transcripts) | `data/raw/spikecodes/911-call-transcripts/` | `calls.jsonl`: 518 conversations; upstream README and Git attributes. |
| [rmunro/disaster_response_messages](https://github.com/rmunro/disaster_response_messages) | `data/raw/rmunro/disaster_response_messages/` | Training: 19,116 rows; validation: 2,337; test: 2,397. Upstream README and license included. |
| [n8maxey/911project](https://github.com/n8maxey/911project) | `data/raw/n8maxey/911project/` | `911_metadata.csv`: 742 rows; upstream README, R Markdown analysis and PDF report. |
| [Austin APD 911 Calls for Service 2023-2026](https://datahub.austintexas.gov/Public-Safety/APD-911-Calls-for-Service-2023-2026/e687-fx2y/about_data) | `data/raw/austintexas/apd-911-calls-for-service-e687-fx2y/` | Verified manual CSV export: 1,074,633 rows and 25 fields. Official metadata and aggregate responses saved separately. |

The first three sources total 12 files, 9,765,929 bytes (about 9.31 MiB).
This excludes the Austin export and its supporting snapshots. Counts come from parsing the
downloaded files, excluding CSV headers. The disaster messages total 23,850
rows in this revision, despite the upstream description's approximate 25,000.

The [manifest](datasets.manifest.json) records exact revisions, download URLs,
file sizes, upstream Git blob hashes and SHA-256 checksums. Downloaded bytes
matched the upstream sizes and Git blob hashes for the first 12 files. Keep the
inventory, manifest and validation reports in Git; keep raw data local and put any future
cleaned outputs under `data/processed/`.

## Austin verified manual export

File: `data/raw/austintexas/apd-911-calls-for-service-e687-fx2y/APD_911_Calls_for_Service_2023-2026_20261016.csv`.
Original bytes and filename are preserved in the Git-ignored directory. No
application ingestion is configured.

### Integrity and coverage

Full-file verification on 2026-10-17 PT found:

| Check | Observed result |
|---|---|
| File size | 345,751,451 bytes (329.73 MiB) |
| Data rows, excluding header | 1,074,633 |
| Fields | 25; names and order exactly match saved official metadata |
| CSV structure | Entire file parsed with strict CSV and UTF-8 decoding; zero incorrect-width or completely empty rows |
| Response Datetime range | 2023-01-01 00:01:00 through 2026-09-30 23:59:17 |
| Coverage | All 45 months from January 2023 through September 2026 |
| Unique incident numbers | 1,074,608; no missing incident numbers |
| Official aggregate comparison | Total rows, unique incident count, date bounds and all 45 monthly row counts match |
| Type checks | All nonempty numeric and datetime fields parse successfully |

SHA-256, independently matched with Python `hashlib` and PowerShell
`Get-FileHash`:

```text
c583f07a9fa83a7b36e30aff4c0c516d20079690327919f1b78a44f00205369b
```

The [validation report](datasets.austin-validation.json) contains per-field
checks, monthly counts and the exact official API queries and responses.
The saved `source-metadata.json` contains official field definitions;
`source-summary.json` and `source-monthly-counts.json` retain the aggregate
responses locally. The manifest's `manual_sources` entry records the verified
file size, counts and checksum.

These checks found no evidence of a truncated export or missing months.
The publisher did not provide an export checksum, so the SHA-256 establishes
a local baseline. Aggregate agreement is not a row-by-row comparison with
the current source.

### Data quality and parsing

- There are 25 repeated incident numbers, each with two different records
  (50 rows total). No complete rows are duplicated. The official distinct-ID
  count confirms the same 25-row excess. Do not deduplicate by incident number
  without deciding how those differing records should be handled.
- Empty values occur in `Call Closed Datetime` (5), `Unit Time on Scene` (19),
  `Geo ID` (7) and `Census Block Group` (7). All other fields have zero empty
  values. These are empty-cell counts, not a guarantee that every nonempty
  value is semantically known or correct.
- Timestamp comparisons flag 24 rows closing before arrival, 13 closing
  before the response timestamp and 1 arriving before the response timestamp.
  The groups can overlap. Preserve and review them before calculating elapsed
  times; the CSV has no timezone offsets and these checks do not establish
  whether clock changes or source errors explain the findings.
- All incident types are `Dispatched Incident`. Observed priority labels are
  `Priority 0` through `Priority 3`; there are no `Priority 4` records.
- Numeric cells can contain comma thousands separators, such as `4,295`.
  Use a CSV parser, then remove grouping commas from numeric fields only.
  Dates use `%Y %b %d %I:%M:%S %p`, such as `2026 Sep 30 11:59:17 PM`.
  Keep incident and geographic identifiers as text. No timezone conversion
  was applied. Day-of-week and response-hour columns match every response
  timestamp.
- Arrival and closure dates extend into October 1, 2026 for incidents that
  began in September. Coverage above uses `Response Datetime`.

### Field inventory

Types below are the publisher's schema. Numeric and datetime validation was
applied to every nonempty value; text fields remain strings.

| CSV field | API field | Type | Empty cells |
|---|---|---|---:|
| Incident Number | `incident_number` | text | 0 |
| Incident Type | `incident_type` | text | 0 |
| Mental Health Flag | `mental_health_flag` | text | 0 |
| Priority Level | `priority_level` | text | 0 |
| Response Datetime | `response_datetime` | calendar_date | 0 |
| Response Day of Week | `response_day_of_week` | text | 0 |
| Response Hour | `response_hour` | number | 0 |
| First Unit Arrived Datetime | `first_unit_arrived_datetime` | calendar_date | 0 |
| Call Closed Datetime | `call_closed_datetime` | calendar_date | 5 |
| Sector | `sector` | text | 0 |
| Initial Problem Description | `initial_problem_description` | text | 0 |
| Initial Problem Category | `initial_problem_category` | text | 0 |
| Final Problem Description | `final_problem_description` | text | 0 |
| Final Problem Category | `final_problem_category` | text | 0 |
| Number of Units Arrived | `number_of_units_arrived` | number | 0 |
| Unit Time on Scene | `unit_time_on_scene` | number | 19 |
| Call Disposition Description | `call_disposition_description` | text | 0 |
| Report Written Flag | `report_written_flag` | text | 0 |
| Response Time | `response_time` | number | 0 |
| Officer Injured/Killed Count | `officer_injured_killed_count` | number | 0 |
| Subject Injured/Killed Count | `subject_injured_killed_count` | number | 0 |
| Other Injured/Killed Count | `other_injured_killed_count` | number | 0 |
| Geo ID | `geoid` | text | 7 |
| Census Block Group | `blkgpnm` | text | 7 |
| Council District | `council_district` | text | 0 |

### Source context

According to the [official metadata API](https://datahub.austintexas.gov/api/views/e687-fx2y.json),
checked on 2026-10-17 PT:

- Dataset ID: `e687-fx2y`; publisher: City of Austin, Austin Police.
- This is a filtered view of CAD incidents received through 911. It excludes
  cancelled duplicate incidents and certain cancellations handled by another
  agency or requiring no police response. It is not a count of all 911 calls.
- The publisher lists monthly updates and coverage from January 1, 2023 to
  September 30, 2026, matching this export's response dates. Future exports
  can change as source records are revised.
- There are 25 published fields, including incident number, initial/final
  problem categories, priority, timestamps, response time and geography.
  This is structured incident data, not call audio or conversation transcripts.
- Priority ranges from 0 (highest) to 4 (lowest), measured at first officer
  arrival. Response time and total unit time on scene are in seconds. Final
  categories and arrival-time priority should not be treated as information
  necessarily available when the call began.
- Metadata declares `PUBLIC_DOMAIN` and links to the
  [City of Austin Open Data Terms of Use](https://data.austintexas.gov/stories/s/ranj-cccq).
  Preserve attribution and the source disclaimer. These records may differ
  from official crime statistics.

## Source limitations

- **Transcripts:** the dataset card declares MIT, but provides no provenance
  narrative or separate license text. Authenticity of each conversation was
  not independently verified. JSON parsing succeeds, but nine messages use
  roles outside `assistant`, `user` and `system` (`assistance`, `caller`,
  `dispatcher`, `tenant`, `helper`). Line 37, message index 83 (zero-based),
  has null content. Preserve the raw file and address these before using it
  as chat training data.
- **Disaster messages:** CC-BY-4.0. Preserve attribution to Robert Munro and
  the source's requested citation: Robert Munro (2012), *Processing short
  message communications in low-resource languages*, Stanford University.
  See the downloaded README and LICENSE for details. Keep the supplied
  training, validation and test splits separate.
- **911project:** the complete repository snapshot contains no audio files,
  despite the README describing MP3 recordings. The CSV includes external
  Internet Archive links; those linked resources were not downloaded or
  checked. There is no license file in this revision. Do not assume its
  redistribution terms match either of the other datasets.

## Restore the first three datasets

The Austin export is manually supplied and is excluded from this command.
Run this in PowerShell 7.3+ from the repository root. It uses the pinned URLs
and validates SHA-256 before placing each file. It skips existing files only
if their hashes match; a failure stops the download.

```powershell
$ErrorActionPreference = 'Stop'
$manifest = Get-Content docs/datasets.manifest.json -Raw | ConvertFrom-Json
foreach ($file in $manifest.datasets.files) {
    if (Test-Path -LiteralPath $file.path) {
        if ((Get-FileHash -LiteralPath $file.path).Hash -ne $file.sha256) {
            throw "Existing file differs: $($file.path)"
        }
        continue
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $file.path) | Out-Null
    $partial = "$($file.path).part"
    Invoke-WebRequest -Uri $file.url -OutFile $partial
    if ((Get-FileHash -LiteralPath $partial).Hash -ne $file.sha256) {
        throw "Download checksum mismatch: $($file.path)"
    }
    Move-Item -LiteralPath $partial -Destination $file.path
}
```
