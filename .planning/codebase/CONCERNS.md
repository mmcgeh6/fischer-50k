# Codebase Concerns

**Analysis Date:** 2026-02-06

## Tech Debt

**Hardcoded Database Credentials in Production Scripts:**
- Issue: Database credentials are hardcoded directly in all Python data loading scripts
- Files:
  - `Supabase_script/ll87_load_supabase.py` (lines 41-44)
  - `Supabase_script/ll97_load_supabase.py` (lines 29-33)
  - `Supabase_script/ll84_load_supabase.py` (lines 40-44)
  - `Supabase_script/ll84_raw_load_supabase.py` (lines 40-44)
- Impact: Credentials are exposed in version control. Any compromise of the repository exposes the entire Supabase database. Scripts cannot be safely shared or run in untrusted environments.
- Fix approach: Migrate credentials to environment variables using Python `os.getenv()` or `.env` files loaded via `python-dotenv`. Document the required env vars in a `.env.example` file.

**Hardcoded File Paths (Windows-Specific):**
- Issue: Data file paths contain absolute Windows paths that won't work on other systems
- Files:
  - `Supabase_script/ll84_load_supabase.py` (line 47) - uses `r"C:\Users\minke\OneDrive\..."`
  - `Supabase_script/ll84_raw_load_supabase.py` (line 47) - same issue
- Impact: Scripts cannot run on different machines, different users, or non-Windows systems. Makes batch automation and CI/CD impossible.
- Fix approach: Use relative paths from script location (`os.path.dirname(__file__)`) or accept file paths as command-line arguments. Store configuration in a separate config file.

**Missing Connection Error Recovery:**
- Issue: Database connection failures cause immediate hard exit with no retry logic
- Files: All loaders (ll87, ll97, ll84, ll84_raw) around connection blocks
- Impact: Network hiccup or temporary Supabase outage causes entire data load to fail. No opportunity for graceful degradation or user-initiated retry.
- Fix approach: Implement exponential backoff retry logic (3-5 attempts) with configurable timeout before failing.

**No Data Validation Before Insert:**
- Issue: Data is converted to types but not validated for business logic constraints (e.g., BBL format validation, year ranges, penalty calculations)
- Files: All loaders, particularly in conversion functions like `convert_to_int()`, `convert_to_float()`, `process_row()`
- Impact: Invalid or malformed data can enter the database silently. For example, negative penalties or year_built values of 1900 without validation.
- Fix approach: Add validation schema (e.g., using Pydantic) that checks BBL format (10 digits), year bounds (1800-2026), penalties >= 0, etc.

**Incomplete Null Handling in LL84 Conversion:**
- Issue: Multiple columns accept "Not Available" and "NA" strings but comparison is case-sensitive in some places
- Files: `Supabase_script/ll84_load_supabase.py` (line 62), `ll84_raw_load_supabase.py` (line 81, 114)
- Impact: Some null-like strings might not be correctly detected as null, leading to invalid data in the database.
- Fix approach: Normalize all null-like strings to a single standard before checking.

## Security Considerations

