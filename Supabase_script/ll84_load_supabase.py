"""
LL84 Data Loader for Supabase (DEDUPLICATED VERSION)
Fischer Energy Partners - 50k Building Lead Tool

This script:
1. Reads the LL84 CSV file (2023 data)
2. Cleans and converts data types appropriately
3. DEDUPLICATES by BBL (keeps last occurrence per BBL)
4. Upserts rows to Supabase PostgreSQL (updates existing, inserts new based on BBL)

This creates a clean ll84_data table with one row per BBL and structured columns.
For preserving ALL rows including duplicates, use ll84_raw_load_supabase.py instead.

BEFORE RUNNING:
1. Install dependencies:  pip install pandas psycopg2-binary
2. Update the connection details below with your Supabase credentials
3. Place the LL84 CSV file in the same folder as this script
   (or update the FILE_PATH below)

USAGE:
  python ll84_load_supabase.py
"""

import pandas as pd
import json
import math
import numpy as np
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
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

# Data source label
DATA_SOURCE = "LL84_2023"

# Batch size for inserts (how many rows per database commit)
BATCH_SIZE = 500

# =============================================================================
# DO NOT EDIT BELOW THIS LINE
# =============================================================================


def clean_value(value):
    """Clean and convert values appropriately"""
    if pd.isna(value) or value == '' or value == 'Not Available' or value == 'NA':
        return None
    return value


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


def convert_to_float(value):
    """Convert value to float, handling various cases"""
    cleaned = clean_value(value)
    if cleaned is None:
        return None
    try:
        # Remove commas if present
        if isinstance(cleaned, str):
            cleaned = cleaned.replace(',', '')
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def convert_yes_no_to_bool(value):
    """Convert Yes/No strings to boolean"""
    cleaned = clean_value(value)
    if cleaned is None:
        return None
    if isinstance(cleaned, str):
        if cleaned.upper() == 'YES':
            return True
        elif cleaned.upper() == 'NO':
            return False
    return None


def process_row(row):
    """Process a single row and convert to database format"""
    
    # BBL is the primary key - must be valid
    bbl = clean_value(row.get('bbl'))
    if not bbl:
        return None
    
    record = {
        'bbl': str(bbl),
        'address': clean_value(row.get('address')),
        'borough': clean_value(row.get('borough')),
        'bin': convert_to_int(row.get('bin')),
        'census_tract': convert_to_int(row.get('census_tract')),
        'city_owned': convert_yes_no_to_bool(row.get('city_owned')),
        'city_council_district': convert_to_int(row.get('city_council_district')),
        'energy_grade': clean_value(row.get('energy_grade')),
        'property_use': clean_value(row.get('property_use')),
        'lien_name': clean_value(row.get('lien_name')),
        'neighborhood': clean_value(row.get('neighborhood')),
        'owner': clean_value(row.get('owner')),
        'postal_code': convert_to_int(row.get('postal_code')),
        'compliance_2024': clean_value(row.get('compliance_2024')),
        'compliance_2030': clean_value(row.get('compliance_2030')),
        'carbon_limit_2024': convert_to_float(row.get('carbon_limit_2024')),
        'carbon_limit_2030': convert_to_float(row.get('carbon_limit_2030')),
        'district_steam_use': convert_to_float(row.get('district_steam_use')),
        'electricity_use': convert_to_float(row.get('electricity_use')),
        'fuel_oil_1_2_use': convert_to_float(row.get('fuel_oil_1_2_use')),
        'fuel_oil_4_use': convert_to_float(row.get('fuel_oil_4_use')),
        'latitude': convert_to_float(row.get('latitude')),
        'longitude': convert_to_float(row.get('longitude')),
        'penalty_2024': convert_to_float(row.get('penalty_2024')),
        'penalty_2030': convert_to_float(row.get('penalty_2030')),
        'total_carbon_emissions': convert_to_float(row.get('total_carbon_emissions')),
        'natural_gas_use': convert_to_float(row.get('natural_gas_use')),
        'site_energy_unit_intensity': convert_to_float(row.get('site_energy_unit_intensity')),
        'total_gross_floor_area': convert_to_float(row.get('total_gross_floor_area')),
        'year_built': convert_to_int(row.get('year_built')),
        'data_source': DATA_SOURCE,
        'last_updated': datetime.now()
    }
    
    return record


