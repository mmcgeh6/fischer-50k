# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Accurate, pre-calculated building intel with professional system narratives — ready to share with prospective clients without manual research.
**Current focus:** Phase 2 - Data Retrieval Waterfall

## Current Position

Phase: 2 of 5 (Data Retrieval Waterfall) — IN PROGRESS
Plan: 1 of 3 complete
Status: Building storage foundation complete, ready for identity step
Last activity: 2026-02-10 — Completed 02-01-PLAN.md

Progress: [████░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 6.0 min
- Total execution time: 0.40 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-web-ui-foundation | 3 | 22 min | 7.3 min |
| 02-data-retrieval-waterfall | 1 | 2 min | 2.0 min |

**Recent Trend:**
- 01-01: 5 min (project structure setup)
- 01-02: 2 min (database and API modules)
- 01-03: 15 min (Streamlit app + bug fixes + human verification)
- 02-01: 2 min (Building_Metrics table creation)
- Trend: Phase 2 started - faster execution on focused database work

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
- psycopg2 direct connection for lib/storage.py: Enables batch processing outside Streamlit context (Technical)
- Dynamic upsert pattern: Only updates columns present in input dict, allows waterfall steps to populate incrementally (Architecture)

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

**Note:** ll84_data table is currently empty. Phase 2 will implement live LL84 API fetch.

## Phase 2 Progress

**Data Retrieval Waterfall** — In Progress (1 of 3 plans complete)

**Completed Plans:**
- 02-01: Building storage foundation with building_metrics table (86 typed columns, dynamic upsert, auto-timestamp trigger)

**Next:**
- 02-02: Identity step implementation (LL97 + GeoSearch API)
- 02-03: Energy and mechanical data fetch (LL84 + LL87)

## Session Continuity

Last session: 2026-02-10 14:40 UTC
Stopped at: Completed 02-01-PLAN.md (Building storage foundation)
Resume file: None

**Next steps:** `/gsd:execute-phase 02 02` — Identity Step (LL97 + GeoSearch)
