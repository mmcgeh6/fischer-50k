# Architecture

**Analysis Date:** 2026-02-06

## Pattern Overview

**Overall:** Five-Stage Waterfall with Cloud-Hosted Data Hub

The system implements a **Live-Hybrid Aggregator Architecture** that combines persistent cloud storage (Supabase PostgreSQL) for heavy/historical datasets with verified NYC Open Data APIs for live identity and energy data. All operations route through a universal BBL (Borough Block Lot) identifier. The architecture supports both manual single-building testing (Phase A) and bulk batch automation (Phase B).

**Key Characteristics:**
- **Cloud-first database**: Supabase PostgreSQL (aws-0-us-west-2.pooler.supabase.com) as single source of truth; Windows Server 2022 maintains nightly backup via pg_dump
- **BBL as North Star**: All 50,000+ buildings indexed by 10-digit numeric BBL format (1011190036, no dashes in SQL)
- **API-driven identity & verification**: GeoSearch, PLUTO, LL84 APIs called in sequence per building
- **Local calculation engine**: Python-based LL97 penalty calculator runs locally (not API-dependent)
- **Data stratification**: Raw JSONB tables for audit data (ll87_raw, ll84_raw) + structured typed table (Building_Metrics) for finished leads
- **Truncate-and-replace loading**: All raw data tables use drop/clear-and-replace strategy when new source files arrive

## Layers

**Layer 1: Data Ingestion (Raw Lakes)**

- Purpose: Preserve source data as-is without modification or deduplication
- Location:
  - `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\ll87_load_supabase.py` - LL87 audit data loader
  - `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\ll84_raw_load_supabase.py` - LL84 raw energy data loader
  - `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\ll97_load_supabase.py` - LL97 covered buildings master list loader
- Contains: Raw Excel/CSV data converted to PostgreSQL tables (ll87_raw as JSONB, ll84_raw as JSONB, ll97_covered_buildings as structured columns)
- Depends on: Excel/CSV source files in `Supabase_script/` directory, Supabase PostgreSQL instance
- Used by: Step 3 (Mechanical Retrieval) and Step 1 (Identity & Compliance) in waterfall; verification and QA queries

**Layer 2: Data Deduplication & Transformation (Clean Data)**

- Purpose: Transform raw dumps into deduplicated, structured data ready for business logic
- Location: `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\ll84_load_supabase.py` (structured version)
- Contains: One-row-per-BBL structured table (ll84_data) with typed columns for all energy metrics, upsert logic on conflict
- Depends on: LL84 CSV raw data (deduplicates by BBL, keeps last occurrence)
- Used by: Step 2 (Live Usage Fetch) to populate Building_Metrics energy fields

**Layer 3: API Orchestration & Resolution (Identity & Live Data)**

- Purpose: Query live verified APIs to resolve addresses to BBL/BIN and fetch current energy data
- Location: `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Get Building Data Fischer.json` (N8N workflow), implied in waterfall implementation
- Contains: Calls to GeoSearch API (address→BBL/BIN), PLUTO API (structure data), LL84 API (energy usage)
- Depends on: NYC Open Data APIs, GeoSearch v2 API, live internet connectivity
- Used by: Steps 1 (identity resolution), 2 (energy fetch), and 4 (context data for calculations)

**Layer 4: Calculation Engine (LL97 Penalty Calculation)**

- Purpose: Apply LL97 three-step formula to calculate emissions, limits, and penalty projections
- Location: (Python script location not yet written; referenced in Implementation Plan Section 4.4)
- Contains: Carbon coefficients (electricity, natural gas, fuel oil, steam) × consumption + Emissions factors × use type sqft → penalty calculation
- Depends on: Energy consumption data from Layer 2, use-type square footage from LL84, emissions factors table (57 types specified in Implementation Plan)
- Used by: Step 4 (Penalty Calculation) to output 2024-2029 and 2030-2034 penalty projections

**Layer 5: Narrative Generation (AI Engineering Narratives)**

- Purpose: Convert LL87 mechanical specs into professional engineering narratives
- Location: (Prompt templates and orchestration not yet implemented; framework specified in Implementation Plan Section 2.5)
- Contains: Six narrative categories (Building Envelope, Heating, Cooling, Air Distribution, Ventilation, DHW) + BAS + 4 equipment spec categories
- Depends on: LL87 mechanical data from Layer 1, context fields from Layer 2 (year built, GFA, energy use)
- Used by: Step 5 to populate structured narrative fields in Building_Metrics table

## Data Flow

**Five-Step Waterfall (per Building):**