def load_and_prepare(file_path):
    """Load CSV and convert rows to records."""
    
    print(f"Loading {file_path}...")
    df = pd.read_csv(file_path)
    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")
    
    records = []
    skipped_count = 0
    
    print("Processing rows...")
    for idx, (_, row) in enumerate(df.iterrows()):
        record = process_row(row)
        if record:
            records.append(record)
        else:
            skipped_count += 1
        
        if (idx + 1) % 1000 == 0:
            print(f"  Processed {idx + 1}/{len(df)} rows...")
    
    print(f"  Processed {len(records)} valid records")
    if skipped_count > 0:
        print(f"  Skipped {skipped_count} records (missing BBL)")
    
    # Deduplicate by BBL (keep last occurrence)
    print("  Deduplicating by BBL (keeping last occurrence)...")
    seen_bbls = {}
    for record in records:
        seen_bbls[record['bbl']] = record
    
    deduplicated = list(seen_bbls.values())
    duplicates_removed = len(records) - len(deduplicated)
    
    if duplicates_removed > 0:
        print(f"  Removed {duplicates_removed} duplicate BBLs")
    print(f"  Final unique records: {len(deduplicated)}")
    
    return deduplicated


def create_table(conn):
    """Create the ll84_data table if it doesn't exist."""
    
    # Drop table if it exists (to fix column types)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS ll84_data CASCADE")
    conn.commit()
    print("  Dropped existing ll84_data table (if any).")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS ll84_data (
        bbl TEXT PRIMARY KEY,
        address TEXT,
        borough TEXT,
        bin BIGINT,
        census_tract BIGINT,
        city_owned BOOLEAN,
        city_council_district INTEGER,
        energy_grade TEXT,
        property_use TEXT,
        lien_name TEXT,
        neighborhood TEXT,
        owner TEXT,
        postal_code INTEGER,
        compliance_2024 TEXT,
        compliance_2030 TEXT,
        carbon_limit_2024 NUMERIC,
        carbon_limit_2030 NUMERIC,
        district_steam_use NUMERIC,
        electricity_use NUMERIC,
        fuel_oil_1_2_use NUMERIC,
        fuel_oil_4_use NUMERIC,
        latitude NUMERIC,
        longitude NUMERIC,
        penalty_2024 NUMERIC,
        penalty_2030 NUMERIC,
        total_carbon_emissions NUMERIC,
        natural_gas_use NUMERIC,
        site_energy_unit_intensity NUMERIC,
        total_gross_floor_area NUMERIC,
        year_built INTEGER,
        data_source TEXT,
        last_updated TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for geographic queries
    CREATE INDEX IF NOT EXISTS idx_ll84_borough ON ll84_data (borough);
    
    -- Index for penalty queries
    CREATE INDEX IF NOT EXISTS idx_ll84_penalty_2024 ON ll84_data (penalty_2024) WHERE penalty_2024 > 0;
    CREATE INDEX IF NOT EXISTS idx_ll84_penalty_2030 ON ll84_data (penalty_2030) WHERE penalty_2030 > 0;
    
    -- Index for energy grade queries
    CREATE INDEX IF NOT EXISTS idx_ll84_energy_grade ON ll84_data (energy_grade);
    
    -- Index for property type queries
    CREATE INDEX IF NOT EXISTS idx_ll84_property_use ON ll84_data (property_use);
    
    COMMENT ON TABLE ll84_data IS 'LL84 Energy benchmarking data for NYC buildings. One row per BBL.';
    COMMENT ON COLUMN ll84_data.bbl IS '10-digit BBL (Borough Block Lot) - primary key';
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("  Table ll84_data created (or already exists).")


def upsert_records(conn, records, batch_size=500):
    """Upsert records in batches (insert or update on conflict)."""
    
    total = len(records)
    upserted = 0
    
    # Build the column list (excluding last_updated which uses DEFAULT)
    columns = [
        'bbl', 'address', 'borough', 'bin', 'census_tract', 'city_owned',
        'city_council_district', 'energy_grade', 'property_use', 'lien_name',
        'neighborhood', 'owner', 'postal_code', 'compliance_2024', 'compliance_2030',
        'carbon_limit_2024', 'carbon_limit_2030', 'district_steam_use',
        'electricity_use', 'fuel_oil_1_2_use', 'fuel_oil_4_use', 'latitude',
        'longitude', 'penalty_2024', 'penalty_2030', 'total_carbon_emissions',
        'natural_gas_use', 'site_energy_unit_intensity', 'total_gross_floor_area',
        'year_built', 'data_source'
    ]
    
    # Build update clause for ON CONFLICT
    update_clause = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'bbl'])
    
    with conn.cursor() as cur:
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            
            # Prepare values for this batch
            values = []
            for rec in batch:
                row = tuple(rec[col] for col in columns)
                values.append(row)
            
            # Build the upsert SQL
            sql = f"""
                INSERT INTO ll84_data ({', '.join(columns)}) 
                VALUES %s
                ON CONFLICT (bbl) 
                DO UPDATE SET 
                    {update_clause},
                    last_updated = NOW()
            """
            
            try:
                execute_values(cur, sql, values)
                upserted += len(batch)
                
                if upserted % 1000 == 0 or upserted == total:
                    conn.commit()
                    print(f"  Upserted {upserted}/{total} records...")
            except Exception as e:
                print(f"\n✗ ERROR in batch starting at record {i}")
                print(f"  Error: {e}")
                print(f"\n  Problematic records in this batch:")
                for idx, rec in enumerate(batch[:5]):  # Show first 5 records of batch
                    print(f"    Record {i + idx}: BBL={rec['bbl']}")
                    for col in columns:
                        val = rec[col]
                        if val is not None and col in ['bin', 'census_tract', 'postal_code', 'year_built']:
                            print(f"      {col}: {val} (type: {type(val).__name__})")
                raise
    
    conn.commit()
    print(f"  Done. {upserted} total records upserted.")


