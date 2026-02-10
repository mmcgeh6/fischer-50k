# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Accurate, pre-calculated building intel with professional system narratives — ready to share with prospective clients without manual research.
**Current focus:** Phase 3 - Calculations & Narratives

## Current Position

Phase: 2 of 5 (Data Retrieval Waterfall) — COMPLETE ✓
Plan: All 3 plans complete
Status: Ready for Phase 3
Last activity: 2026-02-10 — Phase 2 verified and complete

Progress: [████░░░░░░] 40%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 5.3 min
- Total execution time: 0.53 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-web-ui-foundation | 3 | 22 min | 7.3 min |
| 02-data-retrieval-waterfall | 3 | 12 min | 4.0 min |

**Recent Trend:**
- 01-01: 5 min (project structure setup)
- 01-02: 2 min (database and API modules)
- 01-03: 15 min (Streamlit app + bug fixes + human verification)
- 02-01: 2 min (Building_Metrics table creation)
- 02-02: 4 min (NYC API clients)
- 02-03: 6 min (Waterfall orchestrator + UI + human verification)
- Trend: Phase 2 complete — focused modules execute faster

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Streamlit for UI: Simple, Python-native, team isn't developers (Confirmed)
- Anthropic Claude for narratives: Team preference, quality narratives (Confirmed)
- On-demand Airtable push (not sync): Simpler integration, team controls what goes to pipeline (Pending)
- Data-only narrative prompts: Accuracy over completeness, no hallucination (Confirmed)

**From Phase 1 execution:**
- Python 3.14 dependency handling: Documented --only-binary flag and pyarrow workaround (Technical)
- Secrets template approach: Created example file with placeholder password, gitignored real secrets (Security)
- TTL caching strategy: 1h for static data (LL97, LL87), 10m for energy data (LL84) (Technical)
- Data-only narrative approach: explicit "not documented" fallbacks, temperature 0.3 for consistency (Architecture)
- Per-narrative error handling: one failure doesn't break entire batch (Technical)
- Added sqlalchemy dependency: Required by st.connection() (Technical)
- Database column name corrections: ll97 uses preliminary_bin/address, ll84 uses total_gross_floor_area/property_use (Technical)

**From Phase 2 execution:**
- 67 use-type sqft columns: Covers all LL84 types plus emissions-factor-only types for complete penalty calc coverage (Architecture)
- psycopg2 direct connection for lib/storage.py and lib/waterfall.py: Enables batch processing outside Streamlit context (Technical)
- Dynamic upsert pattern: Only updates columns present in input dict, allows waterfall steps to populate incrementally (Architecture)
- LIKE query for LL84 BIN: Handles semicolon-delimited multi-BIN fields in LL84 dataset (Technical)
- GeoSearch confidence threshold 0.8: Prevents low-quality address matches (Technical)
- PLUTO→GeoSearch fallback chain: For non-LL97 buildings, PLUTO provides address, GeoSearch resolves BIN (Architecture)
- Cache-first UI pattern: Check Building_Metrics before re-fetching, 24h threshold (Architecture)
- None value handling in format strings: Use `or 0` not `.get(key, 0)` when dict may have explicit None values (Technical)

### Pending Todos

None yet.

### Blockers/Concerns

None.

## Phase 1 Summary

**Web UI Foundation** — Complete ✓

All 4 requirements satisfied (UI-01 through UI-04):
- BBL input form with validation
- Building data display in organized tabs
- 6 AI-generated system narratives
- GHG emissions and penalty calculations

## Phase 2 Summary

**Data Retrieval Waterfall** — Complete ✓

All 10 requirements satisfied (DATA-01 through DATA-07, STOR-01 through STOR-03):
- Building_Metrics table (86 columns) with dynamic upsert and timestamp trigger
- GeoSearch, LL84, PLUTO API clients with retry logic and field mapping
- 3-step waterfall orchestrator (LL97 → LL84 → LL87) with fallback chains
- UI wired to waterfall with cache-first pattern and data source indicators
- Narrative format string bug fixed (None value handling)

## Session Continuity

Last session: 2026-02-10
Stopped at: Phase 2 complete, verified, ready for Phase 3
Resume file: None

**Next steps:** `/gsd:discuss-phase 3` or `/gsd:plan-phase 3` — Calculations & Narratives
