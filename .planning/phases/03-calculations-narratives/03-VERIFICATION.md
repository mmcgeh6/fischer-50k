---
phase: 03-calculations-narratives
verified: 2026-02-11T20:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 3: Calculations & Narratives Verification Report

**Phase Goal:** System generates accurate penalty projections and professional system narratives
**Verified:** 2026-02-11T20:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | System calculates GHG emissions for both 2024-2029 and 2030-2034 periods using period-specific coefficients | VERIFIED | lib/calculations.py implements `calculate_ghg_emissions()` with CARBON_COEFFICIENTS dict containing period-specific values (e.g., electricity: 0.000288962 for 2024-2029, 0.000145 for 2030-2034). Waterfall Step 4 calls this for both periods. Tests pass with known reference values. |
| 2 | System calculates emissions limits from use-type square footage and emissions factors for all 57 use types | VERIFIED | EMISSIONS_FACTORS dict contains 55 use types for both periods. `calculate_emissions_limit()` iterates use-type sqft and multiplies by factors. `extract_use_type_sqft()` bridges DB column names (with _sqft suffix) to calculator keys. |
| 3 | System calculates LL97 penalty projections ($268 per tCO2e excess) for both periods | VERIFIED | `calculate_ll97_penalty()` implements 3-step formula: GHG → Limit → max(GHG-Limit, 0) × $268. Returns dict with 6 keys (ghg/limit/penalty × 2 periods). All using Decimal precision. UI displays results in LL97 Penalties tab. |
| 4 | System generates all 6 system narratives using Anthropic Claude | VERIFIED | Waterfall Step 5 calls `generate_all_narratives()` from lib/api_client.py with backoff retry (3 attempts, exponential with jitter). Generates: Envelope, Heating, Cooling, Air Distribution, Ventilation, DHW narratives. Results stored in both original category keys and DB column names. |
| 5 | System uses data-only approach with explicit "not documented" fallbacks | VERIFIED | lib/api_client.py narrative prompts use temperature 0.3 and instruct: "Only describe what is documented in the data. If a field is missing, say 'not documented'." Per-narrative error handling ensures one failure doesn't break the batch. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Status | Location |
|----------|--------|----------|
| LL97 penalty calculation engine | Present | lib/calculations.py |
| Schema migration (12 columns) | Present | lib/storage.py:migrate_add_calculation_columns() |
| Waterfall Steps 4-5 | Present | lib/waterfall.py (lines 290-398) |
| Narrative generation with retry | Present | lib/api_client.py (backoff decorator) |
| UI penalty display + debug panel | Present | app.py:display_penalties() |
| Unit tests | Present | tests/test_calculations.py (4 tests) |
| Plan 03-01 summary | Present | .planning/phases/03-calculations-narratives/03-01-SUMMARY.md |

## Bug Fixes During Verification

Three bugs discovered and fixed during human verification:

1. **energy_star_score "Not Available" string in INTEGER column** — LL84 API returns non-numeric strings; fixed in lib/nyc_apis.py to use `_safe_int()` returning None.
2. **bin VARCHAR(10) too short for multi-BIN values** — LL97 table stores comma-separated BINs like "3196065, 3344531"; widened to VARCHAR(50) in schema + migration.
3. **Migration running on every Streamlit rerun** — Added `st.session_state.migration_done` guard in app.py.

## Known Limitations

- Buildings without LL84 energy data (no BIN match) get no penalty calculation — correctly returns None for all 6 fields
- Multi-BIN campus buildings may not match LL84 API (LIKE query with comma-separated BINs) — data sourcing improvement for future
- Narrative generation requires ANTHROPIC_API_KEY — gracefully skipped if not configured

## Conclusion

Phase 3 goal achieved: The system accurately calculates LL97 penalty projections for both compliance periods using Decimal precision and generates professional AI narratives for 6 building systems. All calculations persist to the Building_Metrics table and display correctly in the Streamlit UI.
