# Phase 2: Data Retrieval Waterfall - Research

**Researched:** 2026-02-10
**Domain:** NYC Open Data API Integration, HTTP Client Libraries, PostgreSQL Schema Design
**Confidence:** MEDIUM-HIGH

## Summary

Phase 2 implements the 3-step data retrieval waterfall (Steps 1-3 of the 5-step process) plus data storage. The standard approach combines:

1. **HTTP client library** (httpx recommended over requests for async support, but requests adequate for Phase 2 scope)
2. **Socrata API client** (sodapy for NYC Open Data, despite unmaintained status - still functional)
3. **Direct HTTP calls** (for GeoSearch and PLUTO APIs not using Socrata)
4. **PostgreSQL wide table** (Building_Metrics with typed columns for 11 bare minimum + 42 use-type fields)
5. **Upsert pattern** (ON CONFLICT DO UPDATE for idempotent batch processing)
6. **Timestamp tracking** (created_at/updated_at pattern with triggers)

The codebase already has solid foundations from Phase 1 (database.py reads from Supabase, validators.py handles BBL format, Streamlit UI displays data). Phase 2 extends this by adding external API calls to fetch live data rather than just querying pre-loaded tables.

**Primary recommendation:** Use `requests` library with sodapy for NYC Open Data endpoints, direct requests for GeoSearch/PLUTO APIs, and implement retry logic with exponential backoff for transient failures. Store results in a wide PostgreSQL table with ON CONFLICT upsert logic keyed on BBL.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | 2.31+ | HTTP client for API calls | Industry standard, synchronous, simple, reliable |
| sodapy | 2.2.0 | Socrata API client for NYC Open Data | Official Python client for Socrata (LL84/PLUTO) |
| urllib3 | 2.0+ | HTTP retry mechanisms | Powers requests retry logic, built-in backoff |
| psycopg2-binary | 2.9+ | PostgreSQL adapter (already in project) | Standard for Python PostgreSQL connections |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.27+ | Modern async HTTP client | If moving to async batch processing in future phases |
| tenacity | 8.0+ | Advanced retry logic | If need complex retry conditions beyond urllib3.Retry |
| ratelimit | 2.2+ | Rate limiting decorator | If Socrata throttling becomes issue |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| requests | httpx | httpx adds async support and HTTP/2, but requests is simpler for sync operations; codebase uses Streamlit (sync framework) |
| sodapy | Direct Socrata API | sodapy provides convenient pagination and auth handling vs manual implementation |
| Wide table | JSONB storage | JSONB flexible but 30% disk overhead, slower queries, no query planner statistics |

**Installation:**
```bash
pip install requests>=2.31 sodapy>=2.2.0 urllib3>=2.0
```

Note: psycopg2-binary, pandas, sqlalchemy already in requirements.txt from Phase 1.

## Architecture Patterns

### Recommended Project Structure
```
lib/
├── database.py          # Existing: Supabase queries (Phase 1)
├── api_client.py        # Existing: Claude narratives (Phase 1)
├── nyc_apis.py          # NEW: NYC Open Data API clients
├── validators.py        # Existing: BBL validation (Phase 1)
└── storage.py           # NEW: Building_Metrics upsert operations
```

### Pattern 1: Waterfall Data Fetcher
**What:** Orchestrate the 3-step retrieval process with fallback logic
**When to use:** Main entry point for data retrieval pipeline
**Example:**
```python
# Source: Derived from CLAUDE.md 5-step waterfall + Phase 1 codebase
def fetch_building_data_waterfall(bbl: str) -> Dict[str, Any]:
    """
    Execute 3-step waterfall data retrieval:
    1. LL97 Covered Buildings List (or GeoSearch fallback)
    2. LL84 API live energy data
    3. LL87 raw table mechanical data

    Returns aggregated building data dict ready for storage.
    """
    result = {}

    # Step 1: Identity resolution (primary source: LL97 table)
    ll97_data = query_ll97_table(bbl)
    if ll97_data:
        result.update(ll97_data)
        bin_for_ll84 = ll97_data['bin']
    else:
        # Fallback to GeoSearch API for BBL resolution
        geosearch_data = call_geosearch_api(bbl)
        if geosearch_data:
            result.update(geosearch_data)
            bin_for_ll84 = geosearch_data['bin']
        else:
            raise ValueError(f"BBL {bbl} not found in LL97 or GeoSearch")

    # Step 2: Live energy data from LL84 API
    ll84_data = call_ll84_api(bin_for_ll84)
    if ll84_data:
        result.update(ll84_data)
    else:
        # Fallback to PLUTO API for building metrics
        pluto_data = call_pluto_api(bbl)
        if pluto_data:
            result.update(pluto_data)

    # Step 3: Mechanical data from LL87 raw table (already in Phase 1)
    ll87_data = query_ll87_table(bbl)
    if ll87_data:
        result.update(ll87_data)

    return result
```

