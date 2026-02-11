"""
Storage module for Building_Metrics table.

Creates and manages the Building_Metrics table in Supabase PostgreSQL,
which stores aggregated building data from the 5-step waterfall process.

This module uses psycopg2 directly (not Streamlit's st.connection) to work
in both Streamlit and batch processing contexts.

Tables managed:
- building_metrics: Central store for all aggregated building data
"""

import os
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Try to import Streamlit for secrets, but don't fail if not available
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Try to import dotenv for .env file support
try:
    from dotenv import load_dotenv
    load_dotenv()
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


# List of all use-type square footage columns (60 total)
# 42 Primary LL84 use types + 18 additional (emissions-factor-only + sub-types)
USE_TYPE_SQFT_COLUMNS = [
    "adult_education_sqft",
    "ambulatory_surgical_center_sqft",
    "automobile_dealership_sqft",
    "bank_branch_sqft",
    "barracks_sqft",  # LL84 sub-type
    "bowling_alley_sqft",  # Emissions-factor-only
    "college_university_sqft",
    "convention_center_sqft",  # LL84 sub-type
    "convenience_store_with_gas_station_sqft",
    "convenience_store_without_gas_station_sqft",  # Emissions-factor-only
    "courthouse_sqft",
    "data_center_sqft",
    "distribution_center_sqft",
    "enclosed_mall_sqft",
    "financial_office_sqft",
    "fire_station_sqft",
    "fitness_center_health_club_gym_sqft",
    "food_sales_sqft",
    "food_service_sqft",
    "hospital_general_medical_surgical_sqft",
    "hotel_sqft",
    "hotel_gym_sqft",  # LL84 sub-type
    "k_12_school_sqft",
    "laboratory_sqft",
    "library_sqft",  # Emissions-factor-only
    "lifestyle_center_sqft",  # Emissions-factor-only
    "mailing_center_post_office_sqft",
    "medical_office_sqft",
    "mixed_use_property_sqft",
    "movie_theater_sqft",
    "multifamily_housing_sqft",
    "museum_sqft",
    "non_refrigerated_warehouse_sqft",
    "office_sqft",
    "other_sqft",
    "other_education_sqft",  # Emissions-factor-only
    "other_entertainment_public_assembly_sqft",  # Emissions-factor-only
    "other_lodging_residential_sqft",  # Emissions-factor-only
    "other_mall_sqft",  # Emissions-factor-only
    "other_public_services_sqft",  # Emissions-factor-only
    "other_recreation_sqft",  # Emissions-factor-only
    "other_services_sqft",  # Emissions-factor-only
    "other_technology_science_sqft",  # Emissions-factor-only
    "other_utility_sqft",  # Emissions-factor-only
    "outpatient_rehabilitation_physical_therapy_sqft",
    "parking_sqft",
    "performing_arts_sqft",
    "personal_services_sqft",  # Emissions-factor-only
    "police_station_sqft",
    "pre_school_daycare_sqft",
    "prison_incarceration_sqft",
    "refrigerated_warehouse_sqft",
    "residence_hall_dormitory_sqft",
    "residential_care_facility_sqft",
    "restaurant_sqft",
    "retail_store_sqft",
    "self_storage_facility_sqft",
    "senior_care_community_sqft",
    "social_meeting_hall_sqft",
    "strip_mall_sqft",
    "supermarket_grocery_store_sqft",
    "swimming_pool_sqft",
    "urgent_care_clinic_other_outpatient_sqft",
    "vocational_school_sqft",  # Emissions-factor-only
    "wastewater_treatment_plant_sqft",
    "wholesale_club_supercenter_sqft",
    "worship_facility_sqft",
]


