# Testing Patterns

**Analysis Date:** 2026-02-06

## Test Framework

**Status:** No automated test framework detected

**Framework:**
- Not detected. No pytest, unittest, or other test runner found.
- No test configuration files present (no pytest.ini, setup.cfg, tox.ini)
- No test files detected (no *_test.py, test_*.py, or *_spec.py files)

**Testing Approach:** Manual verification via console output and database queries

**Run Commands:**
```bash
# Run loader (all scripts follow same pattern):
python ll87_load_supabase.py     # Load LL87 data
python ll84_load_supabase.py     # Load deduplicated LL84 data
python ll84_raw_load_supabase.py # Load raw LL84 data (preserves duplicates)
python ll97_load_supabase.py     # Load LL97 Covered Buildings List

# No test runner command exists
```

## Test File Organization

**Location:** Not applicable - no automated tests

**Verification Pattern:** Each loader includes built-in verification function called after data load:
- `verify()` function at end of each loader script
- Runs immediately after successful insert/upsert (line 298 of `ll87_load_supabase.py`)
- Prints verification output to console

## Built-In Verification Pattern

All loaders implement consistent verification workflow:

```python
def verify(conn, reporting_period):
    """Quick verification queries."""

    with conn.cursor() as cur:
        # Step 1: Count total records loaded
        cur.execute("SELECT COUNT(*) FROM {table} WHERE reporting_period = %s", (reporting_period,))
        count = cur.fetchone()[0]

        # Step 2: Count unique BBLs
        cur.execute("SELECT COUNT(DISTINCT bbl) FROM {table} WHERE reporting_period = %s", (reporting_period,))
        unique_bbls = cur.fetchone()[0]

        # Step 3: Sample data retrieval for spot-checking
        cur.execute("""
            SELECT [relevant_columns]
            FROM {table}
            WHERE reporting_period = %s
            LIMIT 3
        """, (reporting_period,))
        samples = cur.fetchall()

    # Step 4: Print results in structured format
    print(f"=== VERIFICATION ===")
    print(f"Total rows: {count}")
    print(f"Unique BBLs: {unique_bbls}")
```

**Verification Output Format:**
- Section header: `=== VERIFICATION ===`
- Counts: total rows, unique BBLs (or variations by table)
- Sample records: 3 rows with key fields displayed
- Useful queries: Copy-paste SQL examples for manual testing

**Example from ll84_load_supabase.py (lines 327-361):**
```
=== VERIFICATION ===
Total buildings in ll84_data: 23,456
Buildings with 2024 penalties: 12,890
Buildings with 2030 penalties: 15,234

Top 3 buildings by 2030 penalty:
  BBL 1001190036 | Grade B
    123 Main Street
    Owner: John Doe
    2024 Penalty: $50,000.00 | 2030 Penalty: $75,000.00
```

## Data Validation Patterns

**Input Validation (Pre-Load):**
- File existence check: `if not os.path.exists(FILE_PATH):`
- Configuration validation: `if "YOUR-PROJECT-REF" in DB_HOST:`
- Column existence: `if bbl_col not in df.columns:` with helpful error listing available columns

**Row-Level Validation (During Load):**
```python
def process_row(row):
    """Process a single row and convert to database format"""

    # BBL is the primary key - must be valid
    bbl = clean_value(row.get('bbl'))
    if not bbl:
        return None  # Skip invalid rows
```

Pattern observed in `ll84_load_supabase.py` lines 108-151.

**Type Validation (During Conversion):**
- Try-except blocks for numeric conversions
- Handling of NaN, infinity, special string values
- Return None for unparseable values rather than raising exceptions

**Example: convert_to_int() from ll84_load_supabase.py (lines 67-78):**
```python
def convert_to_int(value):
    """Convert value to integer, handling various cases"""
    cleaned = clean_value(value)
    if cleaned is None:
        return None
    try:
        # Remove commas if present
        if isinstance(cleaned, str):
            cleaned = cleaned.replace(',', '')
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None
```

## Data Quality Checks in Verification

**Duplicate Detection:**
From ll84_raw_load_supabase.py (lines 231-240):
```python
# Find BBLs with duplicates
cur.execute("""
    SELECT bbl, COUNT(*) as occurrences
    FROM ll84_raw
    WHERE reporting_period = %s
    GROUP BY bbl
    HAVING COUNT(*) > 1
    ORDER BY COUNT(*) DESC
    LIMIT 5
""", (reporting_period,))
duplicates = cur.fetchall()
```

Print output:
```
Top BBLs with most duplicates:
  BBL 1001190036: 3 occurrences
  BBL 1002340456: 2 occurrences
```

**Deduplication Verification:**
From ll84_load_supabase.py (line 186):
```python
duplicates_removed = len(records) - len(deduplicated)
if duplicates_removed > 0:
    print(f"  Removed {duplicates_removed} duplicate BBLs")
```

