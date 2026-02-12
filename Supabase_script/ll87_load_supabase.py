"""
LL87 Data Loader for Supabase
Fischer Energy Partners - 50k Building Lead Tool

This script:
1. Reads the LL87 Excel file (2019-2024)
2. Strips BBL dashes to 10-digit numeric format
3. Converts each row to a JSON object (nulls removed)
4. Uploads ALL rows to Supabase PostgreSQL as JSONB (no deduplication)

Note: The source file contains duplicate rows (same building, same audit ID
appearing multiple times). All rows are preserved as-is. When querying for
the latest audit per building, use:
  SELECT DISTINCT ON (bbl) * FROM ll87_raw ORDER BY bbl, audit_template_id DESC;

BEFORE RUNNING:
1. Install dependencies:  pip install pandas openpyxl psycopg2-binary
2. Update the connection details below with your Supabase credentials
3. Place the LL87 Excel file in the same folder as this script
   (or update the FILE_PATH below)

USAGE:
  python ll87_load_supabase.py
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

# Path to the LL87 Excel file
FILE_PATH = "LL87_2019-2024 (1).xlsx"

# Reporting period label for this file
REPORTING_PERIOD = "2019-2024"

# Batch size for inserts (how many rows per database commit)
BATCH_SIZE = 100

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
        if v.strip().lower() in ('infinity', '-infinity', 'inf', '-inf', 'nan'):
            return None
    return v


def load_and_prepare(file_path, reporting_period):
    """Load Excel, deduplicate by BBL, convert rows to JSON records."""
    
    print(f"Loading {file_path}...")
    print("(This may take 1-2 minutes for the full file)")
    df = pd.read_excel(file_path)
    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")

    bbl_col = 'Borough/Block/Lot (BBL)'
    
    if bbl_col not in df.columns:
        print(f"ERROR: Could not find column '{bbl_col}' in the file.")
        print(f"Available columns starting with 'B': {[c for c in df.columns if c.startswith('B')][:10]}")
        sys.exit(1)
    
    print(f"  Keeping all {len(df)} rows (no deduplication).")

    # Strip dashes from BBL for 10-digit numeric format
    df['bbl_clean'] = df[bbl_col].str.replace('-', '')
    
    # Convert each row to a JSON-ready dict (skip nulls to save space)
    records = []
    for idx, (_, row) in enumerate(df.iterrows()):
        bbl = row['bbl_clean']
        audit_id = int(row['Audit Template ID']) if pd.notna(row.get('Audit Template ID')) else 0
        raw = {}
        for col in df.columns:
            if col == 'bbl_clean':
                continue
            val = clean_value(row[col])
            if val is not None:
                raw[col] = val
        records.append({
            'bbl': bbl,
            'audit_template_id': audit_id,
            'reporting_period': reporting_period,
            'raw_data': raw
        })
        
        if (idx + 1) % 1000 == 0:
            print(f"  Processed {idx + 1}/{len(df)} rows...")

    print(f"  All {len(records)} records prepared.")
    return records


def create_table(conn):
    """Create the ll87_raw table if it doesn't exist."""
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS ll87_raw (
        id SERIAL PRIMARY KEY,
        bbl TEXT NOT NULL,
        audit_template_id INTEGER,
        reporting_period TEXT NOT NULL,
        raw_data JSONB NOT NULL,
        loaded_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for fast BBL lookups
    CREATE INDEX IF NOT EXISTS idx_ll87_raw_bbl ON ll87_raw (bbl);
    
    -- Index for querying within JSON (e.g. finding buildings by property name)
    CREATE INDEX IF NOT EXISTS idx_ll87_raw_gin ON ll87_raw USING GIN (raw_data);
    
    -- Index for finding latest audit per BBL
    CREATE INDEX IF NOT EXISTS idx_ll87_raw_audit_id ON ll87_raw (bbl, audit_template_id DESC);
    
    COMMENT ON TABLE ll87_raw IS 'LL87 Energy Audit raw data. All rows from source file preserved. Use audit_template_id to find latest audit per BBL.';
    COMMENT ON COLUMN ll87_raw.bbl IS '10-digit BBL (Borough Block Lot) - no dashes';
    COMMENT ON COLUMN ll87_raw.audit_template_id IS 'Audit Template ID from source file. Higher = more recent.';
    COMMENT ON COLUMN ll87_raw.reporting_period IS 'Source dataset period: 2019-2024 or 2012-2018';
    COMMENT ON COLUMN ll87_raw.raw_data IS 'Complete audit record as JSON. Keys match original Excel column names.';
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("  Table ll87_raw created (or already exists).")


def clear_period(conn, reporting_period):
    """Delete all rows for a given reporting period (truncate and replace strategy)."""
    
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ll87_raw WHERE reporting_period = %s", (reporting_period,))
        deleted = cur.rowcount
    conn.commit()
    if deleted > 0:
        print(f"  Cleared {deleted} existing rows for period '{reporting_period}'.")
    else:
        print(f"  No existing rows for period '{reporting_period}'. Fresh insert.")


def insert_records(conn, records, batch_size=100):
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
                values_list.append("(%s, %s, %s, %s::jsonb)")
                params.extend([rec['bbl'], rec['audit_template_id'], rec['reporting_period'], json.dumps(rec['raw_data'])])
            
            sql = f"""
                INSERT INTO ll87_raw (bbl, audit_template_id, reporting_period, raw_data) 
                VALUES {', '.join(values_list)}
            """
            
            cur.execute(sql, params)
            inserted += len(batch)
            
            if inserted % 500 == 0 or inserted == total:
                conn.commit()
                print(f"  Inserted {inserted}/{total} records...")
    
    conn.commit()
    print(f"  Done. {inserted} total records inserted.")


def verify(conn, reporting_period):
    """Quick verification queries."""
    
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ll87_raw WHERE reporting_period = %s", (reporting_period,))
        count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT bbl) FROM ll87_raw WHERE reporting_period = %s", (reporting_period,))
        unique_bbls = cur.fetchone()[0]
        
        cur.execute("""
            SELECT bbl, 
                   audit_template_id,
                   raw_data->>'Property Name' as name,
                   raw_data->>'Building Street Address' as address,
                   raw_data->>'Total Floor Area' as sqft
            FROM ll87_raw 
            WHERE reporting_period = %s 
            LIMIT 3
        """, (reporting_period,))
        samples = cur.fetchall()
    
    print(f"\n=== VERIFICATION ===")
    print(f"Total rows for '{reporting_period}': {count}")
    print(f"Unique BBLs: {unique_bbls}")
    print(f"\nSample records:")
    for bbl, audit_id, name, addr, sqft in samples:
        print(f"  BBL {bbl} (Audit {audit_id}): {name} | {addr} | {sqft} sqft")
    
    print(f"\n=== USEFUL QUERIES ===")
    print(f"Look up a building (latest audit):")
    print(f"  SELECT DISTINCT ON (bbl) bbl, audit_template_id,")
    print(f"         raw_data->>'Property Name' as name,")
    print(f"         raw_data->>'Heating Plant 1: Type' as heating_type")
    print(f"  FROM ll87_raw")
    print(f"  WHERE bbl = '{samples[0][0]}'")
    print(f"  ORDER BY bbl, audit_template_id DESC;")


def main():
    # Validate file exists
    if not os.path.exists(FILE_PATH):
        print(f"ERROR: File not found: {FILE_PATH}")
        print(f"Place the LL87 Excel file in: {os.getcwd()}")
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
    print("\nDone! Your LL87 data is loaded in Supabase.")
    print("When you get the 2012-2018 file, change REPORTING_PERIOD to '2012-2018' and run again.")


if __name__ == "__main__":
    main()
