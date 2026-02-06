# Coding Conventions

**Analysis Date:** 2026-02-06

## Naming Patterns

**Files:**
- Lowercase with underscores: `ll87_load_supabase.py`, `ll84_raw_load_supabase.py`
- Pattern: `{data_source}_{operation}_supabase.py` for database loaders
- Example: `ll97_load_supabase.py`, `ll84_load_supabase.py`

**Functions:**
- snake_case for all functions
- Descriptive and purpose-driven: `load_and_prepare()`, `create_table()`, `clean_value()`, `convert_to_int()`, `convert_yes_no_to_bool()`
- Verb-first for action functions: `clean_*`, `convert_*`, `verify()`, `insert_*`, `upsert_*`
- Getter functions explicitly named: `clean_value()`, `process_row()`

**Variables:**
- snake_case for all variables: `bbl_col`, `reporting_period`, `records`, `batch_size`, `inserted`
- Descriptive names for data structures: `deduplicated`, `seen_bbls`, `values_list`, `params`
- Loop variables typically short: `idx`, `i`, but can be explicit: `row`, `rec`, `cur`
- Boolean variables explicit: `city_owned`, `skipped_count`, `duplicates_removed`

**Constants:**
- ALL_CAPS for configuration constants at module level
- Examples: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `FILE_PATH`, `REPORTING_PERIOD`, `BATCH_SIZE`, `SHEET_NAME`
- Located in dedicated CONFIGURATION section at top of each script (see `ll87_load_supabase.py` lines 35-54)

**Database & Data Fields:**
- snake_case for table and column names: `ll87_raw`, `ll84_data`, `ll97_covered_buildings`
- BBL field standardized as `bbl` (10-digit numeric without dashes)
- Audit/version tracking: `audit_template_id`, `id`, `loaded_at`
- Structured data uses simple names: `raw_data` for JSONB columns

## Code Style

**Formatting:**
- 4-space indentation (Python standard)
- Lines wrapped at 80-100 characters in SQL/comments, no hard limit enforced in code
- Multiple statements per line discouraged (see exception: `seen_bbls[record['bbl']] = record` on line 183 of `ll84_load_supabase.py`)
- Blank lines between function definitions (one blank line between functions, two between class definitions if applicable)

**String Handling:**
- Double quotes for strings in Python: `"Loading"`, `"ERROR"`, `"Done!"`
- f-strings preferred for string interpolation: `f"Loaded: {len(df)} rows"` (line 93 of `ll84_load_supabase.py`)
- Raw strings for Windows file paths: `r"C:\Users\minke\OneDrive\Desktop\..."`

**Imports:**
- Organized by category: stdlib, third-party, local
- Order observed in data loaders:
  1. Standard library (pandas, json, math, numpy, datetime, psycopg2, sys, os)
  2. psycopg2 extras only imported when needed: `from psycopg2.extras import execute_values` (line 30 of `ll84_load_supabase.py`)

**Code Organization:**
- Configuration section at top, clearly marked with comment banner
- Helper/utility functions before main processing functions
- Processing functions (`load_and_prepare`, `create_table`, etc.) in logical order
- `main()` function at end, always wrapped in `if __name__ == "__main__":` guard

## Error Handling

**Patterns:**
- Explicit validation before processing with `sys.exit(1)` for fatal errors:
  - File existence check: `if not os.path.exists(FILE_PATH):`
  - Column validation: `if bbl_col not in df.columns:`
  - Configuration validation: `if "YOUR-PROJECT-REF" in DB_HOST:`
- Try-except blocks for database operations with descriptive error messages:
  ```python
  try:
      conn = psycopg2.connect(...)
  except Exception as e:
      print(f"ERROR: Could not connect to database: {e}")
      sys.exit(1)
  ```
- Data validation with return of None for invalid entries (see `clean_value()` pattern)
- Row skipping for invalid data rather than failing: skip rows missing BBL, track skipped count
- Exception handling for type conversion failures: `except (ValueError, TypeError):` returning None