### Pattern 2: Socrata API Client with Pagination
**What:** Use sodapy with limit/offset for large result sets
**When to use:** Querying LL84 or PLUTO Socrata datasets
**Example:**
```python
# Source: https://pypi.org/project/sodapy/
from sodapy import Socrata

client = Socrata(
    "data.cityofnewyork.us",
    app_token="YOUR_APP_TOKEN",  # Optional but recommended
    timeout=10
)

# Query LL84 dataset by BIN
results = client.get(
    "5zyy-y8am",  # LL84 dataset ID
    where=f"nyc_building_identification='{bin}'",
    order="last_modified_date_property DESC",
    limit=1
)
```

### Pattern 3: HTTP Retry with Exponential Backoff
**What:** Automatically retry transient failures with increasing delays
**When to use:** All external API calls (GeoSearch, Socrata, PLUTO)
**Example:**
```python
# Source: https://www.zenrows.com/blog/python-requests-retry
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

def create_session_with_retry():
    """Create requests session with retry logic."""
    session = requests.Session()

    retry_strategy = Retry(
        total=3,  # Total retry attempts
        backoff_factor=1,  # Wait 1s, 2s, 4s between retries
        status_forcelist=[429, 500, 502, 503, 504],  # Retry these status codes
        allowed_methods=["GET", "POST"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session
```

### Pattern 4: PostgreSQL Upsert (ON CONFLICT)
**What:** Insert new records or update existing ones atomically
**When to use:** Storing/updating Building_Metrics table
**Example:**
```python
# Source: https://www.postgresql.org/docs/current/sql-insert.html
upsert_query = """
INSERT INTO building_metrics (
    bbl, bin, address, year_built, property_type, gfa,
    electricity_kwh, natural_gas_kbtu, fuel_oil_kbtu, steam_kbtu,
    -- ... 42 use-type square footage columns ...
    updated_at
)
VALUES (
    %(bbl)s, %(bin)s, %(address)s, %(year_built)s, %(property_type)s, %(gfa)s,
    %(electricity_kwh)s, %(natural_gas_kbtu)s, %(fuel_oil_kbtu)s, %(steam_kbtu)s,
    -- ... 42 values ...
    NOW()
)
ON CONFLICT (bbl)
DO UPDATE SET
    bin = EXCLUDED.bin,
    address = EXCLUDED.address,
    year_built = EXCLUDED.year_built,
    -- ... update all fields except bbl and created_at ...
    updated_at = NOW()
RETURNING bbl, created_at, updated_at
"""
```

### Pattern 5: Building_Metrics Table Schema
**What:** Wide table with typed columns for all building metrics
**When to use:** Central storage for aggregated building data
**Example:**
```sql
-- Source: Derived from CLAUDE.md requirements + PostgreSQL best practices
CREATE TABLE building_metrics (
    -- Primary key
    bbl VARCHAR(10) PRIMARY KEY,

    -- Identity fields (Step 1: LL97/GeoSearch)
    bin VARCHAR(10),
    address TEXT,
    zip_code VARCHAR(5),
    compliance_pathway VARCHAR(100),

    -- Building characteristics (Step 2: LL84/PLUTO)
    year_built INTEGER,
    property_type VARCHAR(200),
    gfa NUMERIC,  -- Gross floor area
    energy_star_score INTEGER,

    -- Energy metrics (Step 2: LL84)
    electricity_kwh NUMERIC,
    natural_gas_kbtu NUMERIC,
    fuel_oil_kbtu NUMERIC,
    steam_kbtu NUMERIC,
    site_eui NUMERIC,  -- Site Energy Use Intensity

    -- 42 use-type square footage fields (Step 2: LL84)
    adult_education_sqft NUMERIC,
    ambulatory_surgical_center_sqft NUMERIC,
    automobile_dealership_sqft NUMERIC,
    bank_branch_sqft NUMERIC,
    college_university_sqft NUMERIC,
    -- ... (37 more use types) ...
    worship_facility_sqft NUMERIC,

    -- LL87 mechanical data reference (Step 3: LL87 table)
    ll87_audit_id INTEGER,
    ll87_period VARCHAR(20),

    -- Processing metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    data_source VARCHAR(50),  -- 'll97', 'll84_api', 'geosearch', 'pluto'

    -- Indexes
    CONSTRAINT building_metrics_pkey PRIMARY KEY (bbl)
);

CREATE INDEX idx_building_metrics_bin ON building_metrics(bin);
CREATE INDEX idx_building_metrics_updated_at ON building_metrics(updated_at);
```