1. **Identity & Compliance (Step 1)**
   - Input: Address or BBL
   - Primary: Query LL97_Covered_Buildings (Supabase ll97_covered_buildings table) by address or BBL
   - If not found: Query GeoSearch API to resolve address → BBL/BIN
   - Output: Official BBL, BIN, canonical address, compliance pathway (CP0-CP4)
   - Human gate: Engineer confirms building identity before proceeding (critical for campuses)

2. **Live Usage Fetch (Step 2)**
   - Input: BIN from Step 1
   - Query: LL84 API (NYC Open Data 5zyy-y8am) using BIN as index
   - Fallback: PLUTO API (64uk-42ks) for Year Built and GFA if LL84 missing
   - Output: Electricity (kWh), Natural Gas (kBtu), Fuel Oil (kBtu), Steam (kBtu), EUI, GFA (sqft), 42 use-type square footages
   - Treatment: Data stored as-is in Building_Metrics table (no AI transformation)

3. **Mechanical Retrieval (Step 3)**
   - Input: BBL from Step 1
   - Query: LL87_Raw (Supabase ll87_raw JSONB table) with dual-dataset protocol:
     - Search 2019-2024 dataset first
     - If no match, search 2012-2018 dataset
     - If both exist, take highest audit_template_id (most recent)
   - Output: Boilers, chillers, heat exchangers, envelope specs, automation system type
   - Treatment: All system variants preserved as separate fields (not deduplicated)

4. **LL97 Penalty Calculations (Step 4)**
   - Input: Energy data (Step 2) + Use-type square footage (Step 2) + Carbon coefficients + Emissions factors
   - Formula (3 steps):
     ```
     Step 4a: GHG_Emissions = (Elec_kWh × 0.000288962) + (Gas_kBtu × 0.00005311) + (Oil_kBtu × 0.00007421) + (Steam_kBtu × 0.00004493)
     Step 4b: Emissions_Limit = SUM(UseType_N_sqft × UseType_N_EmissionsFactor)
     Step 4c: IF (GHG_Emissions - Emissions_Limit) > 0 THEN Penalty = Excess × $268 ELSE Penalty = $0
     ```
   - Run separately for 2024-2029 and 2030-2034 periods (different coefficients/factors)
   - Output: Six values per building (Emissions, Limit, Penalty for each period)

5. **Narrative Generation (Step 5)**
   - Input: LL87 mechanical specs (Step 3) + context (year built, use type, GFA, energy consumption)
   - Process: Feed each mechanical category + context to AI system prompt
   - Output: Six narrative paragraphs (1-2 each) + 4 equipment spec categories (structure TBD)
   - Scope: LL87 data only (LL84 energy data is not narrativized)

**State Management:**

- Each step holds returned data in temporary memory during waterfall execution
- At final stage (Step 5 completion), all data is cross-checked, filtered, verified
- Then committed atomically to Building_Metrics table (SQL INSERT or UPDATE)
- Raw layers (ll87_raw, ll84_raw, ll97_covered_buildings) remain unchanged; they are source of truth for re-processing

## Key Abstractions

**BBL (Borough Block Lot) - Universal Identifier**

- Purpose: Single unambiguous anchor across all 50,000 buildings and all data sources
- Format: 10-digit numeric string in SQL (1011190036) with no dashes
- Scope: One BBL = one building (even if campus spans multiple physical structures)
- Related identifier: BIN (Building Identification Number) is secondary; used as API query parameter for LL84 but always derived from BBL
- Impact: Dash Protocol - SQL operations use numeric format; browser operations (DOF) convert to dashed format (1-01119-0036)

**Compliance Pathway (CP0-CP4) - LL97 Status**

- Purpose: Distinguish which compliance rule applies to each building
- Types:
  - CP0: Article 320 beginning 2024 (largest/first group)
  - CP1: Article 320 beginning 2026
  - CP2: Article 320 beginning 2035
  - CP3: Article 321 One-Time Compliance
  - CP4: City Portfolio Reductions
- Stored as: Boolean columns in ll97_covered_buildings table
- Master source: LL97 Covered Buildings List (cbl_cy25.xlsx), authoritative for all 26,982 buildings

**Primary/Secondary Source Hierarchy**

- Purpose: Resolve conflicting data when field available from multiple sources
- Rule: Primary source always wins; secondary is fallback only
- Examples:
  - Building metrics (GFA, year built): LL84 API > PLUTO API > Manual Input
  - Mechanical systems: LL87 2019-2024 > LL87 2012-2018
  - Address (canonical): LL97 Covered Buildings List > DOB BIS > Self-reported
