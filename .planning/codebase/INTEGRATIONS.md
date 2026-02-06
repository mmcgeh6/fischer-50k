# External Integrations

**Analysis Date:** 2026-02-06

## APIs & External Services

**NYC Open Data - GeoSearch API:**
- Service: Address to BBL/BIN resolution
- Endpoint: `https://geosearch.planninglabs.nyc/v2/search`
- Query: `text={Address}` (free text address search)
- Returns: GeoJSON features with nested properties:
  - BBL path: `features[0].properties.addendum.pad.bbl` (10-digit numeric)
  - BIN path: `features[0].properties.addendum.pad.bin` (Building ID)
- Used by: `Get Building Data Fischer.json` (n8n workflow - "Get BBL" node)
- Authentication: None (public API)
- Rate Limit: Not documented; assume standard NYC Open Data limits

**NYC Open Data - PLUTO API (Parcel Universe):**
- Service: Building structure and property information
- Endpoint: `https://data.cityofnewyork.us/resource/64uk-42ks.json`
- Query: `$where=bbl={BBL}` (10-digit numeric format)
- Key Fields: `ownername`, `numfloors`, `bldgarea`, `yearbuilt`, `address`
- Used by: `Get Building Data Fischer.json` (n8n workflow - "PLUTO" node)
- Fallback source for: Building owner, year built, GFA when LL84 missing
- Authentication: None (public API)
- Rate Limit: Socrata API standard (likely 50K requests/day per IP)

**NYC Open Data - LL84 API (Energy Benchmarking):**
- Service: Building energy usage data (2023 benchmarking year)
- Endpoint: `https://data.cityofnewyork.us/resource/5zyy-y8am.json`
- Query parameters:
  - `$where=nyc_building_identification='{BIN}'` (uses BIN from Step 1, not BBL)
  - `$order=last_modified_date_property DESC` (get latest)
  - `$limit=1` (single most recent record)
- Key Fields: `electricity_use_grid_purchase_kbtu`, `natural_gas_use_kbtu`, `largest_property_use_type`, `property_gfa_self_reported`, `site_energy_use_kbtu`, `total_ghg_emissions_metric_tons_co2e`
- Used by: `Get Building Data Fischer.json` (n8n workflow - "LL84" node)
- Field Quirk: `nyc_building_identification` may contain semicolon-delimited multiple BINs
- Authentication: None (public API)
- Rate Limit: Socrata API standard (likely 50K requests/day per IP)

## Data Storage

**Primary Database: Supabase PostgreSQL (Cloud-Hosted)**

**Connection Details:**
- Host: `aws-0-us-west-2.pooler.supabase.com` (AWS Region: us-west-2)
- Port: `5432` (TCP)
- Database: `postgres`
- User: `postgres.lhtuvtfqjovfuwuxckcw`
- SSL Mode: `require` (mandatory)
- Connection Type: Session Pooler (for connection efficiency)

**Tables:**

**`ll87_raw` - LL87 Energy Audit Data**
- Columns: `id` (SERIAL PK), `bbl` (TEXT, indexed), `audit_template_id` (INTEGER), `reporting_period` (TEXT), `raw_data` (JSONB), `loaded_at` (TIMESTAMPTZ)
- Index Strategy:
  - `idx_ll87_raw_bbl` on `bbl` (fast building lookup)
  - `idx_ll87_raw_gin` on `raw_data` using GIN (JSON content search)
  - `idx_ll87_raw_audit_id` on `(bbl, audit_template_id DESC)` (find latest audit)
- Data Preservation: ALL rows kept including duplicates (no deduplication)
- Query Latest: `SELECT DISTINCT ON (bbl) * FROM ll87_raw ORDER BY bbl, audit_template_id DESC`
- Source File: `LL87_2019-2024 (1).xlsx` (or 2012-2018 variant)
- Loader: `Supabase_script/ll87_load_supabase.py`

