"""
NYC Open Data API clients for GeoSearch, LL84, and PLUTO.

Provides robust API clients with retry logic, field mapping, and error handling
for the three external APIs used in the waterfall pipeline.
"""

import logging
import os
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sodapy import Socrata

from lib.validators import validate_bbl

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================

def _create_retry_session() -> requests.Session:
    """
    Create a requests Session with retry logic.

    Retries on 429 (rate limit) and 5xx (server errors) with exponential backoff.

    Returns:
        Configured requests.Session with retry adapter
    """
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def _safe_float(value: Any) -> Optional[float]:
    """
    Safely convert value to float.

    Args:
        value: Value to convert (string, number, or None)

    Returns:
        Float value or None if conversion fails
    """
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    """
    Safely convert value to int.

    Args:
        value: Value to convert (string, number, or None)

    Returns:
        Integer value or None if conversion fails
    """
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _get_app_token() -> Optional[str]:
    """
    Get NYC Open Data app token from environment or Streamlit secrets.

    Returns:
        App token string or None if not found
    """
    # Try environment variable first
    token = os.environ.get("NYC_OPEN_DATA_APP_TOKEN")
    if token:
        return token

    # Try Streamlit secrets (only in Streamlit context)
    try:
        import streamlit as st
        token = st.secrets.get("NYC_OPEN_DATA_APP_TOKEN")
        if token:
            return token
    except (ImportError, AttributeError):
        # Not in Streamlit context or secrets not configured
        pass

    return None


# ============================================================================
# LL84 Field Mapping
# ============================================================================

# Map LL84 API field names to internal Building_Metrics column names
LL84_FIELD_MAP = {
    # Base energy and building fields
    "year_built": "year_built",
    "largest_property_use_type": "property_type",
    "property_gfa_self_reported": "gfa",
    "electricity_use_grid_purchase_1": "electricity_kwh",  # Field ending in _1 is in kWh
    "natural_gas_use_kbtu": "natural_gas_kbtu",
    "fuel_oil_2_use_kbtu": "fuel_oil_kbtu",
    "district_steam_use_kbtu": "steam_kbtu",
    "site_eui_kbtu_ft": "site_eui",
    "energy_star_score": "energy_star_score",

    # Use-type square footage fields (35 fields discovered from LL84 dataset)
    # Format: API field name -> internal column name (append _sqft to use type)
    "adult_education_gross_floor": "adult_education_sqft",
    "automobile_dealership_gross": "automobile_dealership_sqft",
    "bank_branch_gross_floor_area": "bank_branch_sqft",
    "barracks_gross_floor_area": "barracks_sqft",
    "college_university_gross": "college_university_sqft",
    "convention_center_gross_floor": "convention_center_sqft",
    "courthouse_gross_floor_area": "courthouse_sqft",
    "data_center_gross_floor_area": "data_center_sqft",
    "distribution_center_gross": "distribution_center_sqft",
    "enclosed_mall_gross_floor": "enclosed_mall_sqft",
    "energy_power_station_gross": "energy_power_station_sqft",
    "financial_office_gross_floor": "financial_office_sqft",
    "food_sales_gross_floor_area": "food_sales_sqft",
    "food_service_gross_floor": "food_service_sqft",
    "hotel_gross_floor_area_ft": "hotel_sqft",
    "k_12_school_gross_floor_area": "k_12_school_sqft",
    "laboratory_gross_floor_area": "laboratory_sqft",
    "medical_office_gross_floor": "medical_office_sqft",
    "movie_theater_gross_floor": "movie_theater_sqft",
    "multifamily_housing_gross": "multifamily_housing_sqft",
    "museum_gross_floor_area_ft": "museum_sqft",
    "office_gross_floor_area_ft": "office_sqft",
    "other_gross_floor_area_ft": "other_sqft",
    "parking_gross_floor_area": "parking_sqft",
    "performing_arts_gross_floor": "performing_arts_sqft",
    "pre_school_daycare_gross": "pre_school_daycare_sqft",
    "refrigerated_warehouse_gross": "refrigerated_warehouse_sqft",
    "restaurant_gross_floor_area": "restaurant_sqft",
    "retail_store_gross_floor": "retail_store_sqft",
    "self_storage_facility_gross": "self_storage_facility_sqft",
    "senior_living_community_gross": "senior_living_community_sqft",
    "social_meeting_hall_gross": "social_meeting_hall_sqft",
    "strip_mall_gross_floor_area": "strip_mall_sqft",
    "supermarket_grocery_gross": "supermarket_grocery_sqft",
    "worship_facility_gross_floor": "worship_facility_sqft",
}


# ============================================================================
# API Client Functions
# ============================================================================

