# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fischer Energy Partners - 50K Building Lead Tool**

An automated system to analyze 50,000+ NYC buildings for preliminary energy audits using public data sources. The system aggregates data from NYC Local Laws (LL84, LL87, LL97) to generate building energy profiles, calculate carbon penalty projections, and create engineering narratives for energy retrofit opportunities.

## Database Architecture

### Production Database: Supabase PostgreSQL (Cloud-Hosted)

**Connection Details:**
- Host: `aws-0-us-west-2.pooler.supabase.com`
- Port: `5432`
- Database: `postgres`
- User: `postgres.lhtuvtfqjovfuwuxckcw`
- Password: `U4Y$A9$x1GBRooAF`
- SSL Mode: `require`

### Database Tables

1. **ll87_raw** - LL87 Energy Audit data (2019-2024 and 2012-2018 periods)
   - All rows preserved including duplicates
   - BBL is primary search key (10-digit numeric, no dashes)
   - Data stored as JSONB with audit_template_id for versioning
   - Query latest audit per building: `SELECT DISTINCT ON (bbl) * FROM ll87_raw ORDER BY bbl, audit_template_id DESC`

2. **ll97_covered_buildings** - LL97 Covered Buildings List (master input)
   - One row per BBL (26,982 buildings)
   - Contains compliance pathway assignments (CP0-CP4)
   - BBL is primary key, includes preliminary BIN and canonical address
   - This is the authoritative source for building identity

3. **ll84_raw** - LL84 Energy Benchmarking data (2023)
   - All rows preserved including duplicates
   - BBL is indexed, data stored as JSONB
   - Query latest per building: `SELECT DISTINCT ON (bbl) * FROM ll84_raw ORDER BY bbl, id DESC`

4. **ll84_data** - LL84 deduplicated structured table
   - One row per BBL with typed columns
   - Includes penalty calculations, energy grades, building metrics
   - Upsert logic handles updates to existing BBLs

## Data Loading Commands

All Python scripts are in `Supabase_script/` directory.

### Load LL87 Data
```bash
cd "Supabase_script"
python ll87_load_supabase.py
```
- Reads: `LL87_2019-2024 (1).xlsx`
- Updates `REPORTING_PERIOD` variable for different datasets
- Truncate-and-replace strategy per reporting period

### Load LL97 Covered Buildings List
```bash
cd "Supabase_script"
python ll97_load_supabase.py
```
- Reads: `cbl_cy25.xlsx` (sheet: "LL97 CBL")
- Truncates and replaces entire table

### Load LL84 Data (Raw)
```bash
cd "Supabase_script"
python ll84_raw_load_supabase.py
```
- Reads: CSV file with LL84 2023 data
- Preserves all rows including duplicates
- Data stored as JSONB

### Load LL84 Data (Deduplicated)
```bash
cd "Supabase_script"
python ll84_load_supabase.py
```
- Same CSV source as raw loader
- Deduplicates by BBL (keeps last occurrence)
- Creates structured typed columns

## Core Architecture Concepts

### BBL as North Star
- **BBL (Borough Block Lot)** is the universal anchor identifier across all operations
- Always 10-digit numeric format in SQL (e.g., `1011190036`)
- BIN (Building Identification Number) is secondary - used for LL84 API queries but derived from BBL
- One BBL can have multiple BINs (campus facilities)

### The 5-Step Waterfall Process

1. **Identity & Compliance** - Query LL97 Covered Buildings List for BBL, BIN, canonical address
2. **Live Usage Fetch** - Query NYC Open Data LL84 API (using BIN from Step 1)
3. **Mechanical Retrieval** - Query LL87 Raw Table for audit data (search 2019-2024 first, fallback to 2012-2018)
4. **LL97 Penalty Calculations** - Python engine calculates penalties for 2024-2029 and 2030-2034 periods
5. **Narrative Generation** - AI generates engineering narratives from LL87 mechanical/envelope data

### Primary vs Secondary Source Hierarchy

When field is available from multiple sources and values conflict, **Primary source always wins**.

Example sources by priority:
- **Identity/Address**: LL97 Covered Buildings List → DOB BIS → GeoSearch API
- **Building Metrics**: LL84 API → PLUTO API → Manual Input
- **Mechanical Systems**: LL87 Raw (2019-2024) → LL87 Raw (2012-2018)

### Address Resolution Rule

The address from **LL97 Covered Buildings List** is the canonical address. All other addresses are aliases for reference only.

### The Dash Protocol

- **SQL/API operations**: Use BBL as 10-digit numeric (`1011190036`)
- **Browser operations (DOF)**: Convert to dashed format (`1-01119-0036`)

## LL97 Penalty Calculator

Three-step formula implemented in Python:

**Step 1: Calculate GHG Emissions**
```
GHG Emissions = (Electricity_kWh × Elec_Coeff) + (NatGas_kBtu × Gas_Coeff) +
                (FuelOil_kBtu × Oil_Coeff) + (Steam_kBtu × Steam_Coeff)
```

**Step 2: Calculate Emissions Limit**
```
Emissions Limit = SUM(UseType_N_sqft × UseType_N_EmissionsFactor) for all use types
```