**`ll97_covered_buildings` - LL97 Covered Buildings List (Master Authority)**
- Columns: `id` (SERIAL PK), `bbl` (TEXT, indexed, unique), `preliminary_bin` (TEXT), `address` (TEXT), `zip_code` (TEXT), `cp0_article_320_2024` (BOOLEAN), `cp1_article_320_2026` (BOOLEAN), `cp2_article_320_2035` (BOOLEAN), `cp3_article_321_onetime` (BOOLEAN), `cp4_city_portfolio` (BOOLEAN), `loaded_at` (TIMESTAMPTZ)
- Row Count: 26,982 buildings (authoritative source)
- Index Strategy:
  - `idx_ll97_cbl_bbl` on `bbl` (primary lookup)
  - `idx_ll97_cbl_cp0` on `cp0_article_320_2024` WHERE `TRUE` (filtered index for compliance pathway queries)
- Data Format: Structured columns (not JSONB)
- Canonical Address: Address column is the official address for all buildings
- BBL: Primary key (10-digit numeric, no dashes)
- Source File: `cbl_cy25.xlsx` (sheet: "LL97 CBL")
- Loader: `Supabase_script/ll97_load_supabase.py`
- Load Strategy: Truncate-and-replace (clears all rows before reload)

**`ll84_raw` - LL84 Energy Benchmarking Raw Data (All Rows Preserved)**
- Columns: `id` (SERIAL PK), `bbl` (TEXT, indexed), `reporting_period` (TEXT), `raw_data` (JSONB), `loaded_at` (TIMESTAMPTZ)
- Index Strategy:
  - `idx_ll84_raw_bbl` on `bbl`
  - `idx_ll84_raw_gin` on `raw_data` using GIN
  - `idx_ll84_raw_bbl_id` on `(bbl, id DESC)` (find latest entry per BBL)
- Data Preservation: ALL rows kept including duplicates
- Reporting Period: "2023" (2023 benchmarking year)
- Query Latest: `SELECT DISTINCT ON (bbl) * FROM ll84_raw ORDER BY bbl, id DESC`
- Source File: `Copy of LL84_2023_Website - Decarbonization Compass Data as of 01_2025.csv`
- Loader: `Supabase_script/ll84_raw_load_supabase.py`
- Load Strategy: Clear period and replace

**`ll84_data` - LL84 Energy Benchmarking Deduplicated (Structured)**
- Columns: `bbl` (TEXT PK), `address`, `borough`, `bin`, `census_tract`, `city_owned`, `city_council_district`, `energy_grade`, `property_use`, `lien_name`, `neighborhood`, `owner`, `postal_code`, `compliance_2024`, `compliance_2030`, `carbon_limit_2024` (NUMERIC), `carbon_limit_2030` (NUMERIC), `district_steam_use`, `electricity_use`, `fuel_oil_1_2_use`, `fuel_oil_4_use`, `latitude`, `longitude`, `penalty_2024`, `penalty_2030`, `total_carbon_emissions`, `natural_gas_use`, `site_energy_unit_intensity`, `total_gross_floor_area`, `year_built`, `data_source`, `last_updated` (TIMESTAMPTZ)
- Row Count: One row per unique BBL (deduplicated by keeping last occurrence)
- Index Strategy:
  - `idx_ll84_borough` on `borough`
  - `idx_ll84_penalty_2024` on `penalty_2024` WHERE `penalty_2024 > 0` (filtered)
  - `idx_ll84_penalty_2030` on `penalty_2030` WHERE `penalty_2030 > 0` (filtered)
  - `idx_ll84_energy_grade` on `energy_grade`
  - `idx_ll84_property_use` on `property_use`
- Data Type: Structured columns (not JSONB)
- Upsert Strategy: INSERT ON CONFLICT (bbl) DO UPDATE (updates existing BBLs, inserts new ones)
- Source File: `Copy of LL84_2023_Website - Decarbonization Compass Data as of 01_2025.csv`
- Loader: `Supabase_script/ll84_load_supabase.py`

