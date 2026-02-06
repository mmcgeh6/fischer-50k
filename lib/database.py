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
    ll97_query = """
        SELECT
            bbl,
            bin_preliminary as bin,
            address_canonical as address,
            compliance_pathway
        FROM ll97_covered_buildings
        WHERE bbl = :bbl
    """
    ll97_data = conn.query(ll97_query, params={"bbl": bbl}, ttl="1h")

    if ll97_data.empty:
        return None

    # Start building result dict from LL97 data
    building = ll97_data.iloc[0].to_dict()

    # Step 2: Get LL84 energy data from deduplicated table
    # Includes pre-calculated GHG emissions and penalties
    ll84_query = """
        SELECT
            year_built,
            property_gfa as gfa,
            largest_property_use_type as property_type,
            site_eui_kbtu_ft2 as site_eui,
            electricity_use_grid_purchase_kwh as electricity_kwh,
            natural_gas_use_kbtu as natural_gas_kbtu,
            fuel_oil_2_use_kbtu as fuel_oil_kbtu,
            district_steam_use_kbtu as steam_kbtu,
            total_ghg_emissions_metric_tons_co2e as total_ghg,
            ghg_emissions_2024_2029,
            emissions_limit_2024_2029,
            penalty_2024_2029,
            ghg_emissions_2030_2034,
            emissions_limit_2030_2034,
            penalty_2030_2034,
            energy_star_score
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
