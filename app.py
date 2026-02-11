"""
Fischer 50K Building Lead Tool - Web Interface

Main Streamlit application for building data retrieval and narrative generation.
Enter a BBL to retrieve building energy data, LL97 compliance info, and
AI-generated system narratives.
"""

import streamlit as st
from lib.database import fetch_building_by_bbl, get_building_count, check_building_processed
from lib.waterfall import fetch_building_waterfall, resolve_and_fetch
from lib.api_client import generate_all_narratives, NARRATIVE_CATEGORIES
from lib.validators import validate_bbl, bbl_to_dashed, get_borough_name, normalize_input
from lib.storage import migrate_add_calculation_columns
from datetime import datetime, timedelta, timezone


# Page configuration
st.set_page_config(
    page_title="Fischer 50K Building Lead Tool",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Run schema migration once per session to ensure penalty and narrative columns exist
if 'migration_done' not in st.session_state:
    try:
        migrate_add_calculation_columns()
        st.session_state.migration_done = True
    except Exception as e:
        import logging
        logging.warning(f"Schema migration skipped or failed: {e}")
        st.session_state.migration_done = True  # Don't retry on every rerun

# Initialize session state
if 'building_data' not in st.session_state:
    st.session_state.building_data = None
if 'narratives' not in st.session_state:
    st.session_state.narratives = None
if 'current_bbl' not in st.session_state:
    st.session_state.current_bbl = None
if 'data_source' not in st.session_state:
    st.session_state.data_source = None
if 'last_processed' not in st.session_state:
    st.session_state.last_processed = None


def format_currency(value) -> str:
    """Format number as currency string."""
    if value is None or value == 0:
        return "$0"
    return f"${value:,.0f}"


def format_number(value, suffix: str = "") -> str:
    """Format number with thousands separator."""
    if value is None:
        return "N/A"
    return f"{value:,.0f}{suffix}"


def display_building_info(data: dict):
    """Display building identity and basic info."""
    st.subheader("Building Identity")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("BBL", data.get('bbl', 'N/A'))
        st.write(f"**Borough:** {get_borough_name(data.get('bbl', ''))}")

    with col2:
        st.metric("BIN", data.get('bin', 'N/A'))
        st.write(f"**Compliance Pathway:** {data.get('compliance_pathway', 'N/A')}")

    with col3:
        # Provide DOF lookup link
        bbl = data.get('bbl', '')
        if bbl:
            dashed = bbl_to_dashed(bbl)
            st.write(f"**DOF Lookup:** `{dashed}`")

    st.write(f"**Address:** {data.get('address', 'N/A')}")

    # Building characteristics
    st.subheader("Building Characteristics")
    char_cols = st.columns(4)
    char_cols[0].metric("Year Built", data.get('year_built', 'N/A'))
    char_cols[1].metric("Property Type", data.get('property_type', 'N/A'))
    char_cols[2].metric("Gross Floor Area", format_number(data.get('gfa'), " sqft"))
    char_cols[3].metric("Energy Star Score", data.get('energy_star_score', 'N/A'))

    # Debug: Raw data from Step 1
    with st.expander("Debug: Raw Identity Data", expanded=False):
        st.markdown("**Data Sources:** `{}`".format(data.get('data_source', 'N/A')))

        if data.get('_ll97_query_raw'):
            st.markdown("#### LL97 Covered Buildings Query Result")
            st.json(data['_ll97_query_raw'])
        else:
            st.info("No LL97 query data (building not in Covered Buildings List)")

        if data.get('_pluto_api_raw'):
            st.markdown("#### PLUTO API Response")
            st.json(data['_pluto_api_raw'])

        if data.get('_geosearch_api_raw'):
            st.markdown("#### GeoSearch API Response")
            st.json(data['_geosearch_api_raw'])

        # Show resolution metadata for address inputs
        if data.get('input_type') == 'address':
            st.markdown("#### Address Resolution")
            st.text(f"  Input: {data.get('resolved_from_address', 'N/A')}")
            st.text(f"  Resolved BBL: {data.get('resolved_bbl', 'N/A')}")
            st.text(f"  Confidence: {data.get('geosearch_confidence', 'N/A')}")


def display_energy_data(data: dict):
    """Display LL84 energy benchmarking data."""
    st.subheader("Energy Usage (LL84)")

    energy_cols = st.columns(4)
    energy_cols[0].metric("Electricity", format_number(data.get('electricity_kwh'), " kWh"))
    energy_cols[1].metric("Natural Gas", format_number(data.get('natural_gas_kbtu'), " kBtu"))
    energy_cols[2].metric("Fuel Oil #2", format_number(data.get('fuel_oil_kbtu'), " kBtu"))
    energy_cols[3].metric("District Steam", format_number(data.get('steam_kbtu'), " kBtu"))

    # Site EUI if available
    site_eui = data.get('site_eui')
    if site_eui:
        st.metric("Site EUI", f"{site_eui:.1f} kBtu/sqft")

    # Debug: Raw LL84 API response
    with st.expander("Debug: Raw LL84 API Response", expanded=False):
        if data.get('_ll84_api_raw'):
            st.markdown("**Full Socrata API record** (pre-mapping):")
            st.json(data['_ll84_api_raw'])

            st.markdown("#### Field Mapping Applied")
            from lib.nyc_apis import LL84_FIELD_MAP
            mapped_view = {}
            for api_field, internal_field in LL84_FIELD_MAP.items():
                raw_val = data['_ll84_api_raw'].get(api_field)
                mapped_val = data.get(internal_field)
                if raw_val is not None or mapped_val is not None:
                    mapped_view[f"{api_field} -> {internal_field}"] = {
                        "raw": raw_val,
                        "mapped": mapped_val
                    }
            st.json(mapped_view)
        else:
            st.info("No raw LL84 API response available (LL84 data may be from cache or unavailable)")

    # LL87 Audit info
    st.subheader("LL87 Audit Data")
    if data.get('ll87_raw'):
        st.write(f"**Audit Period:** {data.get('ll87_period', 'Unknown')}")
        st.write(f"**Audit ID:** {data.get('ll87_audit_id', 'Unknown')}")
        with st.expander("Debug: Raw LL87 Data", expanded=False):
            st.json(data.get('ll87_raw'))
    else:
        st.info("No LL87 audit data available for this building (not in ll87_raw table)")


def display_penalties(data: dict):
    """Display GHG emissions and LL97 penalty calculations."""
    st.subheader("LL97 Carbon Penalties")

    st.markdown("""
    LL97 imposes penalties on buildings that exceed emissions limits.
    Penalty rate: **$268 per metric ton CO2e** above the limit.
    """)

    # Check if this is stale cached data (no 'calculated' in data sources)
    data_source = data.get('data_source', '')
    if data_source and 'calculated' not in data_source and data.get('ghg_emissions_2024_2029') is None:
        st.warning("This building was cached before penalty calculations were enabled. Check **Re-fetch live data** and submit again to calculate penalties.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 2024-2029 Period")
        ghg_1 = data.get('ghg_emissions_2024_2029')
        limit_1 = data.get('emissions_limit_2024_2029')
        penalty_1 = data.get('penalty_2024_2029')

        if ghg_1 is not None:
            st.metric("GHG Emissions", f"{ghg_1:,.1f} tCO2e")
            st.metric("Emissions Limit", f"{limit_1:,.1f} tCO2e" if limit_1 else "N/A")

            excess_1 = (ghg_1 - limit_1) if limit_1 else 0
            if excess_1 > 0:
                st.metric("Excess Emissions", f"{excess_1:,.1f} tCO2e", delta=f"+{excess_1:,.1f}", delta_color="inverse")
            else:
                st.metric("Excess Emissions", "0 tCO2e (compliant)")

            st.metric("Annual Penalty", format_currency(penalty_1))
        else:
            st.info("No penalty data available for 2024-2029")

    with col2:
        st.markdown("### 2030-2034 Period")
        ghg_2 = data.get('ghg_emissions_2030_2034')
        limit_2 = data.get('emissions_limit_2030_2034')
        penalty_2 = data.get('penalty_2030_2034')

        if ghg_2 is not None:
            st.metric("GHG Emissions", f"{ghg_2:,.1f} tCO2e")
            st.metric("Emissions Limit", f"{limit_2:,.1f} tCO2e" if limit_2 else "N/A")

            excess_2 = (ghg_2 - limit_2) if limit_2 else 0
            if excess_2 > 0:
                st.metric("Excess Emissions", f"{excess_2:,.1f} tCO2e", delta=f"+{excess_2:,.1f}", delta_color="inverse")
            else:
                st.metric("Excess Emissions", "0 tCO2e (compliant)")

            st.metric("Annual Penalty", format_currency(penalty_2))
        else:
            st.info("No penalty data available for 2030-2034")

    # Debug panel
    with st.expander("Debug: Calculation Inputs", expanded=False):
        st.markdown("**Data Sources:** `{}`".format(data.get('data_source', 'N/A')))

        st.markdown("#### Energy Inputs (Step 4)")
        debug_cols = st.columns(4)
        debug_cols[0].code(f"electricity_kwh: {data.get('electricity_kwh')}")
        debug_cols[1].code(f"natural_gas_kbtu: {data.get('natural_gas_kbtu')}")
        debug_cols[2].code(f"fuel_oil_kbtu: {data.get('fuel_oil_kbtu')}")
        debug_cols[3].code(f"steam_kbtu: {data.get('steam_kbtu')}")

        has_energy = any([
            data.get('electricity_kwh') and data.get('electricity_kwh') > 0,
            data.get('natural_gas_kbtu') and data.get('natural_gas_kbtu') > 0,
            data.get('fuel_oil_kbtu') and data.get('fuel_oil_kbtu') > 0,
            data.get('steam_kbtu') and data.get('steam_kbtu') > 0,
        ])
        st.markdown(f"**Has energy data:** {'Yes' if has_energy else 'No (all None/zero — penalty will be None)'}")

        st.markdown("#### Use-Type Square Footage")
        from lib.storage import USE_TYPE_SQFT_COLUMNS
        use_types_found = {col.replace('_sqft', ''): data.get(col) for col in USE_TYPE_SQFT_COLUMNS if data.get(col)}
        if use_types_found:
            for ut, sqft in use_types_found.items():
                st.text(f"  {ut}: {sqft:,.0f} sqft")
        else:
            st.text("  (none found in data)")

        st.markdown("#### Penalty Fields in Data")
        penalty_fields = ['ghg_emissions_2024_2029', 'emissions_limit_2024_2029', 'penalty_2024_2029',
                          'ghg_emissions_2030_2034', 'emissions_limit_2030_2034', 'penalty_2030_2034']
        for field in penalty_fields:
            val = data.get(field)
            st.text(f"  {field}: {val}")


def display_narratives(narratives: dict, data: dict):
    """Display AI-generated system narratives."""
    st.subheader("System Narratives")
    st.markdown("*AI-generated descriptions based on available building data*")

    if not narratives:
        st.info("No narratives generated yet")
    else:
        for category in NARRATIVE_CATEGORIES:
            narrative = narratives.get(category, "Not generated")
            with st.expander(f"{category} Narrative", expanded=False):
                if narrative.startswith("Error"):
                    st.error(narrative)
                else:
                    st.write(narrative)

    # Debug: Show all fields sent to narrative prompts
    with st.expander("Debug: Narrative Generation Inputs", expanded=False):
        st.markdown("#### Building Context")
        context_fields = {
            'Year Built': data.get('year_built'),
            'Building Use Type': data.get('property_type'),
            'Total Gross Floor Area (sf)': data.get('gfa'),
            'Site Energy Use (kBtu/sqft)': data.get('site_eui'),
            'Fuel Oil #2 Use (kBtu)': data.get('fuel_oil_kbtu'),
            'District Steam Use (kBtu)': data.get('steam_kbtu'),
            'Natural Gas Use (kBtu)': data.get('natural_gas_kbtu'),
            'Electricity Use - Grid Purchase (kWh)': data.get('electricity_kwh'),
        }
        st.json(context_fields)

        st.markdown("#### Existing Narratives")
        narrative_cols = {
            'Building Envelope Narrative': 'envelope_narrative',
            'Heating System Narrative': 'heating_narrative',
            'Cooling System Narrative': 'cooling_narrative',
            'Air Distribution System Narrative': 'air_distribution_narrative',
            'Ventilation System Narrative': 'ventilation_narrative',
            'Domestic Hot Water System Narrative': 'dhw_narrative',
        }
        for label, col in narrative_cols.items():
            val = data.get(col)
            st.text(f"  {label}: {f'{len(val)} chars' if val else 'None'}")

        st.markdown("#### LL87 Equipment Data Extracted for Prompts")
        from lib.api_client import _extract_all_equipment_data
        equipment = _extract_all_equipment_data(data.get('ll87_raw'))
        for section_name, section_data in equipment.items():
            st.markdown(f"**{section_name}:**")
            st.text(section_data)


# Main App
st.title("Fischer 50K Building Lead Tool")
st.markdown("Enter a BBL or NYC address to retrieve building energy data, compliance status, and system narratives.")

# BBL Input Form
with st.form("bbl_form", clear_on_submit=False):
    col1, col2 = st.columns([3, 1])

    with col1:
        bbl_input = st.text_input(
            "BBL or Address",
            placeholder="1011190036 or 350 5th Ave, New York, NY",
            max_chars=200,
            help="Enter a 10-digit BBL (e.g., 1011190036), dashed BBL (e.g., 1-01119-0036), or a NYC street address."
        )

    with col2:
        st.write("")  # Spacer for alignment
        submitted = st.form_submit_button("Retrieve Data", use_container_width=True)

# Process form submission
if submitted:
    if not bbl_input or not bbl_input.strip():
        st.error("Please enter a BBL or address.")
    else:
        # Detect and normalize input
        input_type, normalized = normalize_input(bbl_input)
        effective_bbl = None

        if input_type == "dashed_bbl":
            st.info(f"Converted dashed BBL to: {normalized}")
            effective_bbl = normalized
        elif input_type == "bbl":
            effective_bbl = normalized
        else:
            st.info(f"Resolving address: '{bbl_input.strip()}'...")

        # Cache check (only for BBL inputs where we already have the BBL)
        cached_ts = None
        refetch = False

        if effective_bbl:
            cached_ts = check_building_processed(effective_bbl)

        if cached_ts:
            try:
                last_updated = datetime.fromisoformat(cached_ts.replace('+00:00', ''))
                age = datetime.now(timezone.utc) - last_updated
                is_recent = age < timedelta(hours=24)

                st.info(f"Last processed: {cached_ts}")

                refetch = st.checkbox(
                    "Re-fetch live data",
                    value=not is_recent,
                    help="Check this to fetch fresh data from NYC APIs"
                )
            except Exception:
                refetch = True

        # Execute waterfall (either first time or user requested refetch)
        if not cached_ts or refetch:
            with st.spinner("Running data retrieval waterfall..."):
                try:
                    building_data = resolve_and_fetch(bbl_input, save_to_db=True)

                    # Show resolution feedback for address input
                    if building_data.get('input_type') == 'address':
                        resolved_bbl = building_data.get('resolved_bbl', 'Unknown')
                        confidence = building_data.get('geosearch_confidence', 0)
                        st.success(
                            f"Address resolved to BBL **{resolved_bbl}** "
                            f"(confidence: {confidence:.0%})"
                        )

                    # Update effective_bbl from waterfall result
                    effective_bbl = building_data.get('resolved_bbl', building_data.get('bbl', ''))

                    # Extract narratives from waterfall result
                    narrative_map = {
                        'Building Envelope': 'envelope_narrative',
                        'Heating System': 'heating_narrative',
                        'Cooling System': 'cooling_narrative',
                        'Air Distribution System': 'air_distribution_narrative',
                        'Ventilation System': 'ventilation_narrative',
                        'Domestic Hot Water System': 'dhw_narrative',
                    }

                    # Build narratives dict from either the original keys or DB keys
                    narratives = {}
                    for category, col in narrative_map.items():
                        # Try original key first (waterfall stores under both)
                        if category in building_data:
                            narratives[category] = building_data[category]
                        elif col in building_data:
                            narratives[category] = building_data[col]

                    st.session_state.narratives = narratives if narratives else None

                except ValueError as e:
                    st.error(str(e))
                    building_data = None
                except Exception as e:
                    st.error(f"Waterfall error: {str(e)}")
                    building_data = None
        else:
            # Use cached data from Building_Metrics
            with st.spinner("Loading cached building data..."):
                try:
                    from lib.database import fetch_building_from_metrics
                    building_data = fetch_building_from_metrics(effective_bbl)

                    # If cached data doesn't have ll87_raw, fetch it separately
                    if building_data and not building_data.get('ll87_raw'):
                        ll87_data = fetch_building_by_bbl(effective_bbl)
                        if ll87_data and ll87_data.get('ll87_raw'):
                            building_data['ll87_raw'] = ll87_data['ll87_raw']

                    # Extract narratives from cached data
                    narrative_map = {
                        'Building Envelope': 'envelope_narrative',
                        'Heating System': 'heating_narrative',
                        'Cooling System': 'cooling_narrative',
                        'Air Distribution System': 'air_distribution_narrative',
                        'Ventilation System': 'ventilation_narrative',
                        'Domestic Hot Water System': 'dhw_narrative',
                    }

                    narratives = {}
                    for category, col in narrative_map.items():
                        val = building_data.get(col)
                        if val:
                            narratives[category] = val

                    # Only regenerate narratives if none found in DB and API key available
                    if not narratives:
                        import os
                        api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", None)
                        if api_key:
                            with st.spinner("Generating system narratives with Claude (this may take 30-60 seconds)..."):
                                try:
                                    narratives = generate_all_narratives(building_data)
                                except Exception as e:
                                    st.error(f"Narrative generation error: {str(e)}")
                                    narratives = None

                    st.session_state.narratives = narratives if narratives else None

                except Exception as e:
                    st.error(f"Cache retrieval error: {str(e)}")
                    building_data = None

        if not building_data:
            display_id = effective_bbl or bbl_input.strip()
            st.warning(f"No data found for '{display_id}'. This building may not be in the LL97 Covered Buildings List or NYC APIs.")
        else:
            st.session_state.building_data = building_data
            st.session_state.current_bbl = effective_bbl or building_data.get('bbl', '')
            st.session_state.data_source = building_data.get('data_source', 'unknown')
            st.session_state.last_processed = cached_ts if cached_ts else 'Just now'

            st.success(f"Retrieved data for: {building_data.get('address', 'Unknown address')}")

# Display results if data exists in session state
if st.session_state.building_data:
    data = st.session_state.building_data

    # Show data source indicators
    if st.session_state.data_source:
        st.info(f"**Data sources:** {st.session_state.data_source}")

    # Show PLUTO fallback warning if LL84 API was not used
    if st.session_state.data_source and 'll84_api' not in st.session_state.data_source:
        if 'pluto' in st.session_state.data_source:
            st.warning("LL84 energy data not available for this building. Using PLUTO fallback for basic building metrics.")

    # Create tabs for different data sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "Building Info",
        "Energy Data",
        "LL97 Penalties",
        "System Narratives"
    ])

    with tab1:
        display_building_info(data)

    with tab2:
        display_energy_data(data)

    with tab3:
        display_penalties(data)

    with tab4:
        display_narratives(st.session_state.narratives, data)

# Footer with building count
st.divider()
try:
    total_buildings = get_building_count()
    st.caption(f"Database contains {total_buildings:,} covered buildings")
except Exception:
    st.caption("Fischer 50K Building Lead Tool")
