"""
LL87 Data Loader for Supabase - 2012-2018 CSV Version
Fischer Energy Partners - 50k Building Lead Tool

This script:
1. Reads the LL87 CSV file (2012-2018)
2. Strips BBL dashes to 10-digit numeric format (if present)
3. Converts each row to a JSON object (nulls removed)
4. Uploads ALL rows to Supabase PostgreSQL as JSONB (no deduplication)

Note: This script loads the 2012-2018 dataset. The 2019-2024 data
already exists in the table. Both datasets coexist with different
reporting_period values.

BEFORE RUNNING:
1. Install dependencies:  pip install pandas psycopg2-binary
2. Place the LL87_data_through_2018.csv file in the same folder as this script

USAGE:
  python ll87_2012_2018_load_supabase.py
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
# CONFIGURATION
# =============================================================================

# Your Supabase database connection details
DB_HOST = "aws-0-us-west-2.pooler.supabase.com"
DB_PORT = "5432"
DB_NAME = "postgres"
DB_USER = "postgres.lhtuvtfqjovfuwuxckcw"
DB_PASSWORD = "U4Y$A9$x1GBRooAF"

# Path to the LL87 CSV file
FILE_PATH = "LL87_data_through_2018.csv"

# Reporting period label for this file
REPORTING_PERIOD = "2012-2018"

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
    """Load CSV, convert rows to JSON records."""

    print(f"Loading {file_path}...")
    print("(This may take 1-2 minutes for the full file)")

    # Try different encodings to handle the file
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    df = None
    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, low_memory=False, encoding=encoding)
            print(f"  Successfully loaded with {encoding} encoding")
            break
        except UnicodeDecodeError:
            continue

    if df is None:
        print("ERROR: Could not read the CSV file with any standard encoding")
        sys.exit(1)

    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")

    # The CSV has BBL column (no dashes format)
    bbl_col = 'BBL'

    if bbl_col not in df.columns:
        print(f"ERROR: Could not find column '{bbl_col}' in the file.")
        print(f"Available columns: {df.columns.tolist()[:10]}")
        sys.exit(1)

    print(f"  Keeping all {len(df)} rows (no deduplication).")

    # Ensure BBL is clean 10-digit format (strip dashes if present)
    df['bbl_clean'] = df[bbl_col].astype(str).str.replace('-', '')

    # Convert each row to a JSON-ready dict (skip nulls to save space)
    records = []
    for idx, (_, row) in enumerate(df.iterrows()):
        bbl = row['bbl_clean']

        # Try to extract audit_template_id - it may not exist in this dataset
        # If not available, use 0 as default
        audit_id = 0
        if 'Audit Template ID' in df.columns:
            audit_id = int(row['Audit Template ID']) if pd.notna(row.get('Audit Template ID')) else 0
        elif 'audit_template_id' in df.columns:
            audit_id = int(row['audit_template_id']) if pd.notna(row.get('audit_template_id')) else 0

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

        # Check total counts across both periods
        cur.execute("SELECT reporting_period, COUNT(*) FROM ll87_raw GROUP BY reporting_period ORDER BY reporting_period")
        all_periods = cur.fetchall()

        cur.execute("""
            SELECT bbl,
                   audit_template_id,
                   raw_data->>'Submittal Information_Building Information_Address' as address
            FROM ll87_raw
            WHERE reporting_period = %s
            LIMIT 3
        """, (reporting_period,))
        samples = cur.fetchall()

    print(f"\n=== VERIFICATION ===")
    print(f"Total rows for '{reporting_period}': {count}")
    print(f"Unique BBLs: {unique_bbls}")
    print(f"\nAll periods in database:")
    for period, period_count in all_periods:
        print(f"  {period}: {period_count} rows")

    print(f"\nSample records from '{reporting_period}':")
    for bbl, audit_id, addr in samples:
        print(f"  BBL {bbl} (Audit {audit_id}): {addr}")

    print(f"\n=== USEFUL QUERIES ===")
    print(f"Query across both periods (latest audit per building):")
    print(f"  SELECT DISTINCT ON (bbl) bbl, audit_template_id, reporting_period,")
    print(f"         raw_data->>'Submittal Information_Building Information_Address' as address")
    print(f"  FROM ll87_raw")
    print(f"  WHERE bbl = '{samples[0][0] if samples else '1234567890'}'")
    print(f"  ORDER BY bbl, audit_template_id DESC;")


def main():
    # Validate file exists
    if not os.path.exists(FILE_PATH):
        print(f"ERROR: File not found: {FILE_PATH}")
        print(f"Place the LL87 CSV file in: {os.getcwd()}")
        sys.exit(1)

    # Step 1: Load and prepare the data
    print("\n[1/4] Loading and preparing data...")
    records = load_and_prepare(FILE_PATH, REPORTING_PERIOD)

    # Step 2: Connect to Supabase
    print("\n[2/4] Connecting to Supabase...")
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

    # Step 3: Clear old data for this period and insert new data
    print(f"\n[3/4] Loading {len(records)} records (period: {REPORTING_PERIOD})...")
    clear_period(conn, REPORTING_PERIOD)
    insert_records(conn, records, BATCH_SIZE)

    # Step 4: Verify
    print("\n[4/4] Verifying...")
    verify(conn, REPORTING_PERIOD)

    conn.close()
    print("\nDone! Your LL87 2012-2018 data is loaded in Supabase.")
    print("Both 2012-2018 and 2019-2024 datasets now coexist in the ll87_raw table.")


if __name__ == "__main__":
    main()
