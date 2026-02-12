"""
LL84 Raw Data Loader for Supabase
Fischer Energy Partners - 50k Building Lead Tool

This script:
1. Reads the LL84 CSV file (2023 data)
2. Strips BBL formatting to standardized format
3. Converts each row to a JSON object (nulls removed)
4. Uploads ALL rows to Supabase PostgreSQL as JSONB (no deduplication)

Note: The source file may contain duplicate BBL entries. All rows are preserved 
as-is. When querying for a single record per building, use:
  SELECT DISTINCT ON (bbl) * FROM ll84_raw ORDER BY bbl, id DESC;

BEFORE RUNNING:
1. Install dependencies:  pip install pandas psycopg2-binary
2. Update the connection details below with your Supabase credentials
3. Place the LL84 CSV file in the same folder as this script
   (or update the FILE_PATH below)

USAGE:
  python ll84_raw_load_supabase.py
"""

import pandas as pd
import json
import math
import numpy as np
from datetime import datetime, date
import psycopg2
import sys
import os

# =============================================================================
# CONFIGURATION - UPDATE THESE WITH YOUR SUPABASE DETAILS
# =============================================================================

# Your Supabase database connection details
# Find these in: Supabase Dashboard > Project Settings > Database
DB_HOST = "aws-0-us-west-2.pooler.supabase.com"   # <-- Replace with your host
DB_PORT = "5432"
DB_NAME = "postgres"
DB_USER = "postgres.lhtuvtfqjovfuwuxckcw"
DB_PASSWORD = "U4Y$A9$x1GBRooAF"          # <-- Replace with your password

# Path to the LL84 CSV file
FILE_PATH = r"C:\Users\minke\OneDrive\Desktop\Fischer 50K\Supabase_script\Copy of LL84_2023_Website - Decarbonization Compass Data as of 01_2025.csv"

# Reporting period label for this file
REPORTING_PERIOD = "2023"

# Batch size for inserts (how many rows per database commit)
BATCH_SIZE = 500

# =============================================================================
# DO NOT EDIT BELOW THIS LINE
# =============================================================================


def clean_value(v):
    """Convert pandas/numpy types to JSON-safe Python types. Returns None for nulls."""
    if pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isinf(v) or np.isnan(v):
            return None
        return float(v)
    if isinstance(v, float):
        if math.isinf(v) or math.isnan(v):
            return None
        return v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, str):
        if v.strip().lower() in ('infinity', '-infinity', 'inf', '-inf', 'nan', 'not available', 'na'):
            return None
        return v.strip()
    return v


def load_and_prepare(file_path, reporting_period):
    """Load CSV, convert ALL rows to JSON records (no deduplication)."""
    
    print(f"Loading {file_path}...")
    print("(This may take a moment for the full file)")
    df = pd.read_csv(file_path, dtype_backend='numpy_nullable', low_memory=False)
    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")

    bbl_col = 'bbl'
    
    if bbl_col not in df.columns:
        print(f"ERROR: Could not find column '{bbl_col}' in the file.")
        print(f"Available columns: {list(df.columns)[:10]}")
        sys.exit(1)
    
    print(f"  Keeping all {len(df)} rows (no deduplication).")

    # Clean BBL - remove dashes, spaces, etc
    df['bbl_clean'] = df[bbl_col].astype(str).str.replace('-', '').str.replace(' ', '').str.strip()
    
    # Convert each row to a JSON-ready dict (skip nulls to save space)
    records = []
    skipped = 0
    for idx, (_, row) in enumerate(df.iterrows()):
        bbl = row['bbl_clean']
        
        # Skip if BBL is invalid
        if pd.isna(bbl) or bbl == '' or bbl.lower() in ('nan', 'none', 'not available', 'na'):
            skipped += 1
            continue
            
        raw = {}
        for col in df.columns:
            if col == 'bbl_clean':
                continue
            val = clean_value(row[col])
            if val is not None:
                raw[col] = val
        
        records.append({
            'bbl': bbl,
            'reporting_period': reporting_period,
            'raw_data': raw
        })
        
        if (idx + 1) % 1000 == 0:
            print(f"  Processed {idx + 1}/{len(df)} rows...")

    print(f"  Valid records: {len(records)}")
    if skipped > 0:
        print(f"  Skipped {skipped} rows (invalid BBL)")
    
    return records


