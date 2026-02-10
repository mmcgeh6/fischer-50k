---
phase: 03-calculations-narratives
plan: 01
subsystem: calculations
tags: [ll97, penalties, emissions, decimal-precision, database-schema]
requires:
  - 02-01-building-metrics-table
  - 02-03-waterfall-orchestrator
provides:
  - ll97-penalty-calculator
  - calculation-columns-schema
  - emissions-factors-database
affects:
  - 03-02-penalty-batch-processor
  - 03-03-narrative-engine
tech-stack:
  added: []
  patterns:
    - decimal-precision-arithmetic
    - period-specific-coefficients
    - idempotent-migrations
key-files:
  created:
    - lib/calculations.py
    - tests/test_calculations.py
  modified:
    - lib/storage.py
key-decisions:
  - name: Use Decimal precision for all calculations
    rationale: Avoid floating-point rounding errors in financial calculations
    impact: Accurate penalty calculations to the cent
  - name: Period-specific coefficients and emissions factors
    rationale: LL97 has different carbon coefficients for 2024-2029 vs 2030-2034
    impact: Calculator supports both compliance periods
  - name: 55 use-type emissions factors
    rationale: Complete coverage of all LL84 use types plus emissions-factor-only types
    impact: Calculator handles all building use-type combinations
  - name: None handling for missing energy data
    rationale: Not all buildings have complete energy data
    impact: Calculator returns None dict when energy data missing, avoids false zeros
duration: 3.5 min
completed: 2026-02-10
---

# Phase 03 Plan 01: Penalty Calculation Engine Summary

**One-liner:** LL97 penalty calculator with Decimal precision, 55 use-type emissions factors, and 12 new database columns for storing calculation results and narratives.

## Performance

**Execution Metrics:**
- Duration: 3.5 minutes
- Started: 2026-02-10 21:43 UTC
- Completed: 2026-02-10 21:46 UTC
- Tasks completed: 2/2
- Files created: 2
- Files modified: 1
- Test coverage: 4 tests (known values, None handling, extraction, completeness)

## Accomplishments

Created the computational core of Phase 3 with two deliverables:

**1. Database Schema Extension (lib/storage.py)**
- Added `migrate_add_calculation_columns()` function for idempotent schema migrations
- Extended `building_metrics` table with 12 new columns:
  - 6 penalty calculation columns (NUMERIC): `ghg_emissions_2024_2029`, `emissions_limit_2024_2029`, `penalty_2024_2029`, `ghg_emissions_2030_2034`, `emissions_limit_2030_2034`, `penalty_2030_2034`
  - 6 narrative columns (TEXT): `envelope_narrative`, `heating_narrative`, `cooling_narrative`, `air_distribution_narrative`, `ventilation_narrative`, `dhw_narrative`
- Updated `create_building_metrics_table()` to include new columns in fresh installs
- Migration tested successfully on production Supabase database

**2. LL97 Penalty Calculation Engine (lib/calculations.py)**
- Implemented complete 3-step LL97 penalty formula using Decimal precision
- Added `CARBON_COEFFICIENTS` dict with period-specific coefficients (4 fuel types × 2 periods)
- Added `EMISSIONS_FACTORS` dict with 55 use-type emissions factors (2 periods each)
- Created `calculate_ghg_emissions()` for Step 1 (energy usage → GHG emissions)
- Created `calculate_emissions_limit()` for Step 2 (use-type sqft → emissions limit)
- Created `calculate_ll97_penalty()` for Step 3 (GHG - limit → penalty with $268 multiplier)
- Created `extract_use_type_sqft()` helper to bridge DB column names (with `_sqft`) to calculator keys (without suffix)
- Comprehensive None/missing data handling (returns None dict when energy data unavailable)

**3. Test Suite (tests/test_calculations.py)**
- Test 1: Known values verification (10M kWh + 5M kBtu gas → $642,441.56 penalty)
- Test 2: None handling (missing energy data returns None for all fields)
- Test 3: extract_use_type_sqft correctness (strips _sqft suffix, filters non-use-type columns)
- Test 4: Emissions factors completeness (55 factors per period verified)

## Task Commits

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | Extend building_metrics schema with 12 new columns | e194e1d | ✓ Complete |
| 2 | Create LL97 penalty calculation engine | f418db4 | ✓ Complete |

## Files Created

| File | Purpose | Lines | Exports |
|------|---------|-------|---------|
| `lib/calculations.py` | LL97 penalty calculator with Decimal precision | 391 | calculate_ghg_emissions, calculate_emissions_limit, calculate_ll97_penalty, extract_use_type_sqft, CARBON_COEFFICIENTS, EMISSIONS_FACTORS |
| `tests/test_calculations.py` | Verification test suite for penalty calculator | 42 | - |

## Files Modified

| File | Changes | Reason |
|------|---------|--------|
| `lib/storage.py` | Added migrate_add_calculation_columns(), updated create_building_metrics_table() | Schema extension for Phase 3 columns |

## Decisions Made

**1. Decimal Precision for All Arithmetic**
- **Context:** Financial calculations require exact precision, floats accumulate rounding errors
- **Decision:** Use Python's `Decimal` type exclusively, initialize from strings not floats
- **Implementation:** All coefficients/factors as `Decimal("0.00758")`, all arithmetic operations return Decimal
- **Impact:** Penalty calculations accurate to the cent, no floating-point drift