**Exposed Production Credentials in Readable Code:**
- Risk: Database password `U4Y$A9$x1GBRooAF` and Supabase secret keys visible in multiple script files and documentation
- Files: All Supabase_script/*.py files (lines 41-44, 29-33, etc.) and `FEP_50k Implementation_Plan.md` (line 1)
- Current mitigation: None. Credentials are plaintext in code.
- Recommendations:
  1. Rotate all Supabase credentials immediately (treat as compromised)
  2. Migrate to environment variables with no plaintext in code
  3. Add `.env` and `*.py` patterns to `.gitignore` to prevent future exposure
  4. Use Supabase JWT tokens for API access instead of direct database credentials
  5. Consider using AWS Secrets Manager or similar for production

**No Input Validation on File Paths:**
- Risk: File path parameters could be exploited via path traversal attacks
- Files: `ll87_load_supabase.py` (line 48), `ll97_load_supabase.py` (line 36), `ll84_load_supabase.py` (line 47), `ll84_raw_load_supabase.py` (line 47)
- Current mitigation: Only `os.path.exists()` check before reading
- Recommendations: Validate file paths against a whitelist of allowed directories. Use `pathlib.Path` for safe path handling.

**BIN Field Can Contain Multiple Values (Semicolon-Delimited):**
- Risk: LL84 API documentation notes BIN field may contain multiple semicolon-delimited values. Current scripts don't handle this.
- Files: `ll84_load_supabase.py` (line 120 - converts to BIGINT), `ll84_raw_load_supabase.py` handles this better by storing as text
- Current mitigation: No explicit handling; BIGINT conversion will fail on comma-delimited values
- Recommendations:
  1. Store BIN as TEXT to preserve original format
  2. Document that BIN may be semicolon-delimited (e.g., "1015137; 1015138")
  3. Add parsing logic if single BIN lookup is needed

## Performance Bottlenecks

**Memory Inefficiency in Large DataFrame Operations:**
- Problem: Loading entire CSV/Excel files into memory before processing
- Files: `ll87_load_supabase.py` (line 92 - `pd.read_excel()`), `ll84_load_supabase.py` (line 158 - `pd.read_csv()`), `ll84_raw_load_supabase.py` (line 92 - `pd.read_csv()`)
- Cause: For 50,000+ buildings dataset, pandas loads everything at once. With LL87 data potentially having 500+ columns, memory usage could exceed available RAM on Windows Server.
- Improvement path: Implement chunked reading with `pd.read_csv(chunksize=)` or use streaming JSON parsing.

**Deduplication Using Dictionary Is O(n) Space:**
- Problem: LL84 deduplication logic stores entire dictionary in memory (`seen_bbls = {}`)
- Files: `ll84_load_supabase.py` (lines 181-185)
- Cause: For large datasets, duplicate tracking consumes memory proportional to dataset size
- Improvement path: Use database-level UPSERT logic instead (which it does via `ON CONFLICT`), but the dictionary is still unnecessary overhead.

**No Batch Size Tuning Guidance:**
- Problem: Fixed batch sizes (100-500) may not be optimal for Supabase connection pooling
- Files: All loaders have `BATCH_SIZE` constant (100-500)
- Cause: No empirical testing of batch size vs. throughput/latency trade-off
- Improvement path: Add command-line parameter to tune batch size and measure actual throughput.

**Verification Queries Run Full Table Scans:**
- Problem: Verification step runs COUNT(*) and aggregations without indexes on reporting_period
- Files: `ll87_load_supabase.py` (lines 224, 225, 226 - verify function)
- Cause: These are ad-hoc queries on tables that may grow large
- Improvement path: Add index on `reporting_period` column for faster verification. These queries are not critical path so low priority.

## Fragile Areas

**Column Mapping Dependency in LL97 Loader:**
- Files: `Supabase_script/ll97_load_supabase.py` (lines 58-73)
- Why fragile: Excel column names are hardcoded. If source file column names change even slightly, script fails silently or maps to wrong columns.
- Safe modification: Add validation that checks all expected columns exist before attempting rename. Store mapping in external CSV for easier updates.
- Test coverage: No validation tests for expected columns.

**Multiple Systems Handling in LL87 (Unvalidated Denormalization):**
- Files: `Supabase_script/ll87_load_supabase.py` (all JSONB stored data)
- Why fragile: LL87 audit data has hundreds of columns for multiple systems (Roof 1, Roof 2, Heating Plant 1, Heating Plant 2, etc.). Data structure is complex and not validated. AI narrative generation in Step 5 must synthesize these.
- Safe modification: Document the LL87 schema structure separately. Add JSON schema validation in Step 5 pipeline.
- Test coverage: No tests for LL87 data structure completeness.

**BBL Format Not Validated:**
- Files: All loaders (ll87, ll97, ll84, ll84_raw)
- Why fragile: BBL is described as "10-digit numeric" but no validation enforces this. Scripts accept any string.
- Safe modification: Add regex validation `^[0-9]{10}$` for all BBL values before insert.
- Test coverage: None for BBL format validation.

**LL84 Raw Loader Skips Records with Invalid BBL:**
- Files: `Supabase_script/ll84_raw_load_supabase.py` (lines 113-116)
- Why fragile: Records with missing BBL are silently skipped. No warning or logging of how many records were lost.
- Safe modification: Log all skipped records with reason (invalid BBL) to a separate file for audit trail.
- Test coverage: No logging of data quality metrics.

**Hard-Stop on Database Errors:**
- Files: `ll84_load_supabase.py` (lines 304-321 - exception handling during upsert)
- Why fragile: Single malformed record in a batch causes entire batch to fail with no partial success. Batch size (500) means up to 500 records lost.
- Safe modification: Implement per-record error handling within batches. Insert valid records, log invalid ones, continue.
- Test coverage: No test cases for malformed data handling.

## Scaling Limits

**Fixed Batch Size for Supabase Connection Pooling:**
- Current capacity: Batch size of 100-500 rows works for ~5,000-26,000 buildings
- Limit: Will not scale efficiently to 50,000+ buildings if batch size remains fixed
- Scaling path: Profile actual throughput with different batch sizes. Supabase Session Pooler has limits (~100 concurrent connections per project). Consider increasing batch size progressively (500, 1000, 2000) to find optimal throughput vs. latency.

**Memory Usage Grows Linearly with Deduplication Logic:**
- Current capacity: LL84 deduplication dictionary works for ~10,000 unique BBLs
- Limit: With 50,000 buildings, dictionary could consume >100MB depending on record size
- Scaling path: Use database-level deduplication (which is already in place via UPSERT). Remove in-memory dictionary entirely.

**No Async/Parallel Processing:**
- Current capacity: Single-threaded sequential processing
- Limit: All loaders process data sequentially, one row at a time (or one batch at a time)
- Scaling path: Use `asyncio` or `concurrent.futures.ThreadPoolExecutor` to parallelize API calls (GeoSearch, LL84 API, PLUTO API) that would be added in Steps 2-5. Current step (data loading) is I/O-bound so parallelization would help.

## Concerns About Data Quality

**Duplicate Preservation Without Audit Trail:**
- Problem: LL87 and LL84 raw tables preserve duplicates but provide no explanation of why duplicates exist
- Files: `ll87_load_supabase.py` (lines 102 - "Keeping all rows"), `ll84_raw_load_supabase.py` (lines 102)
- Impact: Downstream processes must handle deduplication logic. No single source of truth about which record is "latest".
- Recommendation: Add `source_hash` column to track duplicate detection and document deduplication strategy in database comments.

**LL84 Data Deduplication Strategy Unclear:**
- Problem: LL84 loader keeps "last occurrence" but definition of "last" depends on CSV row order, not data quality or timestamp
- Files: `ll84_load_supabase.py` (lines 179-189)
- Impact: If source CSV is resorted, deduplication result changes. No reproducibility.
- Recommendation: Use timestamp-based deduplication if available in data, or add explicit `loaded_at` column and use that for ordering.

**No Data Lineage or Audit Logging:**
- Problem: Scripts load data but provide no record of what was loaded, when, by whom, or in what version
- Files: All loaders
- Impact: Cannot trace data provenance. If penalties are calculated incorrectly, cannot determine if data was the issue.
- Recommendation: Add audit logging table tracking: data_source, record_count, loaded_at, loaded_by, script_version, data_hash.

## Missing Critical Features

**No Dry-Run Mode:**
- Problem: All loaders execute immediately when run. No option to preview what will be loaded.
- Files: All four loaders (ll87, ll97, ll84, ll84_raw)
- Blocks: Cannot safely test on production database without risking data corruption.
- Recommendation: Add `--dry-run` flag that parses and validates data without touching database.

**No Incremental Loading:**
- Problem: All loaders truncate-and-replace entire tables. No ability to load only new/changed records.
- Files: `ll87_load_supabase.py` (line 172), `ll84_raw_load_supabase.py` (line 175), `ll97_load_supabase.py` (lines 155-157)
- Blocks: Nightly backups force full reload even if only 10 new buildings were added.
- Recommendation: Implement incremental loading with change detection (e.g., source file hash, timestamp comparison).

**No Data Validation Report:**
- Problem: Loaders only print summary counts. No detailed report of data quality issues.
- Files: All verify functions (ll87, ll97, ll84, ll84_raw)
- Blocks: Cannot identify which BBLs have missing critical fields (e.g., BBL with no address).
- Recommendation: Generate detailed CSV report of data quality issues per BBL.

**No Rollback Capability:**
- Problem: Once data is loaded, no way to revert to previous version if corruption detected.
- Files: Database operations in all loaders
- Blocks: If bad data is discovered post-load, must manually fix database or restore from backup.
- Recommendation: Implement table versioning or change log tracking. Add rollback command.

## Test Coverage Gaps

**No Unit Tests for Type Conversion Functions:**
- What's not tested: Conversion functions (`clean_value`, `convert_to_int`, `convert_to_float`, `convert_yes_no_to_bool`) have no test cases
- Files: `Supabase_script/ll84_load_supabase.py` (lines 60-105), `ll84_raw_load_supabase.py` (lines 60-84), `ll87_load_supabase.py` (lines 61-84)
- Risk: Null handling, numeric conversion edge cases, and string normalization bugs go undetected. A malformed value that breaks type conversion only fails during full data load.
- Priority: High - These are core data quality functions

**No Integration Tests for Database Inserts:**
- What's not tested: Actual INSERT/UPSERT operations against test database
- Files: All loaders' `insert_records()`, `create_table()`, and `upsert_records()` functions
- Risk: Schema changes, constraint violations, or index conflicts only detected during production load.
- Priority: High - Database operations are critical path

**No Tests for File Parsing Edge Cases:**
- What's not tested: Excel/CSV parsing with missing columns, malformed data, encoding issues
- Files: All `load_and_prepare()` and `process_row()` functions
- Risk: If source files have unexpected format changes, loaders fail or produce garbage.
- Priority: Medium - Source files are stable but could change

**No Tests for Deduplication Logic:**
- What's not tested: Deduplication by BBL preserves correct records and order
- Files: `ll84_load_supabase.py` (lines 181-189 - dictionary-based dedup)
- Risk: Deduplication could drop data or select wrong record if logic is broken.
- Priority: Medium

**No Tests for Connection Error Handling:**
- What's not tested: Behavior when database connection drops mid-load, timeout, authentication failure
- Files: All try/except blocks around `psycopg2.connect()`
- Risk: Error messages are confusing, no retry logic exists.
- Priority: Low - Connection errors are infrequent but difficult to debug

---

*Concerns audit: 2026-02-06*