- Implementation: Waterfall checks Primary first; only falls through to Secondary if Primary missing/null

**Address Resolution Rule**

- Purpose: Prevent vanity address mismatches across multiple sources
- Rule: Address from LL97 Covered Buildings List is canonical; all others are aliases
- Impact: Searches key off BBL or official address, never off self-reported or DOF alias
- Benefit: Prevents duplicate leads when same building has multiple address variants

**Data Deduplication Strategy**

- LL87 Dual Dataset: Two historical periods (2019-2024, 2012-2018) queried in sequence; higher audit_template_id wins
- LL84 Deduplication: Raw table (ll84_raw) preserves all duplicates; structured table (ll84_data) keeps last occurrence by BBL (upsert logic)
- LL97 Covered List: One row per BBL (26,982 unique buildings by design)

## Entry Points

**Manual Single-Building Entry Point (Phase A - Testing)**

- Location: Lightweight web UI (not yet implemented; referenced in Implementation Plan Section 5.1)
- Triggers: User enters address or BBL
- Flow: Address/BBL → Step 1 (resolve) → Engineer confirms → Steps 2-5 (waterfall) → Save to Building_Metrics
- Output: Full building lead dashboard

**Batch Automation Entry Point (Phase B - Bulk Run)**

- Location: Python script or Cron job (not yet implemented; referenced in Implementation Plan Section 5.2)
- Triggers: Configuration switch (RUN_MODE=BATCH) or scheduled job
- Input: LL97 Covered Buildings List (ll97_covered_buildings table with 26,982 rows)
- Flow: Loop through BBL rows → Steps 1-5 (waterfall per building, no confirmation gate) → Auto-save to Building_Metrics
- Rate: ~1,000 records/night (configurable batch processing)
- Output: Populated Building_Metrics table with all 50,000 buildings

**Data Loading Entry Points (Infrastructure)**

- `ll87_load_supabase.py`: Read LL87 Excel file → clean BBLs → convert to JSONB → clear-and-replace ll87_raw table
- `ll97_load_supabase.py`: Read LL97 Excel file → structure columns → upsert ll97_covered_buildings table
- `ll84_load_supabase.py`: Read LL84 CSV → deduplicate by BBL → upsert ll84_data table
- All located in `c:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\`

## Error Handling

**Strategy:** Three-tier fallback + human confirmation gate

**Patterns:**

- **Identity Resolution Failure**: If BBL not found in LL97 Covered List, query GeoSearch API. If GeoSearch fails, flag as "Address Not Resolvable" and hold for manual review.

- **API Timeouts/Missing Data**: If LL84 missing, fallback to PLUTO. If PLUTO missing, store as NULL and proceed with what's available. LL87 fallback to 2012-2018 if 2019-2024 missing.

- **Calculation Errors**: If use-type square footage missing, default to "Other" category for penalty calculation. If energy consumption is 0 or NULL, calculate emissions as 0 and proceed.

- **Narrative Generation Failures**: If LL87 data insufficient (< 3 system specs), synthesize generic narrative; if all missing, output "No audit data available" placeholder.

- **Human Confirmation Gate**: Phase A manual workflow requires engineer to confirm building identity before proceeding to Steps 2-5. Prevents campus mismatches and multi-building errors. Phase B batch mode bypasses this gate (assumes LL97 list is authoritative).

## Cross-Cutting Concerns

**Logging:** Not yet specified. Recommend SQL audit trail per building (timestamp, step completed, data sources queried, errors encountered).

**Validation:**
- BBL format: Validate 10-digit numeric format before SQL queries
- Address resolution: Confirm at least one result returned from GeoSearch before proceeding
- Energy data: Confirm all four fuel types (electricity, gas, oil, steam) have numeric values or are explicitly NULL
- Use-type square footages: Validate sum of all 42 use-type sqft matches total GFA within 2% tolerance

**Authentication:**
- Database: Supabase connection string in environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
- APIs: GeoSearch/PLUTO/LL84 are public (no auth required)
- N8N workflows: Assumed self-hosted or SaaS with standard N8N authentication

**Performance:**
- LL87 raw queries: Index on (bbl, audit_template_id DESC) for fast lookups
- LL97 covered list: Index on bbl for O(1) resolution
- LL84 API: Cached by NYC Open Data upstream; local queries to ll84_data table with indices on energy fields
- Batch processing: 1,000 records/night means ~50 days for full 50,000-building run (configurable)

---

*Architecture analysis: 2026-02-06*
