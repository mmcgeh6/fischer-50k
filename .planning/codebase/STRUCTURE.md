# Codebase Structure

**Analysis Date:** 2026-02-06

## Directory Layout

```
Fischer 50K/
├── .claude/                         # Claude settings
│   └── settings.local.json
├── .git/                            # Git repository metadata
├── .planning/                       # Planning documents
│   └── codebase/                    # Generated codebase analysis
├── Supabase_script/                 # Data ingestion layer
│   ├── ll87_load_supabase.py        # LL87 audit data loader
│   ├── ll97_load_supabase.py        # LL97 covered buildings loader
│   ├── ll84_load_supabase.py        # LL84 energy data loader (deduplicated)
│   ├── ll84_raw_load_supabase.py    # LL84 energy data loader (raw, all rows)
│   ├── LL87_2019-2024 (1).xlsx      # Source: LL87 audit data 2019-2024
│   ├── cbl_cy25.xlsx                # Source: LL97 covered buildings list
│   └── Copy of LL84_2023_Website... # Source: LL84 energy benchmarking 2023
├── CLAUDE.md                        # Project instructions & architecture spec
├── FEP_50k Implementation_Plan.md    # Implementation plan (5-step waterfall, penalties, narratives)
├── Get Building Data Fischer.json    # N8N workflow definition (API orchestration)
└── nyc-energy-data-main.zip         # Reference/archive (NYC Open Data)
```

## Directory Purposes