**File Storage:**
- Local filesystem only (Windows Server 2022)
- No cloud file storage integration detected
- Source files stored locally: `Supabase_script/` directory

**Caching:**
- No caching layer detected
- PostgreSQL connection pooling via Supabase Session Pooler (connection-level optimization)

## Authentication & Identity

**Database Authentication:**
- PostgreSQL user/password: `postgres.lhtuvtfqjovfuwuxckcw` / hardcoded in scripts
- SSL/TLS enforced: `sslmode='require'`
- No API token or OAuth detected for Supabase
- Environment variables recommended for production (currently hardcoded in scripts)

**External APIs:**
- GeoSearch, PLUTO, LL84: No authentication required (public NYC Open Data)
- Supabase API key placeholder: `sb_publishable_nMdCWcCjDDwaPOrtHoSkbA_ofATi-qz` (publishable key found in docs, not used in scripts)
- Supabase Secret Key: `sb_secret_eAUr9JR9ZFnTGowTCJmKXQ_LdqUROYu` (found in implementation plan, not currently used)

**Session Management:**
- No session/user authentication detected
- System operates as automated data pipeline (no end-user auth)

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry, error logging service)
- Script-level error handling: `try/except` blocks in Python with console output

**Logging:**
- Console logging: Print statements to stdout during script execution
- No centralized log aggregation
- Verification queries provided at end of each loader script (manual verification)

**Backup Strategy:**
- Nightly `pg_dump` from Supabase to Windows Server 2022
- Cold backup/mirror on local Windows Server (disaster recovery)
- No automated backup service (manual pg_dump process)

## CI/CD & Deployment

**Hosting:**
- Primary: Supabase Cloud PostgreSQL (AWS us-west-2)
- Local Mirror: Windows Server 2022 with `pg_dump` backups
- Workflow Engine: n8n (location TBD - self-hosted or cloud)

**CI Pipeline:**
- None detected (no GitHub Actions, Jenkins, CircleCI)
- Manual execution via Python scripts or n8n UI
- No automated testing or validation pipeline

**Deployment Method:**
- Manual: Run Python loader scripts (`python ll87_load_supabase.py`) from command line
- Workflow: Execute n8n workflow via UI or API trigger

## Environment Configuration

**Required Environment Variables (Currently Hardcoded):**
- `DB_HOST` = `aws-0-us-west-2.pooler.supabase.com`
- `DB_PORT` = `5432`
- `DB_NAME` = `postgres`
- `DB_USER` = `postgres.lhtuvtfqjovfuwuxckcw`
- `DB_PASSWORD` = (currently hardcoded in scripts)
- `FILE_PATH` = path to source Excel/CSV file (varies per script)

**Recommended Production Configuration:**
- Move secrets to environment variables (`.env` file with proper permissions or system env vars)
- Store Supabase API keys separately
- Use connection pooler configuration from Supabase dashboard

**Secrets Location:**
- Currently: Hardcoded in Python scripts (`Supabase_script/*.py`)
- Recommended: Environment variables, `.env` file, or Supabase secrets manager

## Webhooks & Callbacks

**Incoming Webhooks:**
- None detected

**Outgoing Webhooks:**
- None detected
- n8n workflow is pull-based (queries APIs on demand)

## Data Flow Summary

1. **Load Phase**: Python scripts read Excel/CSV files from local filesystem
2. **Transform Phase**: Data cleaned, type-converted, and prepared in pandas DataFrames
3. **Insert Phase**: Records batched and inserted/upserted to Supabase PostgreSQL
4. **Query Phase**: n8n workflows or direct SQL queries fetch and combine data from multiple tables
5. **Compute Phase**: LL97 penalty calculations performed locally (Python) or in n8n JavaScript nodes
6. **Backup Phase**: Nightly `pg_dump` exports to Windows Server 2022

---

*Integration audit: 2026-02-06*