**Step 3: Calculate Penalty**
```
IF (GHG Emissions - Emissions Limit) > 0
THEN Penalty = (GHG Emissions - Emissions Limit) × $268
ELSE Penalty = $0
```

Calculate separately for both compliance periods (2024-2029 and 2030-2034) using period-specific coefficients and emissions factors. See Section 4.4 in Implementation Plan for full coefficient tables.

## AI Narrative Generation

Applies only to LL87 mechanical/envelope data (LL84 data is stored as-is).

**Six Narrative Categories** (1-2 paragraphs each):
1. Building Envelope Narrative
2. Heating System Narrative
3. Cooling System Narrative
4. Air Distribution System Narrative
5. Ventilation System Narrative
6. Domestic Hot Water System Narrative

**Context Fields Fed to All Narrative Prompts:**
- Year Built
- Largest Property Use Type
- Property GFA (ft²)
- Site Energy Use (kBtu)
- Fuel Oil #2 Use (kBtu)
- District Steam Use (kBtu)
- Natural Gas Use (kBtu)
- Electricity Use - Grid Purchase (kWh)

**Additional LL87-Sourced Fields** (structured data, not AI narratives):
- Building Automation System (Boolean/Narrative)
- Heating Equipment Specs (Boilers, Heat Exchangers, Hot Water Pumps, Zone Equipment)
- Cooling Equipment Specs (Chillers, Chilled Water Pumps, Cooling Towers, Condenser Water Pumps)
- Air Distribution Equipment Specs (Air Handling Units, Rooftop Units, Packaged Units)
- Ventilation Equipment Specs (Make-up Air Units, Dedicated Outdoor Air Systems, Energy Recovery Ventilators)

## NYC Open Data API Endpoints

### GeoSearch API (Address → BBL/BIN Resolution)
- Endpoint: `https://geosearch.planninglabs.nyc/v2/search`
- Parameter: `text={Address}`
- BBL Path: `features[0].properties.addendum.pad.bbl`
- BIN Path: `features[0].properties.addendum.pad.bin`

### PLUTO API (Building Structure Data)
- Endpoint: `https://data.cityofnewyork.us/resource/64uk-42ks.json`
- Query: `$where=bbl={BBL}` (10-digit numeric)
- Key Fields: `ownername`, `numfloors`, `bldgarea`, `yearbuilt`

### LL84 API (Energy Usage Data)
- Endpoint: `https://data.cityofnewyork.us/resource/5zyy-y8am.json`
- Query: `$where=nyc_building_identification='{BIN}'&$order=last_modified_date_property DESC&$limit=1`
- Key Fields: `electricity_use_grid_purchase_kbtu`, `natural_gas_use_kbtu`, `largest_property_use_type`
- Note: BIN field may contain semicolon-delimited multiple values

## Use Type Handling

**42 Primary Use Types** from LL84 (Adult Education, Ambulatory Surgical Center, Automobile Dealership, Bank Branch, College/University, etc.) - stored as flat named columns with square footage values.

**5 LL84 Use Types WITHOUT Emissions Factors** (store sqft but exclude from penalty calc):
- Barracks, Convention Center, Energy/Power Station, Hotel - Gym/Fitness Center Floor Area, Wastewater Treatment Plant

**15 Emissions Factor Use Types NOT in LL84** (exist in penalty calc but no LL84 column):
- Bowling Alley, Convenience Store without Gas Station, Library, Lifestyle Center, Personal Services, Vocational School, and 9 "Other" categories

## Data Deduplication Strategy

### LL87 Dual Dataset Protocol
1. Search 2019-2024 dataset first
2. If no match, search 2012-2018 dataset
3. If match exists in both, take the most recent (higher audit_template_id)

### LL84 Deduplication
- Raw table (`ll84_raw`): Preserves all duplicates
- Structured table (`ll84_data`): One row per BBL, upsert logic on conflict

### Multiple Systems Handling (LL87)
When a building has multiple system variants (e.g., multiple heating plants), all variants are ingested and kept as separate fields. The AI narrative engine synthesizes these in Step 5.

## Important Constraints

- **Compliance Year Cycles**: LL87 compliance is every 10 years ending in 6 (2016, 2026, etc.)
- **Campus Buildings**: Single BBL can cover multiple physical structures - human confirmation gate required before proceeding to Steps 2-5 in manual workflow
- **BIN vs BBL**: Although BBL is the North Star, LL84 API is indexed by BIN, so pass the BIN resolved from BBL in Step 1
- **Carbon Penalty Per Unit**: $268 per tCO2e excess emissions
- **Drop and Replace Strategy**: All raw data tables use truncate-and-replace when new data is loaded

## Development Notes

- All database credentials should be stored as environment variables in production (currently hardcoded in scripts for initial setup)
- Migration to any other PostgreSQL host requires updating connection strings only - no code or schema changes
- Windows Server 2022 maintains nightly backup via `pg_dump` from Supabase for disaster recovery
- No git repository configured (this is a data processing project with script-based workflows)