**Supabase_script/**
- Purpose: Data ingestion and database seeding layer
- Contains: Four Python scripts for loading LL87 audits, LL97 covered list, LL84 energy data (both raw and deduplicated versions)
- Key files:
  - `ll87_load_supabase.py` - Converts LL87 Excel to JSONB in ll87_raw table
  - `ll97_load_supabase.py` - Structures LL97 Excel into ll97_covered_buildings table
  - `ll84_load_supabase.py` - Deduplicates LL84 CSV and upserts to ll84_data table
  - `ll84_raw_load_supabase.py` - Preserves all LL84 rows in ll84_raw JSONB table
- All scripts reference Supabase PostgreSQL credentials hardcoded in script headers (DB_HOST, DB_USER, DB_PASSWORD)
- Source files (Excel/CSV) are co-located in this directory for convenience

**.planning/codebase/**
- Purpose: Generated analysis documents for downstream GSD commands
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (generated on demand)
- Used by: `/gsd:plan-phase` and `/gsd:execute-phase` to understand codebase patterns

**.claude/**
- Purpose: Claude Code settings and configuration
- Contains: settings.local.json with project-specific preferences

**.git/**
- Purpose: Git version control metadata
- Status: Repository initialized but no commits yet (initial setup phase)

**Root directory**
- CLAUDE.md - Project specification document (overrides all other documentation)
- FEP_50k Implementation_Plan.md - Detailed implementation plan including database schema, penalty formulas, narrative categories
- Get Building Data Fischer.json - N8N workflow definition for API orchestration and data aggregation
- nyc-energy-data-main.zip - Reference archive (NYC Open Data source)

## Key File Locations

**Entry Points:**

- **Manual/Single Building**: Not yet implemented. Will be a web UI in Phase A (React/FastAPI). Referenced in CLAUDE.md Section 5.1.
- **Batch Automation**: Not yet implemented. Will be a Python script or Cron job in Phase B. Referenced in CLAUDE.md Section 5.2.
- **Data Loading**: Four entry points in `Supabase_script/`:
  - `ll87_load_supabase.py` - Run: `python ll87_load_supabase.py` (REPORTING_PERIOD="2019-2024" or "2012-2018")
  - `ll97_load_supabase.py` - Run: `python ll97_load_supabase.py`
  - `ll84_load_supabase.py` - Run: `python ll84_load_supabase.py` (deduplicated, one row per BBL)
  - `ll84_raw_load_supabase.py` - Run: `python ll84_raw_load_supabase.py` (all rows, JSONB storage)

**Configuration:**

- `CLAUDE.md` - Master specification (database schema, waterfall steps, API endpoints, penalty formulas, narrative categories, environment variables)
- `FEP_50k Implementation_Plan.md` - Detailed implementation plan with complete penalty calculation tables (Carbon Coefficients, Emissions Factors for 57 use types)
- `Get Building Data Fischer.json` - N8N workflow configuration (GeoSearch, PLUTO, LL84 API calls + JavaScript aggregation code)
- Database connection strings: Hardcoded in each Python script header (Supabase_script/*.py lines 40-45)

**Core Logic:**

- `Supabase_script/ll87_load_supabase.py` (lines 87-130): `load_and_prepare()` function - Reads Excel, strips BBL dashes, converts rows to JSONB records, handles Audit Template ID versioning
- `Supabase_script/ll97_load_supabase.py` (lines 49-104): `load_and_prepare()` function - Reads Excel, maps columns to database schema, converts compliance pathway markers to boolean
- `Supabase_script/ll84_load_supabase.py` (lines 108-192): `process_row()` + `load_and_prepare()` - Type conversion (numeric, boolean, date) + deduplication by BBL (keep last)
- `Get Building Data Fischer.json` (lines 92-94): JavaScript code block - Aggregates GeoSearch/PLUTO/LL84 results, calculates emissions limit, formats output

**Testing:**

- No automated tests present. Manual verification built into each data loader script:
  - `ll87_load_supabase.py`: `verify()` function (lines 214-250) - Sample 3 buildings, confirm counts
  - `ll97_load_supabase.py`: `verify()` function (lines 194-238) - Count rows per compliance pathway
  - `ll84_load_supabase.py`: `verify()` function (lines 327-360) - Show top penalty buildings by 2030 penalty

## Naming Conventions

**Files:**

- Pattern: `ll[XX]_[operation]_supabase.py` where XX = law number (87, 97, 84)
- Examples:
  - `ll87_load_supabase.py` - LL87 data loader
  - `ll84_raw_load_supabase.py` - LL84 raw data loader
  - `ll97_load_supabase.py` - LL97 loader
- Convention: All Python loaders target Supabase PostgreSQL and use psycopg2

**Directories:**

- Pattern: `Supabase_script/` - Contains all data ingestion code and source files
- Pattern: `.planning/codebase/` - Analysis documents (uppercase: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md)
- Pattern: `.claude/` - Settings directory

**Database Tables (Supabase PostgreSQL):**

- `ll87_raw` - Raw LL87 audit data (JSONB, all rows preserved, indexed by bbl + audit_template_id)
- `ll97_covered_buildings` - LL97 covered buildings list (structured, 26,982 rows, one per BBL)
- `ll84_data` - LL84 energy data (structured, deduplicated, one row per BBL, upsert logic)
- `ll84_raw` - LL84 energy data (JSONB, all rows, raw dump)
- `Building_Metrics` - Final output table (referenced in CLAUDE.md Section 4.3, not yet created)

**Column Names (Database):**

- Pattern: `snake_case` for all database columns (bbl, audit_template_id, raw_data, reporting_period, cp0_article_320_2024, etc.)
- Pattern: Primary keys are `bbl` (TEXT) for most tables except ll87_raw which has auto-increment `id`
- Pattern: JSON field: `raw_data` (JSONB type) for ll87_raw and ll84_raw

**Variables/Functions (Python):**

- Pattern: `snake_case` for functions and variables (e.g., `clean_value()`, `load_and_prepare()`, `convert_to_float()`, `DB_HOST`, `FILE_PATH`)
- Pattern: Constants in UPPERCASE (DB_HOST, DB_PORT, FILE_PATH, REPORTING_PERIOD, BATCH_SIZE)
- Pattern: Field mappings use descriptive dict keys (e.g., col_map in ll97_load_supabase.py line 58)

**API Endpoints:**

- GeoSearch: `https://geosearch.planninglabs.nyc/v2/search?text={address}`
- PLUTO: `https://data.cityofnewyork.us/resource/64uk-42ks.json?$where=bbl={bbl}`
- LL84: `https://data.cityofnewyork.us/resource/5zyy-y8am.json?$where=nyc_building_identification='{bin}'`

## Where to Add New Code

**New Data Source (e.g., LL88, future law):**
- Location: Create `Supabase_script/ll88_load_supabase.py` following the pattern of existing loaders
- Template:
  ```python
  import pandas as pd
  import psycopg2

  DB_HOST = "aws-0-us-west-2.pooler.supabase.com"
  DB_USER = "postgres.lhtuvtfqjovfuwuxckcw"
  # ... other config

  def load_and_prepare(file_path):
      # Read Excel/CSV, validate schema, convert types, return list of records
      pass

  def create_table(conn):
      # CREATE TABLE IF NOT EXISTS with appropriate indexes
      pass

  def insert_or_upsert_records(conn, records):
      # Batch insert or upsert based on primary key
      pass

  def verify(conn):
      # Sample queries to confirm load succeeded
      pass

  if __name__ == "__main__":
      # Step 1-5: Load, Connect, Create, Insert, Verify
      main()
  ```
- Tests: Add verification queries to `verify()` function for QA
- Documentation: Update CLAUDE.md with new data source details

**New Calculation Engine (e.g., LL98 future penalties):**
- Location: Create `calculation_ll98.py` or similar in project root
- Requirements:
  - Import ll84_data and building context from Supabase
  - Apply new penalty formula with new carbon coefficients and emissions factors
  - Output: Six numeric values (Emissions, Limit, Penalty for 2 periods) or equivalent
  - Integrate into Step 4 of waterfall (referenced in CLAUDE.md Section 2.4)

**New Narrative Category or Equipment Specs:**
- Location: Not yet implemented. Will be in narrative generation layer (Step 5).
- When implemented, expected location: separate module or system prompt templates
- Requirements:
  - Accept LL87 mechanical data (raw JSON or parsed fields)
  - Accept context fields (year built, GFA, energy use, etc.)
  - Output: 1-2 paragraph narrative or structured equipment spec
  - Reference: CLAUDE.md Section 2.5 defines 6 narratives + 4 equipment spec categories

**Web UI for Single-Building Testing (Phase A):**
- Expected location: `ui/` or `frontend/` directory (not yet created)
- Tech stack: React (implied in CLAUDE.md Section 5.1)
- Backend: FastAPI (implied in CLAUDE.md Section 5.1)
- Entry point: Address/BBL input field → Call worker code for Steps 1-5 → Display results
- Integration point: Must call existing Python waterfall logic (location TBD)

**Batch Automation Script (Phase B):**
- Expected location: `batch_runner.py` or `automation/batch.py` (not yet created)
- Logic: Loop through ll97_covered_buildings table (26,982 BBLs) → call waterfall per BBL → insert to Building_Metrics
- Scheduling: Cron job or N8N workflow (reference: CLAUDE.md Section 5.2)
- Rate limiting: Process ~1,000 records/night (configurable)

## Special Directories

**Supabase_script/**
- Purpose: Data ingestion layer (separate from application logic)
- Generated: No (all manually authored Python scripts)
- Committed: Yes (source files tracked in .git)
- Source files stored here: Excel/CSV source data files (LL87, LL97, LL84 CSV)
- Run order:
  1. `ll97_load_supabase.py` (master list; prerequisite for Steps 1-5)
  2. `ll87_load_supabase.py` (both reporting periods, separate runs)
  3. `ll84_load_supabase.py` (deduplicated, one row per BBL)
  4. `ll84_raw_load_supabase.py` (optional; preserve all rows for verification)

**.planning/**
- Purpose: Analysis documents generated by GSD commands
- Generated: Yes (created by `/gsd:map-codebase`)
- Committed: Yes (analysis documents versioned in .git)
- Content: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (on demand by focus area)

**.git/**
- Purpose: Version control metadata
- Generated: Yes (by `git init`)
- Committed: N/A (git metadata)
- Status: Repository initialized, no commits yet

## Database Connection Strings

All scripts use environment-based or hardcoded Supabase connection:

```
Host: aws-0-us-west-2.pooler.supabase.com
Port: 5432
Database: postgres
User: postgres.lhtuvtfqjovfuwuxckcw
Password: [Hardcoded in script headers - should move to .env]
SSL Mode: require
```

**Recommended improvement**: Move credentials to `.env` file and load with `python-dotenv`:

```python
import os
from dotenv import load_dotenv

load_dotenv()
DB_HOST = os.getenv("DB_HOST", "aws-0-us-west-2.pooler.supabase.com")
DB_USER = os.getenv("DB_USER", "postgres.lhtuvtfqjovfuwuxckcw")
DB_PASSWORD = os.getenv("DB_PASSWORD")
```

## Data Flow Between Components

1. **Source Files** (Excel/CSV in `Supabase_script/`)
   ↓
2. **Python Data Loaders** (ll87_load_supabase.py, etc.)
   ↓
3. **Supabase PostgreSQL** (Raw tables: ll87_raw, ll97_covered_buildings, ll84_raw; Structured: ll84_data)
   ↓
4. **N8N Workflow** (Get Building Data Fischer.json) [Phase A/B entry]
   ↓
5. **Waterfall Steps 1-5** (Not yet implemented; will call stored procedures or Python microservices)
   - Step 1: Query ll97_covered_buildings (identity)
   - Step 2: Query ll84_data (energy usage)
   - Step 3: Query ll87_raw (mechanical specs)
   - Step 4: Execute LL97 penalty calculator
   - Step 5: Call AI narrative engine (LLM)
   ↓
6. **Building_Metrics Table** (Final output, one row per building)

---

*Structure analysis: 2026-02-06*