def _get_db_credentials() -> Dict[str, str]:
    """
    Get database credentials from Streamlit secrets, environment variables, or .env file.

    Priority order:
    1. Streamlit secrets (if available)
    2. Environment variables
    3. .env file via python-dotenv (if available)

    Returns:
        Dictionary with host, port, database, user, password, sslmode
    """
    creds = {}

    # Try Streamlit secrets first
    if HAS_STREAMLIT:
        try:
            creds = {
                "host": st.secrets["connections"]["postgresql"]["host"],
                "port": st.secrets["connections"]["postgresql"]["port"],
                "database": st.secrets["connections"]["postgresql"]["database"],
                "user": st.secrets["connections"]["postgresql"]["username"],
                "password": st.secrets["connections"]["postgresql"]["password"],
                "sslmode": "require"
            }
            return creds
        except (KeyError, AttributeError):
            pass  # Fall through to environment variables

    # Try environment variables
    creds = {
        "host": os.environ.get("DB_HOST", "aws-0-us-west-2.pooler.supabase.com"),
        "port": os.environ.get("DB_PORT", "5432"),
        "database": os.environ.get("DB_NAME", "postgres"),
        "user": os.environ.get("DB_USER", "postgres.lhtuvtfqjovfuwuxckcw"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "sslmode": os.environ.get("DB_SSLMODE", "require")
    }

    # If password is still empty and we have dotenv, try loading again
    if not creds["password"] and HAS_DOTENV:
        load_dotenv()
        creds["password"] = os.environ.get("DB_PASSWORD", "")

    if not creds["password"]:
        raise ValueError(
            "Database password not found. Set DB_PASSWORD environment variable "
            "or configure Streamlit secrets."
        )

    return creds


def get_connection():
    """
    Create a new PostgreSQL connection using psycopg2.

    Returns:
        psycopg2 connection object
    """
    creds = _get_db_credentials()
    conn = psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        database=creds["database"],
        user=creds["user"],
        password=creds["password"],
        sslmode=creds["sslmode"]
    )
    return conn


def create_building_metrics_table():
    """
    Create the building_metrics table with all required fields and indexes.

    Also creates the updated_at trigger function and attaches it to the table.

    This function is idempotent - safe to run multiple times.
    """
    conn = get_connection()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    try:
        # Create the trigger function for updated_at (idempotent)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)

        # Build use-type columns SQL
        use_type_columns_sql = ",\n    ".join([f"{col} NUMERIC" for col in USE_TYPE_SQFT_COLUMNS])

        # Create the building_metrics table
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS building_metrics (
                -- Identity fields (from LL97/GeoSearch - Step 1)
                bbl VARCHAR(10) PRIMARY KEY,
                bin TEXT,
                address TEXT,
                zip_code VARCHAR(5),
                compliance_pathway VARCHAR(200),

                -- Building characteristics (from LL84/PLUTO - Step 2)
                year_built INTEGER,
                property_type VARCHAR(200),
                gfa NUMERIC,
                energy_star_score INTEGER,

                -- Energy metrics (from LL84 - Step 2)
                electricity_kwh NUMERIC,
                natural_gas_kbtu NUMERIC,
                fuel_oil_kbtu NUMERIC,
                steam_kbtu NUMERIC,
                site_eui NUMERIC,

                -- Use-type square footage fields (67 columns)
                {use_type_columns_sql},

                -- LL87 reference fields (Step 3)
                ll87_audit_id INTEGER,
                ll87_period VARCHAR(20),

                -- LL97 penalty calculations (Phase 3 - Step 4)
                ghg_emissions_2024_2029 NUMERIC,
                emissions_limit_2024_2029 NUMERIC,
                penalty_2024_2029 NUMERIC,
                ghg_emissions_2030_2034 NUMERIC,
                emissions_limit_2030_2034 NUMERIC,
                penalty_2030_2034 NUMERIC,

                -- AI-generated narratives (Phase 3 - Step 5)
                envelope_narrative TEXT,
                heating_narrative TEXT,
                cooling_narrative TEXT,
                air_distribution_narrative TEXT,
                ventilation_narrative TEXT,
                dhw_narrative TEXT,

                -- Data source tracking
                data_source VARCHAR(100),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """
        cursor.execute(create_table_sql)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_building_metrics_bin
            ON building_metrics(bin);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_building_metrics_updated
            ON building_metrics(updated_at);
        """)

        # Drop and recreate trigger (for idempotency)
        cursor.execute("""
            DROP TRIGGER IF EXISTS update_building_metrics_updated_at
            ON building_metrics;
        """)

        cursor.execute("""
            CREATE TRIGGER update_building_metrics_updated_at
            BEFORE UPDATE ON building_metrics
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)

        print("Building_Metrics table created successfully")

    finally:
        cursor.close()
        conn.close()


def upsert_building_metrics(building_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert or update a building record in building_metrics table.

    Only updates columns that are present in the input dict.
    BBL is required and used as the primary key for conflict resolution.

    Args:
        building_data: Dictionary with building data. Must contain 'bbl' key.
                      Other keys should match column names in building_metrics table.

    Returns:
        Dictionary with bbl, created_at, updated_at of the upserted row

    Raises:
        ValueError: If 'bbl' key is missing from building_data
    """
    if 'bbl' not in building_data:
        raise ValueError("building_data must contain 'bbl' key")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Filter out None values and separate BBL
        data = {k: v for k, v in building_data.items() if v is not None}
        bbl = data['bbl']

        # Build column lists for INSERT
        columns = list(data.keys())
        placeholders = [f"%({col})s" for col in columns]

        # Build UPDATE clause (exclude bbl, created_at, updated_at)
        update_columns = [col for col in columns
                         if col not in ('bbl', 'created_at', 'updated_at')]
        update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])

        # Build the upsert query
        query = f"""
            INSERT INTO building_metrics ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT (bbl) DO UPDATE SET
                {update_clause}
            RETURNING bbl, created_at, updated_at;
        """

        cursor.execute(query, data)
        result = cursor.fetchone()
        conn.commit()

        return dict(result)

    finally:
        cursor.close()
        conn.close()


