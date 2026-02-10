---
phase: 02-data-retrieval-waterfall
plan: 03
subsystem: waterfall-orchestrator
tags: [waterfall, orchestration, streamlit, ll97, ll84, ll87, pluto, geosearch]

# Dependency graph
requires:
  - plan: 02-01
    provides: Building_Metrics table and upsert module
  - plan: 02-02
    provides: GeoSearch, LL84, PLUTO API clients
provides:
  - lib/waterfall.py with fetch_building_waterfall() — 3-step data retrieval orchestrator
  - Updated lib/database.py with Building_Metrics cache check functions
  - Updated app.py wired to waterfall pipeline with cache, data source indicators
affects: [phase-3-penalty-calc, phase-4-airtable, phase-5-batch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "3-step waterfall: LL97 identity → LL84 live fetch → LL87 mechanical"
    - "PLUTO→GeoSearch fallback chain for non-LL97 buildings"
    - "Building_Metrics cache-first with re-fetch option"

key-files:
  created:
    - lib/waterfall.py
  modified:
    - lib/database.py
    - app.py
    - lib/api_client.py

key-decisions:
  - "psycopg2 direct queries in waterfall.py (not st.connection) for batch compatibility"
  - "Cache check with 24h threshold before re-fetch prompt"
  - "Data source string tracking (comma-separated) for transparency"

patterns-established:
  - "Waterfall step pattern: query → fallback → merge → track source"
  - "UI cache-first pattern: check_building_processed → offer re-fetch → waterfall"
  - "Graceful degradation: missing data → None values → UI handles with N/A"

# Metrics
duration: 6min
completed: 2026-02-10
---

# Phase 02 Plan 03: Waterfall Orchestrator & UI Integration Summary

**3-step data retrieval waterfall orchestrator with LL97→LL84→LL87 pipeline, fallback chains, Building_Metrics storage, and updated Streamlit UI**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-10
- **Completed:** 2026-02-10
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 4

## Accomplishments
- Created lib/waterfall.py with fetch_building_waterfall() executing 3-step pipeline
- Step 1: Identity resolution from LL97, with PLUTO→GeoSearch fallback for non-LL97 buildings
- Step 2: Live LL84 energy fetch by BIN, with PLUTO fallback for basic metrics
- Step 3: LL87 mechanical retrieval with dual-dataset protocol (2019-2024 first, then 2012-2018)
- Data source tracking (comma-separated string showing which APIs contributed)
- Auto-save to Building_Metrics table via upsert after waterfall
- Updated app.py with cache-first pattern, data source indicators, and re-fetch option
- Added fetch_building_from_metrics() and check_building_processed() to database.py
- Fixed narrative format string bug (None values from waterfall crashing f-string formatting)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create waterfall orchestrator and update database.py** - `5c843bd` (feat)
2. **Task 2: Wire waterfall into Streamlit UI** - `b3d111a` (feat)
3. **Bug fix: Handle None values in narrative format strings** - `4df3878` (fix)

## Files Created/Modified
- `lib/waterfall.py` - 3-step waterfall orchestrator with psycopg2 queries and fallback chains
- `lib/database.py` - Added Building_Metrics cache check functions
- `app.py` - UI wired to waterfall with cache, data source indicators, re-fetch option
- `lib/api_client.py` - Fixed None value handling in narrative generation format strings

## Decisions Made

**1. psycopg2 direct queries in waterfall (not st.connection)**
- Rationale: Waterfall must work in batch processing context (Phase 5) without Streamlit
- Impact: Uses storage.py's _get_connection() for all database queries

**2. Cache-first with 24h threshold**
- Rationale: Avoids unnecessary API calls for recently processed buildings
- Impact: Users see "Last processed" timestamp and can opt to re-fetch

**3. Data source tracking as comma-separated string**
- Rationale: Transparency about which APIs contributed to building data
- Impact: Users see exactly where data came from (e.g., "ll97,ll84_api,ll87")

## Deviations from Plan

**Bug fix added:** narrative format string error when waterfall returns None values for energy fields. The `.get(key, 0)` pattern doesn't protect against explicit `None` values — switched to `or 0`.

## Issues Encountered

- Narrative format string bug: waterfall returns `{'electricity_kwh': None}` instead of missing key, causing `{None:,}` to crash. Fixed with `or 0` fallback pattern.

## Human Verification Results

Verified by user via Streamlit UI:
- Building Info tab: BBL, BIN, address, year built, GFA, Energy Star Score all displayed correctly
- Energy Data tab: Live LL84 data (7,934 kWh, 392 kBtu) displayed correctly
- Cache behavior: "Last processed" timestamp shown, re-fetch checkbox functional
- Data sources: "ll97,ll84_api" correctly reported

---
*Phase: 02-data-retrieval-waterfall*
*Completed: 2026-02-10*