**2. Period-Specific Coefficients and Factors**
- **Context:** LL97 has two compliance periods with different carbon coefficients and emissions factors
- **Decision:** Store coefficients/factors in nested dicts keyed by period ("2024-2029", "2030-2034")
- **Implementation:** `CARBON_COEFFICIENTS[period]`, `EMISSIONS_FACTORS[period]`, calculate for both periods in single call
- **Impact:** Calculator supports both compliance periods, future-proof for additional periods

**3. 55 Use-Type Emissions Factors**
- **Context:** LL84 has 42 primary use types, LL97 has 54 emissions factors, need complete coverage
- **Decision:** Map all 54 LL97 factors plus "other" (Restaurant/Bar) = 55 total, omit 13 columns without factors
- **Implementation:** EMISSIONS_FACTORS keys match storage.py column names (without _sqft suffix)
- **Impact:** Calculator handles all possible building use-type combinations, skips columns without factors

**4. None Handling for Missing Energy Data**
- **Context:** Not all buildings have complete energy data (especially non-LL84 buildings)
- **Decision:** Return None dict (all 6 keys = None) when no energy data available, don't calculate false zeros
- **Implementation:** Check `has_energy_data = any([electricity > 0, gas > 0, oil > 0, steam > 0])` before calculation
- **Impact:** Downstream code can distinguish "no penalty" (compliant) from "no data" (cannot calculate)

**5. extract_use_type_sqft Bridge Function**
- **Context:** Database columns have `_sqft` suffix, calculator keys don't (e.g., `office_sqft` → `office`)
- **Decision:** Create helper function to extract and transform column names
- **Implementation:** Iterate USE_TYPE_SQFT_COLUMNS, strip suffix, filter None/zero values
- **Impact:** Clean separation between database schema and calculator API, easier to use

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**1. Test Module Import Path**
- **Issue:** Running `python tests/test_calculations.py` failed with `ModuleNotFoundError: No module named 'lib'`
- **Cause:** Python doesn't automatically add parent directory to sys.path when running scripts
- **Resolution:** Ran tests via `python -c "import sys; sys.path.insert(0, '.'); ..."` to inject parent directory
- **Prevention:** In production, use `pytest` or `python -m tests.test_calculations` which handle paths correctly

**2. Windows Path Handling in Git**
- **Issue:** Git warns "LF will be replaced by CRLF" for new Python files
- **Cause:** Windows git config auto-converts line endings
- **Resolution:** No action needed - warning only, doesn't affect functionality
- **Prevention:** Could set `.gitattributes` with `*.py text eol=lf` but not critical

## Next Phase Readiness

**Ready for Phase 3 Plan 2 (Penalty Batch Processor):**
- ✓ Calculator functions ready to import and use
- ✓ Database schema includes all required columns for storing results
- ✓ extract_use_type_sqft() provides clean interface for building data
- ✓ None handling allows batch processor to skip buildings without energy data

**Ready for Phase 3 Plan 3 (Narrative Engine):**
- ✓ Database schema includes 6 narrative TEXT columns
- ✓ Column names match narrative categories from CLAUDE.md spec

**Blockers:** None

**Recommendations for Next Plans:**
1. Plan 02 (Batch Processor): Use `calculate_ll97_penalty()` + `extract_use_type_sqft()` → `upsert_building_metrics()`
2. Plan 03 (Narrative Engine): Fetch LL87 data, generate narratives, store in narrative columns
3. Consider adding batch processing progress indicator (e.g., tqdm) for 26,982 buildings

## Technical Notes

**Carbon Coefficients Source:**
- From FEP_50k Implementation_Plan.md Section 4.4
- 2024-2029 electricity: 0.000288962 tCO2e/kWh (NYC grid carbon intensity)
- 2030-2034 electricity: 0.000145 tCO2e/kWh (50% reduction target)
- Gas/Oil/Steam coefficients constant across both periods (fuel-specific carbon content)

**Emissions Factors Source:**
- From FEP_50k Implementation_Plan.md Section 4.4
- 55 use types mapped to LL84 column names in snake_case
- "Other - Restaurant/Bar" mapped to generic "other" key (0.02381 / 0.008505075)
- 13 columns without factors omitted: barracks, convention_center, convenience_store_with_gas_station, hotel_gym, wastewater_treatment_plant, swimming_pool, mixed_use_property, police_station, fire_station, prison_incarceration, residential_care_facility, other_utility, energy_power_station

**Penalty Formula:**
```
Step 1: GHG = (Elec_kWh × Elec_Coeff) + (Gas_kBtu × Gas_Coeff) + (Oil_kBtu × Oil_Coeff) + (Steam_kBtu × Steam_Coeff)
Step 2: Limit = SUM(UseType_sqft × UseType_Factor) for all use types
Step 3: Penalty = max(GHG - Limit, 0) × $268
```

**Test Results:**
- Known values test: 10M kWh + 5M kBtu gas + 100k sqft office → GHG 3155.17 tCO2e, Limit 758.00 tCO2e, Penalty $642,441.56 ✓
- None handling: All None inputs → All None outputs ✓
- Extraction: office_sqft → office, hotel_sqft → hotel, bbl ignored ✓
- Completeness: 55 factors per period ✓

**Performance Characteristics:**
- Calculator is stateless (no caching, no side effects)
- O(n) complexity where n = number of use-type columns with data
- Expected ~1ms per building calculation (Decimal arithmetic is fast)
- Batch processor can calculate 26,982 buildings in ~30 seconds