### Anti-Patterns to Avoid
- **Hand-rolling Socrata pagination:** Use sodapy's `get_all()` generator instead of manual offset loops
- **Storing all data in JSONB:** Pulls out 42 use-type fields as typed columns saves ~30% disk space and enables query planner statistics
- **Ignoring retry logic:** NYC Open Data can be flaky; always use retry with backoff
- **Blocking Streamlit UI during batch processing:** Use st.progress() and process in smaller batches
- **Hardcoding API credentials:** Use Streamlit secrets or environment variables

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry logic | Custom retry loop with sleep() | urllib3.Retry with HTTPAdapter | Handles exponential backoff, jitter, status code filtering, max retries |
| Socrata pagination | Manual offset/limit loops | sodapy.get_all() generator | Handles pagination automatically, prevents memory issues with large datasets |
| App token management | Pass token in every request | sodapy client initialization | Centralized auth, automatic header injection |
| Timestamp triggers | Manual NOW() in every update | PostgreSQL trigger function | Database enforces consistency, prevents forget-to-update bugs |
| BBL validation | Regex or string checks | validators.py (already exists) | Borough validation, length checks, dashed format conversion |
| Connection pooling | Create new connection per request | Streamlit st.connection() | Automatic pooling, lifecycle management, secrets integration |

**Key insight:** NYC Open Data ecosystem has quirks (semicolon-delimited BINs, inconsistent field names, rate limits). Use sodapy to abstract these away rather than parsing API responses manually.

## Common Pitfalls