**Compliance Pathway Verification:**
From ll97_load_supabase.py (lines 203-212):
```python
cur.execute("""
    SELECT
        SUM(CASE WHEN cp0_article_320_2024 THEN 1 ELSE 0 END) as cp0,
        SUM(CASE WHEN cp1_article_320_2026 THEN 1 ELSE 0 END) as cp1,
        SUM(CASE WHEN cp2_article_320_2035 THEN 1 ELSE 0 END) as cp2,
        SUM(CASE WHEN cp3_article_321_onetime THEN 1 ELSE 0 END) as cp3,
        SUM(CASE WHEN cp4_city_portfolio THEN 1 ELSE 0 END) as cp4
    FROM ll97_covered_buildings
""")
```

Output distribution by compliance pathway.

## Connection Testing

**Pattern:** Try-except wrapper around psycopg2.connect():

From all loaders (example from ll87_load_supabase.py, lines 272-285):
```python
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode="require"
    )
    print("  Connected successfully.")
except Exception as e:
    print(f"ERROR: Could not connect to database: {e}")
    print("Check your connection details and make sure Supabase is running.")
    sys.exit(1)
```

**Testing Manually:**
Can verify connection outside Python via psql CLI or database client with same credentials.

## Progress Tracking & Observability

**Batch Processing Progress:**
All loaders track and report progress during batch operations:

From ll87_load_supabase.py (line 126-127):
```python
if (idx + 1) % 1000 == 0:
    print(f"  Processed {idx + 1}/{len(df)} rows...")
```

From ll84_load_supabase.py (lines 308-310):
```python
if upserted % 1000 == 0 or upserted == total:
    conn.commit()
    print(f"  Upserted {upserted}/{total} records...")
```

**5-Step Execution Reporting:**
Every loader prints step progress:
```
[1/5] Loading and preparing data...
[2/5] Connecting to Supabase...
[3/5] Creating table...
[4/5] Upserting 23,456 records...
[5/5] Verifying...
```

This allows tracking execution and identifying where failures occur.

## Error Reporting & Debugging

**Batch Error Details:**
From ll84_load_supabase.py (lines 304-321):
```python
try:
    execute_values(cur, sql, values)
except Exception as e:
    print(f"\n✗ ERROR in batch starting at record {i}")
    print(f"  Error: {e}")
    print(f"\n  Problematic records in this batch:")
    for idx, rec in enumerate(batch[:5]):  # Show first 5 records
        print(f"    Record {i + idx}: BBL={rec['bbl']}")
        for col in columns:
            val = rec[col]
            if val is not None and col in ['bin', 'census_tract', 'postal_code', 'year_built']:
                print(f"      {col}: {val} (type: {type(val).__name__})")
    raise
```

Provides context about which batch, record positions, and problematic values before re-raising.

## Manual Testing Procedures

**Test 1: File Input Validation**
- Place Excel/CSV file in expected location
- Run loader, verify file discovery or appropriate error message

**Test 2: Database Connectivity**
- Run loader step [2/5]
- Verify connection succeeds or specific error message appears

**Test 3: Table Creation**
- Run loader step [3/5]
- Query database directly: `\dt ll87_raw` in psql to confirm table exists
- Verify indexes created

**Test 4: Data Loading**
- Run full loader
- Step [5/5] prints count statistics
- Manually spot-check sample records using provided queries

**Test 5: Deduplication (if applicable)**
```sql
-- For LL84 dedup loader:
SELECT COUNT(*) FROM ll84_data;  -- Should be unique BBLs only

-- For LL84 raw loader:
SELECT COUNT(*), COUNT(DISTINCT bbl) FROM ll84_raw;  -- May differ
```

**Test 6: Data Type Validation**
```sql
-- Verify conversions worked:
SELECT penalty_2024, penalty_2030, year_built FROM ll84_data LIMIT 5;
-- Check that numeric types rendered correctly
```

**Test 7: Compliance Pathway Verification (LL97 only)**
```sql
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN cp0_article_320_2024 THEN 1 ELSE 0 END) as cp0_count
FROM ll97_covered_buildings;
-- Verify pathway assignments match source data
```

## What's Not Tested

**Coverage Gaps:**
- No unit tests for conversion functions (clean_value, convert_to_int, etc.)
- No integration tests for entire pipeline
- No edge case testing (e.g., very large files, malformed CSV)
- No concurrent load testing
- No data recovery/rollback scenarios
- No performance benchmarks

**Test Coverage:** Estimated at 0% - only manual verification functions

## Recommended Testing Improvements

For future development:
1. Add pytest unit tests for conversion functions
2. Add integration tests with test database and fixture data
3. Add parametrized tests for different file formats
4. Measure batch performance under load
5. Test error recovery (e.g., partial load failure)

---

*Testing analysis: 2026-02-06*
