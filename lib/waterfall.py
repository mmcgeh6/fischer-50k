"""
Waterfall orchestrator for 5-step data retrieval process.

Executes the data retrieval waterfall:
1. Identity & Compliance (LL97 -> PLUTO -> GeoSearch fallback chain)
2. Live Usage Fetch (LL84 API -> PLUTO fallback)
3. Mechanical Retrieval (LL87 raw table query)
4. LL97 Penalty Calculations
5. Narrative Generation

Saves results to Building_Metrics table and returns complete building data.
"""

import logging
from typing import Dict, Any, Optional
import json
import os

from lib.storage import get_connection as storage_get_connection, upsert_building_metrics
from lib.nyc_apis import call_ll84_api, call_pluto_api, call_geosearch_api
from lib.calculations import calculate_ll97_penalty, extract_use_type_sqft
from lib.api_client import generate_all_narratives

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions for Database Queries
# ============================================================================

def _query_ll97(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Query LL97 Covered Buildings table for identity data.

    Args:
        bbl: 10-digit BBL string

    Returns:
        Dictionary with bbl, bin, address, zip_code, compliance_pathway or None
    """
    conn = storage_get_connection()
    cursor = conn.cursor()

    try:
        query = """
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
            WHERE bbl = %s
        """
        cursor.execute(query, (bbl,))
        row = cursor.fetchone()

        if not row:
            return None

        # Parse row into dict
        result = {
            'bbl': row[0],
            'bin': row[1],
            'address': row[2],
            'zip_code': row[3]
        }

        # Derive compliance pathway from boolean columns
        pathways = []
        if row[4]:  # cp0_article_320_2024
            pathways.append('CP0 (2024)')
        if row[5]:  # cp1_article_320_2026
            pathways.append('CP1 (2026)')
        if row[6]:  # cp2_article_320_2035
            pathways.append('CP2 (2035)')
        if row[7]:  # cp3_article_321_onetime
            pathways.append('CP3 (One-Time)')
        if row[8]:  # cp4_city_portfolio
            pathways.append('CP4 (City Portfolio)')

        result['compliance_pathway'] = ', '.join(pathways) if pathways else 'None assigned'

        return result

    finally:
        cursor.close()
        conn.close()


def _query_ll87(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Query LL87 raw table for mechanical audit data.

    Searches 2019-2024 first, falls back to 2012-2018 per CLAUDE.md dual dataset protocol.

    Args:
        bbl: 10-digit BBL string

    Returns:
        Dictionary with ll87_audit_id, ll87_period, ll87_raw or None
    """
    conn = storage_get_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT DISTINCT ON (bbl)
                bbl,
                audit_template_id,
                reporting_period,
                raw_data
            FROM ll87_raw
            WHERE bbl = %s
            ORDER BY bbl,
                     CASE WHEN reporting_period = '2019-2024' THEN 1 ELSE 2 END,
                     audit_template_id DESC
        """
        cursor.execute(query, (bbl,))
        row = cursor.fetchone()

        if not row:
            return None

        # Parse JSONB data
        raw_data = row[3]
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                pass  # Keep as string if can't parse

        return {
            'll87_audit_id': row[1],
            'll87_period': row[2],
            'll87_raw': raw_data
        }

    finally:
        cursor.close()
        conn.close()


# ============================================================================
# Main Waterfall Function
# ============================================================================

def fetch_building_waterfall(bbl: str, save_to_db: bool = True) -> Dict[str, Any]:
    """
    Execute the 5-step data retrieval waterfall for a given BBL.

    Step 1: Identity & Compliance (LL97 -> PLUTO -> GeoSearch fallback)
    Step 2: Live Usage Fetch (LL84 API -> PLUTO fallback)
    Step 3: Mechanical Retrieval (LL87 raw table)
    Step 4: LL97 Penalty Calculations
    Step 5: Narrative Generation

    Args:
        bbl: 10-digit BBL string (no dashes)
        save_to_db: If True, save results to Building_Metrics table

    Returns:
        Dictionary with all retrieved data and data_source tracking string
    """
    logger.info(f"Step 1: Resolving identity for BBL {bbl}")

    # Initialize result dict
    result = {'bbl': bbl}
    data_sources = []

    # ========================================================================
    # STEP 1: Identity & Compliance
    # ========================================================================

    # Try LL97 table first (primary source)
    ll97_data = _query_ll97(bbl)

    if ll97_data:
        logger.info("Step 1: BBL found in LL97 table")
        result.update(ll97_data)
        data_sources.append('ll97')
    else:
        # LL97 miss - execute PLUTO -> GeoSearch fallback chain
        logger.warning("Step 1: BBL not in LL97, executing PLUTO->GeoSearch fallback chain")

        # Call PLUTO to get building data (including address)
        pluto_data = call_pluto_api(bbl)

        if pluto_data and pluto_data.get('address'):
            pluto_address = pluto_data['address']
            logger.info(f"Step 1: PLUTO returned address '{pluto_address}', querying GeoSearch for BIN")

            # Store PLUTO data (year_built, gfa, etc.)
            result.update({
                'year_built': pluto_data.get('year_built'),
                'gfa': pluto_data.get('gfa'),
                'address': pluto_address,
                'zip_code': pluto_data.get('zip_code')
            })
            data_sources.append('pluto')

            # Call GeoSearch with PLUTO address to resolve BIN
            geosearch_data = call_geosearch_api(pluto_address)

            if geosearch_data and geosearch_data.get('bin'):
                logger.info(f"Step 1: GeoSearch resolved BIN {geosearch_data['bin']} from PLUTO address")
                result['bin'] = geosearch_data['bin']
                data_sources.append('geosearch')
            else:
                logger.warning("Step 1: GeoSearch failed to resolve BIN from PLUTO address")
        elif pluto_data:
            # PLUTO returned data but no address
            logger.warning("Step 1: PLUTO returned no address for BBL, cannot resolve BIN")
            result.update({
                'year_built': pluto_data.get('year_built'),
                'gfa': pluto_data.get('gfa'),
                'zip_code': pluto_data.get('zip_code')
            })
            data_sources.append('pluto')
        else:
            # PLUTO itself failed
            logger.error(f"Step 1: PLUTO returned no data for BBL {bbl}")

    # ========================================================================
    # STEP 2: Live Usage Fetch
    # ========================================================================

    bin_number = result.get('bin')

    if bin_number:
        logger.info(f"Step 2: Fetching LL84 data for BIN {bin_number}")

        # Try LL84 API
        ll84_data = call_ll84_api(bin_number)

        if ll84_data:
            # Merge all LL84 fields into result (energy metrics + use-type sqft fields)
            result.update(ll84_data)
            data_sources.append('ll84_api')
        else:
            # LL84 miss - fallback to PLUTO if not already called in Step 1
            logger.warning("Step 2: LL84 data not found, falling back to PLUTO")

            if 'pluto' not in data_sources:
                # Haven't called PLUTO yet in Step 1, call it now
                pluto_data = call_pluto_api(bbl)
                if pluto_data:
                    # PLUTO provides year_built, gfa but NOT energy metrics
                    result.update({
                        'year_built': pluto_data.get('year_built'),
                        'gfa': pluto_data.get('gfa'),
                        'address': pluto_data.get('address'),
                        'zip_code': pluto_data.get('zip_code')
                    })
                    data_sources.append('pluto')
            # else: PLUTO already called in Step 1, data already merged
    else:
        logger.warning("Step 2: No BIN available, skipping LL84 API fetch")

        # Try PLUTO for basic building metrics if not already called
        if 'pluto' not in data_sources:
            pluto_data = call_pluto_api(bbl)
            if pluto_data:
                result.update({
                    'year_built': pluto_data.get('year_built'),
                    'gfa': pluto_data.get('gfa'),
                    'address': pluto_data.get('address'),
                    'zip_code': pluto_data.get('zip_code')
                })
                data_sources.append('pluto')

    # ========================================================================
    # STEP 3: Mechanical Retrieval
    # ========================================================================

    logger.info(f"Step 3: Retrieving LL87 mechanical data for BBL {bbl}")

    ll87_data = _query_ll87(bbl)

    if ll87_data:
        result.update(ll87_data)
        data_sources.append('ll87')

    # ========================================================================
    # STEP 4: LL97 Penalty Calculations
    # ========================================================================

    try:
        logger.info(f"Step 4: Calculating LL97 penalties for BBL {bbl}")

        # Extract energy values from result dict (using 'or 0' pattern for None values)
        electricity_kwh = result.get('electricity_kwh') or 0
        natural_gas_kbtu = result.get('natural_gas_kbtu') or 0
        fuel_oil_kbtu = result.get('fuel_oil_kbtu') or 0
        steam_kbtu = result.get('steam_kbtu') or 0

        # Extract use-type sqft from result dict
        use_type_sqft = extract_use_type_sqft(result)

        # Calculate penalties
        penalty_result = calculate_ll97_penalty(
            electricity_kwh,
            natural_gas_kbtu,
            fuel_oil_kbtu,
            steam_kbtu,
            use_type_sqft
        )

        # Check if penalty calculation returned data (not all None values)
        if penalty_result and any(v is not None for v in penalty_result.values()):
            logger.info(f"Step 4: Penalty calculation successful for BBL {bbl}")

            # Convert Decimal to float for storage (psycopg2 handles float->NUMERIC fine)
            for key, value in penalty_result.items():
                if value is not None:
                    result[key] = float(value)
                else:
                    result[key] = None

            data_sources.append('calculated')

            # Save penalty data to database
            if save_to_db:
                penalty_db_data = {'bbl': bbl}
                penalty_db_data.update({k: result[k] for k in penalty_result.keys()})
                try:
                    upsert_building_metrics(penalty_db_data)
                    logger.info(f"Step 4: Saved penalty data to Building_Metrics for BBL {bbl}")
                except Exception as e:
                    logger.error(f"Step 4: Failed to save penalty data: {e}")
        else:
            logger.warning(f"Step 4: No penalty data calculated for BBL {bbl} (missing required data)")

    except Exception as e:
        logger.error(f"Step 4: Penalty calculation error for BBL {bbl}: {e}")

    # ========================================================================
    # STEP 5: Narrative Generation
    # ========================================================================

    try:
        # Check if ANTHROPIC_API_KEY is available
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("ANTHROPIC_API_KEY")
            except Exception:
                pass

        if api_key:
            logger.info(f"Step 5: Generating system narratives for BBL {bbl}")

            # Generate all 6 narratives
            narratives = generate_all_narratives(result)

            # Map narrative dict keys to DB column names
            narrative_map = {
                "Building Envelope": "envelope_narrative",
                "Heating System": "heating_narrative",
                "Cooling System": "cooling_narrative",
                "Air Distribution System": "air_distribution_narrative",
                "Ventilation System": "ventilation_narrative",
                "Domestic Hot Water System": "dhw_narrative"
            }

            # Store narratives in result dict under both original and DB keys
            for category, db_column in narrative_map.items():
                if category in narratives:
                    result[db_column] = narratives[category]
                    # Also keep under original category key for backwards compatibility
                    result[category] = narratives[category]

            data_sources.append('narratives')

            # Save narrative data to database
            if save_to_db:
                narrative_db_data = {'bbl': bbl}
                # Only include the DB column names
                for db_column in narrative_map.values():
                    if db_column in result:
                        narrative_db_data[db_column] = result[db_column]

                try:
                    upsert_building_metrics(narrative_db_data)
                    logger.info(f"Step 5: Saved narratives to Building_Metrics for BBL {bbl}")
                except Exception as e:
                    logger.error(f"Step 5: Failed to save narratives: {e}")
        else:
            logger.warning("Step 5: ANTHROPIC_API_KEY not available, skipping narrative generation")

    except Exception as e:
        logger.error(f"Step 5: Narrative generation error for BBL {bbl}: {e}")

    # ========================================================================
    # Finalize and Save
    # ========================================================================

    # Set data source tracking string
    result['data_source'] = ','.join(data_sources)

    logger.info(f"Waterfall complete for BBL {bbl}, sources: {result['data_source']}")

    # Save basic building data to Building_Metrics table if requested
    # (Penalties and narratives already saved in Steps 4-5)
    if save_to_db:
        # Prepare data for Building_Metrics (exclude ll87_raw JSONB - stays in ll87_raw table)
        # Also exclude narratives (already saved) to avoid duplication
        exclude_keys = {'ll87_raw', 'Building Envelope', 'Heating System', 'Cooling System',
                       'Air Distribution System', 'Ventilation System', 'Domestic Hot Water System'}
        db_data = {k: v for k, v in result.items() if k not in exclude_keys}

        try:
            upsert_building_metrics(db_data)
            logger.info(f"Saved building data to Building_Metrics table for BBL {bbl}")
        except Exception as e:
            logger.error(f"Failed to save to Building_Metrics: {e}")

    return result
