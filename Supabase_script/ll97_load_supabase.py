"""
LL97 Covered Buildings List - Loader for Supabase
Fischer Energy Partners - 50k Building Lead Tool

This script:
1. Reads the LL97 Covered Buildings Excel file (CY 2025)
2. Creates a structured table (small dataset, no JSONB needed)
3. Uploads all 26,982 rows to Supabase PostgreSQL

BEFORE RUNNING:
1. Install dependencies:  pip install pandas openpyxl psycopg2-binary
2. Update the connection details below with your Supabase credentials
3. Place the LL97 Excel file in the same folder as this script

USAGE:
  python ll97_load_supabase.py
"""

import pandas as pd
import psycopg2
import sys
import os

# =============================================================================
# CONFIGURATION - UPDATE THESE WITH YOUR SUPABASE DETAILS
# =============================================================================

# Your Supabase database connection details (Session Pooler)
DB_HOST = "aws-0-us-west-2.pooler.supabase.com"
DB_PORT = "5432"
DB_NAME = "postgres"
DB_USER = "postgres.lhtuvtfqjovfuwuxckcw"
DB_PASSWORD = "U4Y$A9$x1GBRooAF"          # <-- Replace with your password

# Path to the LL97 Excel file
FILE_PATH = "cbl_cy25.xlsx"

# Sheet name containing the building data
SHEET_NAME = "LL97 CBL"

# Batch size for inserts
BATCH_SIZE = 500

# =============================================================================
# DO NOT EDIT BELOW THIS LINE
# =============================================================================


def load_and_prepare(file_path, sheet_name):
    """Load Excel and prepare records for insert."""
    
    print(f"Loading {file_path} (sheet: {sheet_name})...")
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    print(f"  Loaded: {len(df)} rows, {len(df.columns)} columns")
    
    # Clean up column names for Postgres
    # CP3 has a newline in the header from the Excel file
    col_map = {
        'BBL': 'bbl',
        'Preliminary BIN': 'preliminary_bin',
        'Address': 'address',
        'Zip Code': 'zip_code',
        'CP0: Article 320 beginning 2024': 'cp0_article_320_2024',
        'CP1: Article 320 beginning 2026': 'cp1_article_320_2026',
        'CP2: Article 320 beginning 2035': 'cp2_article_320_2035',
    }
    
    # Handle the CP3 column with newline in name
    for col in df.columns:
        if 'CP3' in col:
            col_map[col] = 'cp3_article_321_onetime'
        if 'CP4' in col:
            col_map[col] = 'cp4_city_portfolio'
    
    df = df.rename(columns=col_map)
    
    # Convert BBL to string (already 10-digit, just ensure text type)
    df['bbl'] = df['bbl'].astype(str).str.strip()
    
    # Convert compliance pathway X markers to boolean
    cp_cols = ['cp0_article_320_2024', 'cp1_article_320_2026', 'cp2_article_320_2035',
               'cp3_article_321_onetime', 'cp4_city_portfolio']
    for col in cp_cols:
        df[col] = df[col].notna() & (df[col] == 'X')
    
    # Convert zip code to string, handle NaN and non-numeric values (some have em dashes)
    def clean_zip(x):
        if pd.isna(x):
            return None
        try:
            return str(int(x))
        except (ValueError, TypeError):
            return None
    
    df['zip_code'] = df['zip_code'].apply(clean_zip)
    
    # Convert BIN to string (can be a long comma-separated list)
    df['preliminary_bin'] = df['preliminary_bin'].apply(lambda x: str(x) if pd.notna(x) else None)
    
    # Convert address NaN to None
    df['address'] = df['address'].apply(lambda x: str(x) if pd.notna(x) else None)
    
    print(f"  Prepared {len(df)} records.")
    return df


