---
phase: 01-web-ui-foundation
plan: 02
subsystem: api
tags: [database, claude-api, narrative-generation, supabase, anthropic]

# Dependency graph
requires: [01-01]
provides:
  - Database module with fetch_building_by_bbl() function
  - Claude API client with generate_all_narratives() function
  - 6 narrative categories for building system analysis
affects: [01-03, streamlit-app]

# Tech tracking
tech-stack:
  added: []
  patterns: [st.connection() for database access, data-only narrative generation, per-narrative error handling]

key-files:
  created:
    - lib/database.py
    - lib/api_client.py
  modified: []

key-decisions:
  - "Used st.connection() for automatic caching (1h for static data, 10m for energy data)"
  - "Data-only narrative approach: explicit 'not documented' fallbacks, no inferences"
  - "Low temperature (0.3) for Claude to ensure analytical consistency"
  - "Per-narrative error handling: one failure doesn't break entire batch"

patterns-established:
  - "Database queries follow 5-step waterfall: LL97 identity → LL84 energy → LL87 audit"
  - "LL87 dual dataset protocol: prefer 2019-2024, fallback to 2012-2018"
  - "TTL caching strategy: 1h for static data, 10m for potentially updated data"
  - "Equipment extraction defensive: handles varied/missing field names in LL87 JSONB"

# Metrics
duration: 2min
completed: 2026-02-06
---

# Phase 01 Plan 02: Database and API Client Modules Summary

**Database module queries LL97/LL84/LL87 tables; Claude API client generates 6 data-only system narratives with error handling**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-06T15:32:11Z
- **Completed:** 2026-02-06T15:34:12Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Database module retrieves building data from all three Supabase tables
- Claude API client generates 6 system narratives with data-only approach
- Both modules use Streamlit secrets for credential management
- Error handling prevents complete failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Create database module** - `c6477e2` (feat)
2. **Task 2: Create Claude API client module** - `9d87797` (feat)

## Files Created/Modified

### Created
- `lib/database.py` - Database access module
  - `fetch_building_by_bbl()`: Query all three tables (LL97, LL84, LL87) for given BBL
  - `get_building_count()`: Get total count of covered buildings
  - Uses st.connection() for automatic caching and connection pooling

- `lib/api_client.py` - Claude API client
  - `NARRATIVE_CATEGORIES`: 6 system categories (Envelope, Heating, Cooling, Air Distribution, Ventilation, DHW)
  - `generate_all_narratives()`: Generate all 6 narratives for a building
  - `generate_single_narrative()`: Generate one narrative for testing/regeneration
  - Data-only approach with explicit "not documented" fallbacks

### Modified
None

## Decisions Made

**1. TTL Caching Strategy**
- Static data (LL97, LL87): 1 hour TTL
- Energy data (LL84): 10 minutes TTL
- Rationale: Balance freshness with query performance; LL84 may update more frequently

**2. Data-Only Narrative Prompts**
- System prompt enforces: "If specific data is missing, explicitly state 'not documented' — do NOT infer or assume"
- Temperature 0.3 for analytical consistency
- Rationale: Accuracy over completeness; no hallucination risk

**3. Per-Narrative Error Handling**
- Each narrative generation wrapped in try/except
- Failure of one narrative doesn't break entire batch
- Error messages stored in place of narrative
- Rationale: Resilience for production use; partial data better than no data

**4. LL87 Dual Dataset Protocol**
- SQL query prefers 2019-2024 dataset over 2012-2018
- Uses CASE expression in ORDER BY clause
- Rationale: Matches CLAUDE.md specification for audit data freshness

## Deviations from Plan

None - plan executed exactly as written.

## Technical Implementation Notes

### Database Module Architecture
```python
# Three-step data retrieval follows 5-step waterfall:
1. Query ll97_covered_buildings (identity: BBL, BIN, address, compliance pathway)
2. Query ll84_data (energy metrics: GFA, EUI, fuel usage, pre-calculated penalties)
3. Query ll87_raw (audit data: JSONB with DISTINCT ON for latest audit)
```

### API Client Architecture
```python
# Narrative generation flow:
1. Extract equipment data from LL87 JSONB (category-specific field mapping)
2. Build context from building data (year, type, GFA, energy usage)
3. Generate narrative using Claude Sonnet 4.5 (temperature 0.3)
4. Return text or error message (per-narrative exception handling)
```

### Key Query Patterns

**LL97 Identity Query:**
```sql
SELECT bbl, bin_preliminary as bin, address_canonical as address, compliance_pathway
FROM ll97_covered_buildings
WHERE bbl = :bbl
```

**LL87 Dual Dataset Query:**
```sql
SELECT DISTINCT ON (bbl) bbl, audit_template_id, reporting_period, raw_data
FROM ll87_raw
WHERE bbl = :bbl
ORDER BY bbl,
         CASE WHEN reporting_period = '2019-2024' THEN 1 ELSE 2 END,
         audit_template_id DESC
```

**LL84 Energy Data Query:**
```sql
SELECT year_built, property_gfa, electricity_use_grid_purchase_kwh,
       penalty_2024_2029, penalty_2030_2034, ...
FROM ll84_data
WHERE bbl = :bbl
```

## Integration Points

### Database Module Exports
- `fetch_building_by_bbl(bbl: str) -> Optional[Dict[str, Any]]`
- `get_building_count() -> int`

### API Client Exports
- `NARRATIVE_CATEGORIES: List[str]` (6 categories)
- `generate_all_narratives(building_data: Dict) -> Dict[str, str]`
- `generate_single_narrative(building_data: Dict, category: str) -> str`

### Consumed By (Next Plans)
- Plan 01-03: Streamlit app imports both modules
- App will use `fetch_building_by_bbl()` for data retrieval
- App will use `generate_all_narratives()` for narrative generation

## User Setup Required

**External services require manual configuration.** Users must:

1. **Configure Supabase credentials** in `.streamlit/secrets.toml`:
   - Copy from `.streamlit/secrets.toml.example`
   - Update `[connections.postgresql].password` field
   - Connection details already configured (host, port, database, user)

2. **Configure Anthropic API key** in `.streamlit/secrets.toml`:
   - Get API key from Anthropic Console -> API Keys -> Create key
   - Update `ANTHROPIC_API_KEY` field

## Next Phase Readiness

**Ready for Streamlit app development (Plan 03):**
- Database module can query all three tables independently
- API client can generate narratives when called
- Both modules syntax-validated and import successfully
- Error handling in place for missing data/failed API calls

**No blockers or concerns.**

---
*Phase: 01-web-ui-foundation*
*Completed: 2026-02-06*