def get_building_metrics(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a building record from building_metrics table.

    Args:
        bbl: 10-digit BBL string

    Returns:
        Dictionary with building data, or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            "SELECT * FROM building_metrics WHERE bbl = %s",
            (bbl,)
        )
        result = cursor.fetchone()

        if result:
            return dict(result)
        return None

    finally:
        cursor.close()
        conn.close()


def migrate_add_calculation_columns():
    """
    Add Phase 3 calculation and narrative columns to building_metrics table.

    Adds 12 new columns:
    - 6 penalty calculation columns (NUMERIC): ghg_emissions_2024_2029,
      emissions_limit_2024_2029, penalty_2024_2029, ghg_emissions_2030_2034,
      emissions_limit_2030_2034, penalty_2030_2034
    - 6 narrative columns (TEXT): envelope_narrative, heating_narrative,
      cooling_narrative, air_distribution_narrative, ventilation_narrative,
      dhw_narrative

    This function is idempotent - safe to run multiple times.
    """
    conn = get_connection()
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    try:
        # Define columns to add
        penalty_columns = [
            "ghg_emissions_2024_2029",
            "emissions_limit_2024_2029",
            "penalty_2024_2029",
            "ghg_emissions_2030_2034",
            "emissions_limit_2030_2034",
            "penalty_2030_2034"
        ]

        narrative_columns = [
            "envelope_narrative",
            "heating_narrative",
            "cooling_narrative",
            "air_distribution_narrative",
            "ventilation_narrative",
            "dhw_narrative"
        ]

        # Add penalty calculation columns (NUMERIC)
        for col in penalty_columns:
            cursor.execute(f"""
                ALTER TABLE building_metrics
                ADD COLUMN IF NOT EXISTS {col} NUMERIC;
            """)

        # Add narrative columns (TEXT)
        for col in narrative_columns:
            cursor.execute(f"""
                ALTER TABLE building_metrics
                ADD COLUMN IF NOT EXISTS {col} TEXT;
            """)

        # Widen bin column for multi-BIN campus buildings (was VARCHAR(10), needs VARCHAR(50))
        cursor.execute("""
            ALTER TABLE building_metrics
            ALTER COLUMN bin TYPE TEXT;
        """)

        print("Migration complete: Added 12 calculation and narrative columns")

    finally:
        cursor.close()
        conn.close()


# Export list for external reference
__all__ = [
    'create_building_metrics_table',
    'upsert_building_metrics',
    'get_building_metrics',
    'migrate_add_calculation_columns',
    'USE_TYPE_SQFT_COLUMNS'
]