**Null/Missing Data:**
- None (Python) for missing/null values
- Pandas `pd.isna()` used to check for missing values from Excel/CSV
- Special string handling for data-specific nulls: `'Not Available'`, `'NA'`, `'infinity'`, `'nan'`

## Logging & Output

**Framework:** Console printing via `print()`

**Patterns:**
- Structured step reporting: `[1/5]`, `[2/5]` format showing progress (line 267 of `ll87_load_supabase.py`)
- Status updates with context: `f"  Loaded: {len(df)} rows, {len(df.columns)} columns"`
- Numbered progress in batch operations: `[1/5] Loading and preparing data...` then `[2/5] Connecting to Supabase...`
- Indented status messages with two spaces for sub-steps: `  Connected successfully.`
- Warning messages use `WARNING:` prefix
- Error messages use `ERROR:` prefix
- Verification section clearly marked: `=== VERIFICATION ===`
- Useful queries section: `=== USEFUL QUERIES ===` with formatted examples

## Comments

**When to Comment:**
- Module docstring at top explains script purpose and prerequisites
- Section headers (e.g., "# Configuration" line 35, "# DO NOT EDIT BELOW THIS LINE" line 57)
- Complex data transformation logic (see `convert_yes_no_to_bool()` conversion)
- Database design notes via PostgreSQL COMMENT statements (example: line 155 of `ll87_load_supabase.py`)
- Inline comments for non-obvious operations: "# Keep last occurrence per BBL" (line 179 of `ll84_load_supabase.py`)

**JSDoc/TSDoc:** Not applicable (Python project)

**Pattern:** Comments explain WHY, not WHAT the code does

## Function Design

**Size:** Functions typically 5-25 lines, single responsibility:
- `clean_value()`: 10 lines - converts pandas types
- `convert_to_int()`: 7 lines - handles int conversion with error handling
- `load_and_prepare()`: 20-25 lines - orchestrates data loading
- `insert_records()`: 25 lines - batch insert with progress reporting
- Larger functions break into logical sections with blank-line separators

**Parameters:**
- Explicit over implicit: function accepts specific parameters, not *args/**kwargs
- Configuration via constants, not function parameters (DB credentials are module-level constants)
- Simple types preferred: strings, integers, dictionaries
- Pandas DataFrames and connections passed when needed

**Return Values:**
- Single return type per function: returns records list, DataFrame, or tuple, but not mixed
- None for missing/invalid cases (cleanup functions return None on error)
- Tuples used for multiple related returns (see `cur.fetchone()` tuple unpacking)

## Module Design

**Exports:**
- No explicit `__all__` defined
- All functions available at module level but organized by purpose
- Main entry point is `main()` function, executed via `if __name__ == "__main__":`

**Script Structure (Consistent across all loaders):**
1. Module docstring (purpose, usage, prerequisites)
2. Imports
3. Configuration section
4. Utility functions (clean_value, convert_*)
5. Data processing functions (load_and_prepare, process_row)
6. Database functions (create_table, insert_records, upsert_records)
7. Verification function (verify)
8. Main orchestration (main)
9. Entry point guard

## Batch Processing Convention

**Batch Operations:**
- BATCH_SIZE constant controls chunk size (100-500 typical)
- Progress reported in multiples: `if (idx + 1) % 1000 == 0:` or `if inserted % 500 == 0 or inserted == total:`
- Commits per batch or at end for safety (see line 207 of `ll87_load_supabase.py`)
- Column lists built upfront for efficiency (lines 270-279 of `ll84_load_supabase.py`)

## Data Type Conversion Convention

**Pattern Observed:**
- Utility functions for each target type: `convert_to_int()`, `convert_to_float()`, `convert_yes_no_to_bool()`
- All conversion functions follow same pattern:
  1. Call `clean_value()` first
  2. Check if None, return None
  3. Handle specific conversions (remove commas, strip strings, convert case)
  4. Catch exceptions, return None on failure
- Reusable across all loaders (seen in both LL84 and LL87)

---

*Convention analysis: 2026-02-06*