def create_table(conn):
    """Create the ll97_covered_buildings table."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS ll97_covered_buildings (
        id SERIAL PRIMARY KEY,
        bbl TEXT NOT NULL,
        preliminary_bin TEXT,
        address TEXT,
        zip_code TEXT,
        cp0_article_320_2024 BOOLEAN DEFAULT FALSE,
        cp1_article_320_2026 BOOLEAN DEFAULT FALSE,
        cp2_article_320_2035 BOOLEAN DEFAULT FALSE,
        cp3_article_321_onetime BOOLEAN DEFAULT FALSE,
        cp4_city_portfolio BOOLEAN DEFAULT FALSE,
        loaded_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for fast BBL lookups
    CREATE INDEX IF NOT EXISTS idx_ll97_cbl_bbl ON ll97_covered_buildings (bbl);
    
    -- Index for filtering by compliance pathway
    CREATE INDEX IF NOT EXISTS idx_ll97_cbl_cp0 ON ll97_covered_buildings (cp0_article_320_2024) WHERE cp0_article_320_2024 = TRUE;
    
    COMMENT ON TABLE ll97_covered_buildings IS 'LL97 Covered Buildings List (CY 2025). Master list of buildings subject to Local Law 97 with compliance pathway assignments.';
    COMMENT ON COLUMN ll97_covered_buildings.bbl IS '10-digit BBL (Borough Block Lot)';
    COMMENT ON COLUMN ll97_covered_buildings.cp0_article_320_2024 IS 'Compliance Pathway 0: Article 320 beginning 2024';
    COMMENT ON COLUMN ll97_covered_buildings.cp1_article_320_2026 IS 'Compliance Pathway 1: Article 320 beginning 2026';
    COMMENT ON COLUMN ll97_covered_buildings.cp2_article_320_2035 IS 'Compliance Pathway 2: Article 320 beginning 2035';
    COMMENT ON COLUMN ll97_covered_buildings.cp3_article_321_onetime IS 'Compliance Pathway 3: Article 321 One-Time Compliance';
    COMMENT ON COLUMN ll97_covered_buildings.cp4_city_portfolio IS 'Compliance Pathway 4: City Portfolio Reductions';
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("  Table ll97_covered_buildings created (or already exists).")


def insert_records(conn, df, batch_size):
    """Insert records in batches."""
    
    # Check if data already loaded
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ll97_covered_buildings")
        existing = cur.fetchone()[0]
    
    if existing > 0:
        print(f"  WARNING: Table already has {existing} rows.")
        print(f"  Clearing existing data before reload...")
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE ll97_covered_buildings RESTART IDENTITY")
        conn.commit()
    
    total = len(df)
    inserted = 0
    
    cols = ['bbl', 'preliminary_bin', 'address', 'zip_code',
            'cp0_article_320_2024', 'cp1_article_320_2026', 'cp2_article_320_2035',
            'cp3_article_321_onetime', 'cp4_city_portfolio']
    
    for i in range(0, total, batch_size):
        batch = df.iloc[i:i+batch_size]
        
        with conn.cursor() as cur:
            values_list = []
            params = []
            for _, row in batch.iterrows():
                values_list.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                params.extend([row[c] for c in cols])
            
            sql = f"""
                INSERT INTO ll97_covered_buildings 
                    (bbl, preliminary_bin, address, zip_code,
                     cp0_article_320_2024, cp1_article_320_2026, cp2_article_320_2035,
                     cp3_article_321_onetime, cp4_city_portfolio)
                VALUES {', '.join(values_list)}
            """
            cur.execute(sql, params)
        
        conn.commit()
        inserted += len(batch)
        
        if inserted % 5000 == 0 or inserted == total:
            print(f"  Inserted {inserted}/{total} rows...")
    
    print(f"  Done! {inserted} rows loaded.")


def verify(conn):
    """Run verification queries."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ll97_covered_buildings")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT bbl) FROM ll97_covered_buildings")
        unique_bbls = cur.fetchone()[0]
        
        cur.execute("""
            SELECT 
                SUM(CASE WHEN cp0_article_320_2024 THEN 1 ELSE 0 END) as cp0,
                SUM(CASE WHEN cp1_article_320_2026 THEN 1 ELSE 0 END) as cp1,
                SUM(CASE WHEN cp2_article_320_2035 THEN 1 ELSE 0 END) as cp2,
                SUM(CASE WHEN cp3_article_321_onetime THEN 1 ELSE 0 END) as cp3,
                SUM(CASE WHEN cp4_city_portfolio THEN 1 ELSE 0 END) as cp4
            FROM ll97_covered_buildings
        """)
        cp0, cp1, cp2, cp3, cp4 = cur.fetchone()
        
        cur.execute("""
            SELECT bbl, address, zip_code, cp0_article_320_2024 
            FROM ll97_covered_buildings LIMIT 3
        """)
        samples = cur.fetchall()
    
    print(f"\n=== VERIFICATION ===")
    print(f"Total rows: {total}")
    print(f"Unique BBLs: {unique_bbls}")
    print(f"\nCompliance pathways:")
    print(f"  CP0 (Article 320, 2024): {cp0}")
    print(f"  CP1 (Article 320, 2026): {cp1}")
    print(f"  CP2 (Article 320, 2035): {cp2}")
    print(f"  CP3 (Article 321, One-Time): {cp3}")
    print(f"  CP4 (City Portfolio): {cp4}")
    print(f"\nSample records:")
    for bbl, addr, zip_code, cp0 in samples:
        print(f"  BBL {bbl}: {addr}, {zip_code} (CP0={cp0})")
    
    print(f"\n=== USEFUL QUERIES ===")
    print(f"Check if a building is covered:")
    print(f"  SELECT * FROM ll97_covered_buildings WHERE bbl = '1000010010';")
    print(f"\nFind all CP0 buildings in a zip code:")
    print(f"  SELECT bbl, address FROM ll97_covered_buildings")
    print(f"  WHERE cp0_article_320_2024 = TRUE AND zip_code = '10001';")


def main():
    file_path = FILE_PATH
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    
    # Step 1: Load and prepare
    print("[1/4] Loading and preparing data...")
    df = load_and_prepare(file_path, SHEET_NAME)
    
    # Step 2: Connect
    print("\n[2/4] Connecting to Supabase...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
            sslmode='require'
        )
        print("  Connected successfully.")
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        print("Check your connection details and make sure Supabase is running.")
        sys.exit(1)
    
    # Step 3: Create table
    print("\n[3/4] Creating table...")
    create_table(conn)
    
    # Step 4: Insert
    print(f"\n[4/4] Loading {len(df)} records...")
    insert_records(conn, df, BATCH_SIZE)
    
    # Verify
    verify(conn)
    
    conn.close()
    print("\nDone! LL97 Covered Buildings loaded to Supabase.")


if __name__ == "__main__":
    main()