def call_geosearch_api(address: str) -> Optional[Dict[str, Any]]:
    """
    Call GeoSearch API to resolve NYC address to BBL and BIN.

    Args:
        address: Street address to geocode

    Returns:
        Dict with keys: bbl, bin, confidence, label, address
        Returns None if no match or confidence < 0.8
    """
    session = _create_retry_session()
    endpoint = "https://geosearch.planninglabs.nyc/v2/search"

    try:
        response = session.get(
            endpoint,
            params={"text": address},
            timeout=15
        )
        response.raise_for_status()

        data = response.json()
        features = data.get("features", [])

        if not features:
            logger.warning(f"GeoSearch: No results for address: {address}")
            return None

        # Extract first result
        feature = features[0]
        properties = feature.get("properties", {})
        addendum = properties.get("addendum", {})
        pad = addendum.get("pad", {})

        bbl = pad.get("bbl")
        bin_num = pad.get("bin")
        confidence = properties.get("confidence", 0)
        label = properties.get("label", "")

        # Filter low-confidence matches (research pitfall #4)
        if confidence < 0.8:
            logger.warning(
                f"GeoSearch: Low confidence match ({confidence:.2f}) for address: {address}"
            )
            return None

        logger.info(
            f"GeoSearch: Resolved '{address}' to BBL {bbl}, BIN {bin_num} "
            f"(confidence: {confidence:.2f})"
        )

        return {
            "bbl": bbl,
            "bin": bin_num,
            "confidence": confidence,
            "label": label,
            "address": address
        }

    except requests.RequestException as e:
        logger.error(f"GeoSearch API error for address '{address}': {e}")
        return None


def call_ll84_api(
    bin_number: str,
    app_token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Call LL84 API to fetch live energy benchmarking data by BIN.

    Handles semicolon-delimited multiple BINs using LIKE query.
    Maps all returned fields to internal Building_Metrics column names.

    Args:
        bin_number: NYC BIN to query (can be part of semicolon-delimited list)
        app_token: NYC Open Data app token (optional, uses _get_app_token() if None)

    Returns:
        Dict with mapped field names or None if no results
    """
    if app_token is None:
        app_token = _get_app_token()

    client = None
    try:
        client = Socrata(
            "data.cityofnewyork.us",
            app_token,
            timeout=30
        )

        # Use LIKE query to handle semicolon-delimited BINs (research pitfall #2)
        results = client.get(
            "5zyy-y8am",
            where=f"nyc_building_identification LIKE '%{bin_number}%'",
            order="last_modified_date_property DESC",
            limit=1
        )

        if not results:
            logger.warning(f"LL84: No data found for BIN {bin_number}")
            return None

        # Map API fields to internal names
        raw_data = results[0]
        mapped_data = {}

        for api_field, internal_field in LL84_FIELD_MAP.items():
            value = raw_data.get(api_field)

            # Convert to appropriate Python types
            if value is not None and value != "":
                # Determine type based on field name patterns
                if internal_field in ["year_built"]:
                    mapped_data[internal_field] = _safe_int(value)
                elif internal_field.endswith("_sqft") or internal_field in [
                    "gfa", "electricity_kwh", "natural_gas_kbtu",
                    "fuel_oil_kbtu", "steam_kbtu", "site_eui"
                ]:
                    mapped_data[internal_field] = _safe_float(value)
                elif internal_field == "energy_star_score":
                    # Energy Star Score can be text like "Not Available" — store None for non-numeric
                    mapped_data[internal_field] = _safe_int(value)
                else:
                    # String field
                    mapped_data[internal_field] = str(value)
            else:
                mapped_data[internal_field] = None

        logger.info(f"LL84: Retrieved data for BIN {bin_number}")
        return mapped_data

    except Exception as e:
        logger.error(f"LL84 API error for BIN {bin_number}: {e}")
        return None

    finally:
        if client:
            client.close()


def call_pluto_api(
    bbl: str,
    app_token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Call PLUTO API to fetch building structure data by BBL.

    Args:
        bbl: 10-digit BBL (no dashes)
        app_token: NYC Open Data app token (optional, uses _get_app_token() if None)

    Returns:
        Dict with keys: year_built, num_floors, gfa, owner_name, address, zip_code
        Returns None if BBL invalid or no results
    """
    # Validate BBL format
    if not validate_bbl(bbl):
        logger.error(f"PLUTO: Invalid BBL format: {bbl}")
        return None

    if app_token is None:
        app_token = _get_app_token()

    client = None
    try:
        client = Socrata(
            "data.cityofnewyork.us",
            app_token,
            timeout=30
        )

        # Query by BBL (10-digit numeric, no dashes)
        results = client.get(
            "64uk-42ks",
            where=f"bbl='{bbl}'",
            limit=1
        )

        if not results:
            logger.warning(f"PLUTO: No data found for BBL {bbl}")
            return None

        # Map PLUTO fields to internal names
        raw_data = results[0]
        mapped_data = {
            "year_built": _safe_int(raw_data.get("yearbuilt")),
            "num_floors": _safe_int(raw_data.get("numfloors")),
            "gfa": _safe_float(raw_data.get("bldgarea")),
            "owner_name": raw_data.get("ownername"),
            "address": raw_data.get("address"),  # CRITICAL: for GeoSearch fallback chain
            "zip_code": raw_data.get("zipcode")
        }

        logger.info(f"PLUTO: Retrieved data for BBL {bbl}")
        return mapped_data

    except Exception as e:
        logger.error(f"PLUTO API error for BBL {bbl}: {e}")
        return None

    finally:
        if client:
            client.close()
