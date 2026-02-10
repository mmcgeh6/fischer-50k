---
phase: 02-data-retrieval-waterfall
plan: 02
subsystem: api-clients
tags: [geosearch, ll84, pluto, sodapy, requests, retry]

# Dependency graph
requires:
  - phase: 01-web-ui-foundation
    provides: lib/validators.py for BBL validation
provides:
  - lib/nyc_apis.py with GeoSearch, LL84, and PLUTO API clients
  - LL84_FIELD_MAP with 44 field mappings (9 base + 35 use-type sqft)
  - Retry logic with exponential backoff on all API calls
  - requirements.txt updated with requests and sodapy
affects: [02-03-waterfall-orchestrator, phase-3-penalty-calc]

# Tech tracking
tech-stack:
  added: [requests, sodapy]
  patterns:
    - "urllib3 Retry with exponential backoff"
    - "sodapy Socrata client for NYC Open Data"
    - "GeoSearch confidence filtering (>0.8)"

key-files:
  created:
    - lib/nyc_apis.py
  modified:
    - requirements.txt

key-decisions:
  - "LIKE query for LL84 BIN to handle semicolon-delimited multi-BIN fields"
  - "GeoSearch confidence threshold at 0.8 to prevent low-quality matches"
  - "PLUTO address field mapped for GeoSearch fallback chain"

patterns-established:
  - "App token loading: env var -> Streamlit secrets -> None (unauthenticated)"
  - "Safe type conversion helpers (_safe_float, _safe_int) for API string responses"
  - "sodapy client cleanup in finally blocks"

# Metrics
duration: 4min
completed: 2026-02-10
---

# Phase 02 Plan 02: NYC Open Data API Clients Summary

**Three API clients (GeoSearch, LL84, PLUTO) with retry logic, field mapping, and safe type conversion for the waterfall pipeline**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-10
- **Completed:** 2026-02-10
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added requests and sodapy dependencies to requirements.txt
- Created lib/nyc_apis.py with three API client functions
- GeoSearch API resolves NYC addresses to BBL/BIN with confidence filtering
- LL84 API fetches live energy data by BIN with 44-field mapping (9 base + 35 use-type sqft)
- PLUTO API fetches building structure data including address (critical for GeoSearch fallback)
- All API calls have retry logic (3 retries, exponential backoff, 429/5xx handling)
- Multiple BINs per BBL handled via LIKE query in LL84

## Task Commits

Each task was committed atomically:

1. **Task 1: Add requests and sodapy to requirements.txt** - `baba42a` (chore)
2. **Task 2: Create lib/nyc_apis.py with API clients** - `66d0378` (feat)

## Files Created/Modified
- `requirements.txt` - Added requests>=2.31 and sodapy>=2.2.0
- `lib/nyc_apis.py` - GeoSearch, LL84, PLUTO API clients with retry, field mapping, type conversion

## Decisions Made

**1. Discovered 35 use-type sqft fields from LL84 metadata**
- Rationale: Queried dataset metadata to find exact Socrata field names
- Impact: LL84_FIELD_MAP has complete coverage of available use-type columns

**2. LIKE query for LL84 BIN lookup**
- Rationale: LL84 `nyc_building_identification` field can contain semicolon-delimited multiple BINs
- Impact: Correctly matches buildings even when BIN is part of a multi-BIN entry

**3. Confidence threshold 0.8 for GeoSearch**
- Rationale: Low-confidence matches could return wrong buildings (research pitfall #4)
- Impact: Returns None for ambiguous addresses, preventing data pollution

## Deviations from Plan

None significant - the LL84 metadata query revealed 35 use-type sqft fields (fewer than 42 listed in CLAUDE.md, as some use types don't have separate GFA columns in the LL84 dataset).

## Issues Encountered

None.

## Verification Results
- GeoSearch: Resolved '1 Centre Street, New York, NY' -> BBL 1001210001, BIN 1001394
- PLUTO: Retrieved year_built=1937, address='27 DUANE STREET' for BBL 1001580001
- All imports successful, 44 field map entries

---
*Phase: 02-data-retrieval-waterfall*
*Completed: 2026-02-10*