def verify(conn):
    """Quick verification queries."""
    
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ll84_data")
        count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM ll84_data WHERE penalty_2024 > 0")
        penalty_2024_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM ll84_data WHERE penalty_2030 > 0")
        penalty_2030_count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT bbl, address, owner, energy_grade, 
                   penalty_2024, penalty_2030
            FROM ll84_data 
            WHERE penalty_2030 > 0
            ORDER BY penalty_2030 DESC
            LIMIT 3
        """)
        top_penalties = cur.fetchall()
    
    print(f"\n=== VERIFICATION ===")
    print(f"Total buildings in ll84_data: {count:,}")
    print(f"Buildings with 2024 penalties: {penalty_2024_count:,}")
    print(f"Buildings with 2030 penalties: {penalty_2030_count:,}")
    
    print(f"\nTop 3 buildings by 2030 penalty:")
    for bbl, addr, owner, grade, pen_24, pen_30 in top_penalties:
        print(f"  BBL {bbl} | Grade {grade}")
        print(f"    {addr}")
        print(f"    Owner: {owner}")
        print(f"    2024 Penalty: ${pen_24:,.2f} | 2030 Penalty: ${pen_30:,.2f}")


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
    records = load_and_prepare(FILE_PATH)
    
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
    
    # Step 4: Upsert data
    print(f"\n[4/5] Upserting {len(records)} records...")
    upsert_records(conn, records, BATCH_SIZE)
    
    # Step 5: Verify
    print("\n[5/5] Verifying...")
    verify(conn)
    
    conn.close()
    print("\n" + "="*60)
    print("COMPLETE! Your LL84 data is loaded in Supabase.")
    print("="*60)


if __name__ == "__main__":
    main()
