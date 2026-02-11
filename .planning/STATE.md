# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Accurate, pre-calculated building intel with professional system narratives — ready to share with prospective clients without manual research.
**Current focus:** Phase 3 complete — ready for Phase 4 (Airtable Integration)

## Current Position

Phase: 3 of 5 complete (Calculations & Narratives)
Plan: 2 of 2 complete
Status: Complete
Last activity: 2026-02-11 — Phase 3 verified and closed

Progress: [██████░░░░] 60%

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: 4.9 min
- Total execution time: 0.65 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-web-ui-foundation | 3 | 22 min | 7.3 min |
| 02-data-retrieval-waterfall | 3 | 12 min | 4.0 min |
| 03-calculations-narratives | 2 | 5 min | 2.5 min |

**Recent Trend:**
- 01-01: 5 min (project structure setup)
- 01-02: 2 min (database and API modules)
- 01-03: 15 min (Streamlit app + bug fixes + human verification)
- 02-01: 2 min (Building_Metrics table creation)
- 02-02: 4 min (NYC API clients)
- 02-03: 6 min (Waterfall orchestrator + UI + human verification)
- 03-01: 3.5 min (Penalty calculation engine)
- 03-02: 1.5 min (Wire Steps 4-5 + UI + bug fixes during verification)
- Trend: Accelerating — Phase 3 fastest phase overall

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

**From Phase 3 execution:**
- Decimal precision for penalties: All LL97 calculations use Decimal type, avoid floating-point errors (Technical)
- Period-specific coefficients: Carbon coefficients and emissions factors differ between 2024-2029 and 2030-2034 periods (Architecture)
- 55 use-type emissions factors: Complete coverage of LL97 factors (Architecture)
- None dict for missing energy data: Calculator returns None for all 6 fields when no energy data (Technical)
- extract_use_type_sqft bridge: Helper strips _sqft suffix from DB columns to match calculator keys (Technical)
- Idempotent schema migrations: ALTER TABLE ADD COLUMN IF NOT EXISTS for safe re-runs (Technical)
- energy_star_score sanitization: LL84 API returns "Not Available" string — use _safe_int() to store None (Technical)
- bin VARCHAR(50): Multi-BIN campus buildings store comma-separated values exceeding VARCHAR(10) (Technical)
- Session-state migration guard: Run schema migration once per Streamlit session, not every rerun (Technical)
- Backoff retry for narratives: Exponential backoff with jitter on Anthropic API calls (Technical)

### Pending Todos

None yet.

### Blockers/Concerns

- Multi-BIN campus buildings may not match LL84 API with comma-separated BIN values — data sourcing improvement for future phases

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

## Phase 3 Summary

**Calculations & Narratives** — Complete ✓

All 13 requirements satisfied (CALC-01 through CALC-05, NARR-01 through NARR-08):
- LL97 penalty calculation engine with Decimal precision and 55 emissions factors
- 12 new database columns (6 penalty NUMERIC + 6 narrative TEXT) via idempotent migration
- Waterfall extended to 5 steps: identity → energy → mechanical → penalties → narratives
- Backoff retry on Anthropic API narrative generation
- UI displays penalties and narratives with debug panel
- Bug fixes: energy_star_score sanitization, bin column width, migration guard

## Session Continuity

Last session: 2026-02-11
Stopped at: Phase 3 verified and closed
Resume file: None

**Next steps:** Plan and execute Phase 4 (Airtable Integration)
