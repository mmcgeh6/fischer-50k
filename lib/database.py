"""
Database module for building data retrieval.

Uses Streamlit's st.connection() for PostgreSQL access with automatic
caching, secrets management, and connection pooling.

Tables accessed:
- ll97_covered_buildings: Primary building identity (BBL, BIN, address)
- ll84_data: Energy benchmarking data with penalty calculations
- ll87_raw: LL87 energy audit data (JSONB)
"""

import streamlit as st
from typing import Optional, Dict, Any
import json


def get_connection():
    """Get PostgreSQL connection using Streamlit's connection management."""
    return st.connection("postgresql", type="sql")


def fetch_building_by_bbl(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Fetch building data from all sources (LL97, LL84, LL87) for given BBL.

    This performs the data retrieval portion of the 5-step waterfall:
    1. Query LL97 Covered Buildings List for identity
    2. Query LL84 deduplicated table for energy data
    3. Query LL87 raw table for audit data

    Args:
        bbl: 10-digit BBL string

    Returns:
        Dictionary with building data from all sources, or None if not found
    """
    conn = get_connection()

    # Step 1: Get LL97 covered building info (identity, compliance pathway)
    # This is the primary source for building identity per CLAUDE.md
    # Actual column names: preliminary_bin, address, cp0-cp4 booleans
    ll97_query = """
        SELECT
            bbl,
            preliminary_bin as bin,
            address,
            zip_code,
            cp0_article_320_2024,
            cp1_article_320_2026,
            cp2_article_320_2035,
            cp3_article_321_onetime,
            cp4_city_portfolio
        FROM ll97_covered_buildings
        WHERE bbl = :bbl
    """
    ll97_data = conn.query(ll97_query, params={"bbl": bbl}, ttl="1h")

    if ll97_data.empty:
        return None

    # Start building result dict from LL97 data
    building = ll97_data.iloc[0].to_dict()

    # Derive compliance pathway string from boolean columns
    pathways = []
    if building.get('cp0_article_320_2024'):
        pathways.append('CP0 (2024)')
    if building.get('cp1_article_320_2026'):
        pathways.append('CP1 (2026)')
    if building.get('cp2_article_320_2035'):
        pathways.append('CP2 (2035)')
    if building.get('cp3_article_321_onetime'):
        pathways.append('CP3 (One-Time)')
    if building.get('cp4_city_portfolio'):
        pathways.append('CP4 (City Portfolio)')
    building['compliance_pathway'] = ', '.join(pathways) if pathways else 'None assigned'

    # Step 2: Get LL84 energy data from deduplicated table
    # Actual column names from ll84_load_supabase.py
    ll84_query = """
        SELECT
            year_built,
            total_gross_floor_area as gfa,
            property_use as property_type,
            site_energy_unit_intensity as site_eui,
            electricity_use as electricity_kwh,
            natural_gas_use as natural_gas_kbtu,
            fuel_oil_1_2_use as fuel_oil_kbtu,
            district_steam_use as steam_kbtu,
            total_carbon_emissions as total_ghg,
            total_carbon_emissions as ghg_emissions_2024_2029,
            carbon_limit_2024 as emissions_limit_2024_2029,
            penalty_2024 as penalty_2024_2029,
            total_carbon_emissions as ghg_emissions_2030_2034,
            carbon_limit_2030 as emissions_limit_2030_2034,
            penalty_2030 as penalty_2030_2034,
            energy_grade as energy_star_score
        FROM ll84_data
        WHERE bbl = :bbl
    """
    ll84_data = conn.query(ll84_query, params={"bbl": bbl}, ttl="10m")

    if not ll84_data.empty:
        # Merge LL84 data into building dict
        ll84_row = ll84_data.iloc[0].to_dict()
        building.update(ll84_row)

    # Step 3: Get LL87 audit data (latest audit, prefer 2019-2024 over 2012-2018)
    # Per CLAUDE.md: Search 2019-2024 first, fallback to 2012-2018
    ll87_query = """
        SELECT DISTINCT ON (bbl)
            bbl,
            audit_template_id,
            reporting_period,
            raw_data
        FROM ll87_raw
        WHERE bbl = :bbl
        ORDER BY bbl,
                 CASE WHEN reporting_period = '2019-2024' THEN 1 ELSE 2 END,
                 audit_template_id DESC
    """
    ll87_data = conn.query(ll87_query, params={"bbl": bbl}, ttl="1h")

    if not ll87_data.empty:
        ll87_row = ll87_data.iloc[0]
        # Store raw JSONB data for narrative generation
        raw_data = ll87_row['raw_data']
        # Handle if raw_data is already parsed or is a string
        if isinstance(raw_data, str):
            try:
                building['ll87_raw'] = json.loads(raw_data)
            except json.JSONDecodeError:
                building['ll87_raw'] = raw_data
        else:
            building['ll87_raw'] = raw_data
        building['ll87_period'] = ll87_row['reporting_period']
        building['ll87_audit_id'] = ll87_row['audit_template_id']

    return building


def get_building_count() -> int:
    """Get total count of buildings in ll97_covered_buildings table."""
    conn = get_connection()
    result = conn.query("SELECT COUNT(*) as count FROM ll97_covered_buildings", ttl="1h")
    return int(result.iloc[0]['count'])


def fetch_building_from_metrics(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Fetch building data from Building_Metrics table (cached waterfall results).

    This provides a "check cache first" option for the UI. If data exists in
    Building_Metrics, it means the waterfall has already been executed for this BBL.

    Args:
        bbl: 10-digit BBL string

    Returns:
        Dictionary with building data from Building_Metrics table, or None if not found
    """
    conn = get_connection()

    query = """
        SELECT * FROM building_metrics
        WHERE bbl = :bbl
    """

    try:
        result = conn.query(query, params={"bbl": bbl}, ttl="10m")

        if result.empty:
            return None

        # Convert to dict
        building = result.iloc[0].to_dict()
        return building

    except Exception as e:
        # Table might not exist yet - graceful degradation
        return None


def check_building_processed(bbl: str) -> Optional[str]:
    """
    Check if BBL exists in Building_Metrics table (has been processed).

    Used by UI to show "last processed" status and decide whether to re-fetch.

    Args:
        bbl: 10-digit BBL string

    Returns:
        ISO format timestamp string of when building was last updated, or None if not found
    """
    conn = get_connection()

    query = """
        SELECT updated_at FROM building_metrics
        WHERE bbl = :bbl
    """

    try:
        result = conn.query(query, params={"bbl": bbl}, ttl="10m")

        if result.empty:
            return None

        # Return timestamp as string
        updated_at = result.iloc[0]['updated_at']
        return str(updated_at)

    except Exception as e:
        # Table might not exist yet - graceful degradation
        return None