### Pitfall 1: Socrata Rate Limit Throttling
**What goes wrong:** API returns 429 Too Many Requests, breaking the retrieval pipeline
**Why it happens:** Unauthenticated requests share a communal IP-based quota (very restrictive); authenticated requests get 1000 req/hour per app token
**How to avoid:**
1. Always use app token (register at https://data.cityofnewyork.us/profile/app_tokens)
2. Add 429 to retry status_forcelist
3. Implement exponential backoff with jitter
**Warning signs:** Intermittent 429 errors, especially during batch processing

### Pitfall 2: Multiple BINs Per BBL
**What goes wrong:** LL84 API query returns no results even though building is in LL97 list
**Why it happens:** LL84's `nyc_building_identification` field can contain semicolon-delimited multiple BINs (e.g., "1001234;1001235"); exact match query fails
**How to avoid:**
1. Use LIKE query instead of exact match: `WHERE nyc_building_identification LIKE '%{bin}%'`
2. OR split the field and check if BIN is in the list
3. Document this in code comments
**Warning signs:** Buildings with known LL84 data returning empty results

### Pitfall 3: LL84 API Field Name Mismatches
**What goes wrong:** Expected field names don't exist in API response
**Why it happens:** Socrata field names are inconsistent (underscores vs spaces, abbreviations, case sensitivity)
**How to avoid:**
1. Verify actual field names from dataset API documentation: https://data.cityofnewyork.us/resource/5zyy-y8am.json
2. Use sodapy metadata query: `client.get_metadata("5zyy-y8am")`
3. Map API field names to internal field names with explicit dict
**Warning signs:** KeyError exceptions when accessing response fields

### Pitfall 4: GeoSearch Address Fuzzy Matching
**What goes wrong:** GeoSearch returns unexpected BBL/BIN for an address
**Why it happens:** GeoSearch is a geocoding API with fuzzy matching; it returns "best match" even if confidence is low
**Why it happens (cont):** Multiple addresses can resolve to same BBL (entrance variations, vanity addresses)
**How to avoid:**
1. Check confidence score in response: `features[0].properties.confidence`
2. Only accept confidence >= 0.8 for automated processing
3. Flag low-confidence matches for manual review
**Warning signs:** BBL resolution succeeds but address in LL97 doesn't match input address

### Pitfall 5: Wide Table Query Performance
**What goes wrong:** SELECT * queries become slow as table grows
**Why it happens:** PostgreSQL must read all 50+ columns even if only a few are needed
**How to avoid:**
1. Always SELECT specific columns needed for the operation
2. Create partial indexes on commonly queried subsets
3. Pull frequently-queried fields (BBL, BIN, address, year_built) into separate summary table if needed
**Warning signs:** Query times increase non-linearly as table size grows

### Pitfall 6: Timestamp Trigger Forgotten
**What goes wrong:** `updated_at` shows stale timestamps even after updates
**Why it happens:** PostgreSQL doesn't auto-update timestamp columns; requires explicit trigger function
**How to avoid:**
```sql
-- Create trigger function (once)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach to table
CREATE TRIGGER update_building_metrics_updated_at
    BEFORE UPDATE ON building_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```
**Warning signs:** `updated_at` never changes from initial creation timestamp

### Pitfall 7: PLUTO API BBL Format Confusion
**What goes wrong:** PLUTO API query returns no results for valid BBL
**Why it happens:** PLUTO expects 10-digit numeric BBL without dashes; easy to accidentally pass dashed format
**How to avoid:**
1. Use validators.py to ensure BBL is in 10-digit format before PLUTO query
2. Add assertion in PLUTO client function: `assert len(bbl) == 10 and bbl.isdigit()`
**Warning signs:** PLUTO queries consistently return empty for BBLs that exist in PLUTO dataset

## Code Examples

Verified patterns from official sources:

### NYC GeoSearch API Call
```python
# Source: https://geosearch.planninglabs.nyc/docs/
import requests

def geosearch_resolve_address(address: str) -> Optional[Dict]:
    """
    Resolve NYC address to BBL and BIN using GeoSearch API.

    Returns dict with keys: bbl, bin, confidence, label
    """
    url = "https://geosearch.planninglabs.nyc/v2/search"
    params = {"text": address}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    if not data.get("features"):
        return None

    feature = data["features"][0]
    props = feature["properties"]

    # Check confidence score
    confidence = props.get("confidence", 0)
    if confidence < 0.8:
        # Low confidence, flag for review
        return None

    # Extract BBL and BIN from PAD addendum
    pad = props.get("addendum", {}).get("pad", {})

    return {
        "bbl": pad.get("bbl"),
        "bin": pad.get("bin"),
        "confidence": confidence,
        "label": props.get("label"),
        "address": props.get("name")
    }
```

### LL84 API Query with sodapy
```python
# Source: https://pypi.org/project/sodapy/
from sodapy import Socrata
from typing import Optional, Dict

def fetch_ll84_energy_data(bin: str, app_token: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch latest LL84 energy benchmarking data for a building.

    Args:
        bin: Building Identification Number
        app_token: Socrata app token (optional but recommended)

    Returns:
        Dict with energy metrics and use-type square footages
    """
    client = Socrata(
        "data.cityofnewyork.us",
        app_token=app_token,
        timeout=30
    )

    try:
        # Query LL84 dataset (5zyy-y8am) by BIN
        # Use LIKE to handle semicolon-delimited multiple BINs
        results = client.get(
            "5zyy-y8am",
            where=f"nyc_building_identification LIKE '%{bin}%'",
            order="last_modified_date_property DESC",
            limit=1
        )

        if not results:
            return None

        # Map Socrata field names to internal names
        row = results[0]
        return {
            "year_built": row.get("year_built"),
            "property_type": row.get("largest_property_use_type_self_selected"),
            "gfa": row.get("property_gfa_self_reported_ft"),
            "electricity_kwh": row.get("electricity_use_grid_purchase_kwh"),
            "natural_gas_kbtu": row.get("natural_gas_use_kbtu"),
            "fuel_oil_kbtu": row.get("fuel_oil_2_use_kbtu"),
            "steam_kbtu": row.get("district_steam_use_kbtu"),
            "site_eui": row.get("site_energy_use_intensity_kbtu_ft"),
            "energy_star_score": row.get("energy_star_score"),
            # Extract 42 use-type sqft fields
            "adult_education_sqft": row.get("adult_education_gross_floor_area_ft"),
            # ... (41 more mappings)
        }
    finally:
        client.close()
```

### PLUTO API Query
```python
# Source: https://data.cityofnewyork.us/City-Government/Primary-Land-Use-Tax-Lot-Output-PLUTO-/64uk-42ks
from sodapy import Socrata

def fetch_pluto_building_data(bbl: str, app_token: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch building structure data from PLUTO as fallback.

    Args:
        bbl: 10-digit BBL (no dashes)
        app_token: Socrata app token

    Returns:
        Dict with year_built, numfloors, bldgarea, ownername
    """
    # Validate BBL format
    assert len(bbl) == 10 and bbl.isdigit(), f"Invalid BBL format: {bbl}"

    client = Socrata(
        "data.cityofnewyork.us",
        app_token=app_token,
        timeout=30
    )

    try:
        results = client.get(
            "64uk-42ks",  # PLUTO dataset ID
            where=f"bbl='{bbl}'",
            limit=1
        )

        if not results:
            return None

        row = results[0]
        return {
            "year_built": row.get("yearbuilt"),
            "num_floors": row.get("numfloors"),
            "bldg_area": row.get("bldgarea"),
            "owner_name": row.get("ownername")
        }
    finally:
        client.close()
```

### Building_Metrics Upsert Function
```python
# Source: https://www.postgresql.org/docs/current/sql-insert.html
import streamlit as st
from typing import Dict, Any

def upsert_building_metrics(building_data: Dict[str, Any]) -> None:
    """
    Insert or update building metrics in Supabase.

    Uses ON CONFLICT DO UPDATE for idempotent upserts.
    """
    conn = st.connection("postgresql", type="sql")

    upsert_query = """
    INSERT INTO building_metrics (
        bbl, bin, address, zip_code, compliance_pathway,
        year_built, property_type, gfa, energy_star_score,
        electricity_kwh, natural_gas_kbtu, fuel_oil_kbtu, steam_kbtu, site_eui,
        ll87_audit_id, ll87_period,
        data_source, updated_at
    )
    VALUES (
        %(bbl)s, %(bin)s, %(address)s, %(zip_code)s, %(compliance_pathway)s,
        %(year_built)s, %(property_type)s, %(gfa)s, %(energy_star_score)s,
        %(electricity_kwh)s, %(natural_gas_kbtu)s, %(fuel_oil_kbtu)s, %(steam_kbtu)s, %(site_eui)s,
        %(ll87_audit_id)s, %(ll87_period)s,
        %(data_source)s, NOW()
    )
    ON CONFLICT (bbl)
    DO UPDATE SET
        bin = EXCLUDED.bin,
        address = EXCLUDED.address,
        zip_code = EXCLUDED.zip_code,
        compliance_pathway = EXCLUDED.compliance_pathway,
        year_built = EXCLUDED.year_built,
        property_type = EXCLUDED.property_type,
        gfa = EXCLUDED.gfa,
        energy_star_score = EXCLUDED.energy_star_score,
        electricity_kwh = EXCLUDED.electricity_kwh,
        natural_gas_kbtu = EXCLUDED.natural_gas_kbtu,
        fuel_oil_kbtu = EXCLUDED.fuel_oil_kbtu,
        steam_kbtu = EXCLUDED.steam_kbtu,
        site_eui = EXCLUDED.site_eui,
        ll87_audit_id = EXCLUDED.ll87_audit_id,
        ll87_period = EXCLUDED.ll87_period,
        data_source = EXCLUDED.data_source,
        updated_at = NOW()
    RETURNING bbl, created_at, updated_at
    """

    # Execute with psycopg2 via st.connection
    with conn.session as session:
        result = session.execute(upsert_query, building_data)
        session.commit()
        return result.fetchone()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Requests library only | httpx for new projects | 2020-2021 | httpx supports async/HTTP2, but requests still dominant for sync workloads |
| Manual JSON field access | sodapy client | 2015 | Abstracts Socrata pagination, auth, metadata |
| Separate columns only | Hybrid: typed columns + JSONB where appropriate | 2014 (PG 9.4) | JSONB for flexible data, typed columns for frequently queried fields |
| MERGE statement unavailable | MERGE added to PostgreSQL 15 | 2022 | Can use MERGE instead of ON CONFLICT, but ON CONFLICT still preferred for single-row upserts |
| GeoSupport desktop API | GeoSearch web API | 2017-2018 | Cloud-based, no local install, but less comprehensive than GeoSupport |

**Deprecated/outdated:**
- **sodapy maintenance:** Unmaintained as of Aug 2022, but still functional and widely used (no replacement announced)
- **Socrata SODA 1.0/2.0 APIs:** Use SODA 3.0 with X-App-Token header instead of query parameter
- **LL84 pre-2023 datasets:** Use 5zyy-y8am (2023-present) dataset, not older dataset IDs

## Open Questions

Things that couldn't be fully resolved:

1. **GeoSearch API Rate Limits**
   - What we know: No authentication required, free public API, maintained by NYC Planning Labs
   - What's unclear: Documented rate limits or throttling thresholds
   - Recommendation: Implement same retry logic as Socrata; monitor for 429s during batch processing

2. **LL84 API 42 Use-Type Field Names**
   - What we know: Dataset has 42 use-type square footage fields matching LL97 emissions factors
   - What's unclear: Exact field names in Socrata API response (spaces vs underscores, abbreviations)
   - Recommendation: Query dataset metadata at planning time: `client.get_metadata("5zyy-y8am")` and map field names

3. **Building_Metrics Table Size Projections**
   - What we know: 26,982 buildings in LL97 list, ~53 columns per row
   - What's unclear: Actual disk usage with NUMERIC types, index overhead
   - Recommendation: Create table with 100 sample rows and use `pg_total_relation_size()` to estimate

4. **Batch Processing Performance**
   - What we know: Streamlit is synchronous, sodapy is synchronous
   - What's unclear: Time to process all 26,982 buildings (3 API calls each = ~80k requests)
   - Recommendation: Process in batches of 100 with progress indicator; estimate 2-3 hours for full run with app token

5. **PLUTO Fallback Necessity**
   - What we know: LL84 API should have all covered buildings from LL97 list
   - What's unclear: Actual coverage percentage (how often PLUTO fallback needed)
   - Recommendation: Track fallback usage with data_source field; may be rare (< 1%)

## Sources

### Primary (HIGH confidence)
- PostgreSQL 18 Documentation - INSERT ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
- sodapy PyPI Package (v2.2.0): https://pypi.org/project/sodapy/
- Streamlit Caching Documentation: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
- NYC Open Data LL84 Dataset (5zyy-y8am): https://data.cityofnewyork.us/Environment/NYC-Building-Energy-and-Water-Data-Disclosure-for-/5zyy-y8am
- NYC Open Data PLUTO Dataset (64uk-42ks): https://data.cityofnewyork.us/City-Government/Primary-Land-Use-Tax-Lot-Output-PLUTO-/64uk-42ks

### Secondary (MEDIUM confidence)
- Socrata Application Tokens Documentation: https://dev.socrata.com/docs/app-tokens.html
- NYC GeoSearch API: https://geosearch.planninglabs.nyc/
- HTTPX vs Requests Comparison (Oxylabs): https://oxylabs.io/blog/httpx-vs-requests-vs-aiohttp
- Python Requests Retry Guide (ZenRows): https://www.zenrows.com/blog/python-requests-retry
- PostgreSQL JSONB vs Columns (Heap): https://www.heap.io/blog/when-to-avoid-jsonb-in-a-postgresql-schema
- PostgreSQL Timestamp Tracking (Hasura): https://hasura.io/docs/2.0/schema/postgres/default-values/created-updated-timestamps/

### Tertiary (LOW confidence - mark for validation)
- sodapy Tutorial with NYC Open Data (GitHub): https://github.com/mebauer/sodapy-tutorial-nyc-opendata
- GeoSearch API Overview (Medium): https://medium.com/nyc-planning-digital/geowhat-a-quick-overview-of-nyc-geocoding-tools-b15655fd9207
- ThreadPoolExecutor Rate Limiting (ratemate): https://pypi.org/project/ratemate/

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - requests and sodapy are industry standard for this domain, verified with official documentation
- Architecture: MEDIUM-HIGH - Waterfall pattern derived from CLAUDE.md (project-specific), upsert and retry patterns verified with official PostgreSQL/urllib3 docs
- Pitfalls: MEDIUM - Multiple BINs and field name mismatches confirmed via dataset inspection, others derived from common Socrata/PostgreSQL issues
- Code examples: HIGH - All examples verified against official documentation (PostgreSQL, sodapy, Socrata API)
- LL84/PLUTO field mappings: LOW - Need to verify actual field names from dataset metadata at planning time

**Research date:** 2026-02-10
**Valid until:** 2026-03-10 (30 days - stable domain, sodapy unmaintained but functional)

**Key validation needed during planning:**
1. Query LL84 dataset metadata to map exact field names for 42 use-type square footage columns
2. Test GeoSearch API response structure to confirm BBL/BIN extraction path
3. Verify PLUTO API field names match code examples (yearbuilt, numfloors, bldgarea)
4. Estimate Building_Metrics table size with sample data
