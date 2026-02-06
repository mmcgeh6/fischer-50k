# Technology Stack

**Analysis Date:** 2026-02-06

## Languages

**Primary:**
- Python 3 - Data loading scripts and LL97 penalty calculations
- SQL (PostgreSQL) - Database schema and queries
- JavaScript - Workflow orchestration logic (n8n)

**Markup/Config:**
- JSON - Workflow definitions and configuration files
- Markdown - Documentation

## Runtime

**Environment:**
- Windows Server 2022 - Production data processing and local mirror/backup host
- Cloud-hosted (Supabase PostgreSQL) - Production database

**Python:**
- Python 3.x (implied from pandas/psycopg2 compatibility) for data loaders
- No version specification file (.python-version, requirements.txt) found in repository

## Package Manager

**Python Dependencies:**
- `pandas` - DataFrame operations for loading and transforming Excel/CSV files
- `openpyxl` - Reading XLSX Excel files
- `psycopg2-binary` - PostgreSQL database connection driver
- `numpy` - Numerical operations and type conversions
- Built-in libraries: `json`, `math`, `datetime`, `sys`, `os`

**Lockfile:** Not present. Dependencies are hardcoded in comments at top of each script.

## Frameworks

**Core:**
- PostgreSQL 14+ (Supabase) - Production database for LL87, LL97, LL84 data
- n8n - Workflow automation platform for API orchestration (Get Building Data Fischer workflow)

**Data Processing:**
- pandas - ETL and data transformation
- psycopg2 - Database connection pooling (uses Supabase Session Pooler)

## Key Dependencies

**Critical:**
- `psycopg2-binary` - Required for database connectivity to Supabase PostgreSQL
  - Connection: AWS RDS instance at `aws-0-us-west-2.pooler.supabase.com:5432`
  - SSL Mode: `require` (must be enabled for security)
  - Uses session pooler for connection management

**Infrastructure:**
- `pandas` - Handles large Excel/CSV files (LL87 dataset spans 1000s of rows)
- `openpyxl` - Required for processing LL97 CY25 Excel workbook (`cbl_cy25.xlsx`)
- `numpy` - Type conversions for JSON serialization of NULL/NaN/Infinity values

## Configuration

**Environment:**
- Supabase PostgreSQL credentials embedded in Python scripts:
  - `DB_HOST`: `aws-0-us-west-2.pooler.supabase.com`
  - `DB_PORT`: `5432`
  - `DB_NAME`: `postgres`
  - `DB_USER`: `postgres.lhtuvtfqjovfuwuxckcw`
  - `DB_PASSWORD`: Hardcoded in scripts (production should use env vars)
  - `sslmode`: `require`

**Key Configuration Variables in Scripts:**
- `FILE_PATH`: Path to source Excel/CSV files (configured per loader script)
- `REPORTING_PERIOD`: Labels datasets (e.g., "2019-2024", "2012-2018", "2023")
- `BATCH_SIZE`: Tuning parameter for insert batching (100-500 rows per commit)
- `SHEET_NAME`: For `ll97_load_supabase.py`, reads sheet named "LL97 CBL"

**Database Connection String Pattern:**
```
psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    sslmode="require"
)
```

## Build/Dev Tools

**Workflow Orchestration:**
- n8n (self-hosted or cloud) - Executes multi-step API workflows
  - Node Types: Manual Trigger, HTTP Request (4.3), Code (JavaScript 2)
  - Workflow: `Get Building Data Fischer.json` coordinates GeoSearch, PLUTO, and LL84 API calls

**Data Sources (External):**
- Excel files: LL87 (`LL87_2019-2024 (1).xlsx`), LL97 (`cbl_cy25.xlsx`)
- CSV files: LL84 (`Copy of LL84_2023_Website - Decarbonization Compass Data as of 01_2025.csv`)

**Database Tools:**
- Supabase Dashboard - Project settings, database monitoring
- psycopg2 - Direct SQL execution with parameterized queries
- `pg_dump` - Nightly backups from Supabase to Windows Server 2022

## Platform Requirements

**Development:**
- Windows Server 2022 with Python 3 installed
- Excel/CSV file access (local file system)
- Network access to Supabase PostgreSQL (port 5432, SSL required)

**Production:**
- Deployment target: Supabase Cloud PostgreSQL (AWS us-west-2 region)
- Windows Server 2022 maintains nightly `pg_dump` backup mirror for disaster recovery
- n8n instance (location TBD - self-hosted or cloud)
- NYC Open Data API access (no authentication required, public APIs)

**Network Requirements:**
- Outbound HTTPS to Supabase pooler (`aws-0-us-west-2.pooler.supabase.com:5432`)
- Outbound HTTPS to NYC Open Data APIs:
  - GeoSearch: `https://geosearch.planninglabs.nyc/v2/search`
  - PLUTO: `https://data.cityofnewyork.us/resource/64uk-42ks.json`
  - LL84: `https://data.cityofnewyork.us/resource/5zyy-y8am.json`

---

*Stack analysis: 2026-02-06*