def create_table(conn):
    """Create the ll84_raw table if it doesn't exist."""
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS ll84_raw (
        id SERIAL PRIMARY KEY,
        bbl TEXT NOT NULL,
        reporting_period TEXT NOT NULL,
        raw_data JSONB NOT NULL,
        loaded_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for fast BBL lookups
    CREATE INDEX IF NOT EXISTS idx_ll84_raw_bbl ON ll84_raw (bbl);
    
    -- Index for querying within JSON (e.g. finding buildings by address, owner)
    CREATE INDEX IF NOT EXISTS idx_ll84_raw_gin ON ll84_raw USING GIN (raw_data);
    
    -- Index for getting latest entry per BBL
    CREATE INDEX IF NOT EXISTS idx_ll84_raw_bbl_id ON ll84_raw (bbl, id DESC);
    
    COMMENT ON TABLE ll84_raw IS 'LL84 Energy benchmarking raw data. All rows from source file preserved including duplicates.';
    COMMENT ON COLUMN ll84_raw.bbl IS '10-digit BBL (Borough Block Lot) - no dashes';
    COMMENT ON COLUMN ll84_raw.reporting_period IS 'Source dataset year: 2023';
    COMMENT ON COLUMN ll84_raw.raw_data IS 'Complete LL84 record as JSON. Keys match original CSV column names.';
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("  Table ll84_raw created (or already exists).")


def clear_period(conn, reporting_period):
    """Delete all rows for a given reporting period (truncate and replace strategy)."""
    
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ll84_raw WHERE reporting_period = %s", (reporting_period,))
        deleted = cur.rowcount
    conn.commit()
    if deleted > 0:
        print(f"  Cleared {deleted} existing rows for period '{reporting_period}'.")
    else:
        print(f"  No existing rows for period '{reporting_period}'. Fresh insert.")


def insert_records(conn, records, batch_size=500):
    """Insert records in batches."""
    
    total = len(records)
    inserted = 0
    
    with conn.cursor() as cur:
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            
            # Build batch insert
            values_list = []
            params = []
            for rec in batch:
                values_list.append("(%s, %s, %s::jsonb)")
                params.extend([rec['bbl'], rec['reporting_period'], json.dumps(rec['raw_data'])])
            
            sql = f"""
                INSERT INTO ll84_raw (bbl, reporting_period, raw_data) 
                VALUES {', '.join(values_list)}
            """
            
            cur.execute(sql, params)
            inserted += len(batch)
            
            if inserted % 1000 == 0 or inserted == total:
                conn.commit()
                print(f"  Inserted {inserted}/{total} records...")
    
    conn.commit()
    print(f"  Done. {inserted} total records inserted.")


def verify(conn, reporting_period):
    """Quick verification queries."""
    
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ll84_raw WHERE reporting_period = %s", (reporting_period,))
        count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT bbl) FROM ll84_raw WHERE reporting_period = %s", (reporting_period,))
        unique_bbls = cur.fetchone()[0]
        
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
        
        cur.execute("""
            SELECT bbl, 
                   raw_data->>'address' as address,
                   raw_data->>'owner' as owner,
                   raw_data->>'property_use' as property_use,
                   raw_data->>'energy_grade' as energy_grade
            FROM ll84_raw 
            WHERE reporting_period = %s 
            LIMIT 3
        """, (reporting_period,))
        samples = cur.fetchall()
    
    print(f"\n=== VERIFICATION ===")
    print(f"Total rows for '{reporting_period}': {count:,}")
    print(f"Unique BBLs: {unique_bbls:,}")
    print(f"Duplicate BBLs: {count - unique_bbls:,}")
    
    if duplicates:
        print(f"\nTop BBLs with most duplicates:")
        for bbl, occ in duplicates:
            print(f"  BBL {bbl}: {occ} occurrences")
    
    print(f"\nSample records:")
    for bbl, addr, owner, prop_use, grade in samples:
        print(f"  BBL {bbl} | Grade {grade}")
        print(f"    {addr}")
        print(f"    Owner: {owner} | Type: {prop_use}")
    
    print(f"\n=== USEFUL QUERIES ===")
    print(f"Get latest entry per BBL:")
    print(f"  SELECT DISTINCT ON (bbl) *")
    print(f"  FROM ll84_raw")
    print(f"  WHERE reporting_period = '{reporting_period}'")
    print(f"  ORDER BY bbl, id DESC;")
    print(f"\nLook up all entries for a specific building:")
    print(f"  SELECT id, bbl, raw_data->>'address' as address,")
    print(f"         raw_data->>'penalty_2024' as penalty_2024,")
    print(f"         raw_data->>'penalty_2030' as penalty_2030")
    print(f"  FROM ll84_raw")
    print(f"  WHERE bbl = '{samples[0][0]}'")
    print(f"  ORDER BY id;")


def main():
    # Validate file exists
    if not os.path.exists(FILE_PATH):
        print(f"ERROR: File not found: {FILE_PATH}")
        print(f"Current directory: {os.getcwd()}")
        sys.exit(1)
    
    # Validate connection details were updated
    if "YOUR-PROJECT-REF" in DB_HOST or "YOUR-DATABASE-PASSWORD" in DB_PASSWORD:
        print("ERROR: Update the database connection details at the top of this script.")
        print("Find them in: Supabase Dashboard > Project Settings > Database")
        sys.exit(1)
    
    # Step 1: Load and prepare the data
    print("\n[1/5] Loading and preparing data...")
    records = load_and_prepare(FILE_PATH, REPORTING_PERIOD)
    
    # Step 2: Connect to Supabase
    print("\n[2/5] Connecting to Supabase...")
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
    
    # Step 3: Create table
    print("\n[3/5] Creating table...")
    create_table(conn)
    
    # Step 4: Clear old data for this period and insert new data
    print(f"\n[4/5] Loading {len(records)} records (period: {REPORTING_PERIOD})...")
    clear_period(conn, REPORTING_PERIOD)
    insert_records(conn, records, BATCH_SIZE)
    
    # Step 5: Verify
    print("\n[5/5] Verifying...")
    verify(conn, REPORTING_PERIOD)
    
    conn.close()
    print("\n" + "="*60)
    print("COMPLETE! Your LL84 raw data is loaded in Supabase.")
    print("="*60)
    print("\nNOTE: Duplicate BBLs have been preserved.")
    print("Use the queries above to investigate duplicates and get latest per BBL.")


if __name__ == "__main__":
    main()
