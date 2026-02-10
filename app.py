"""
Fischer 50K Building Lead Tool - Web Interface

Main Streamlit application for building data retrieval and narrative generation.
Enter a BBL to retrieve building energy data, LL97 compliance info, and
AI-generated system narratives.
"""

import streamlit as st
from lib.database import fetch_building_by_bbl, get_building_count, check_building_processed
from lib.waterfall import fetch_building_waterfall
from lib.api_client import generate_all_narratives, NARRATIVE_CATEGORIES
from lib.validators import validate_bbl, bbl_to_dashed, get_borough_name
from lib.storage import migrate_add_calculation_columns
from datetime import datetime, timedelta


# Page configuration
st.set_page_config(
    page_title="Fischer 50K Building Lead Tool",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Run schema migration to ensure penalty and narrative columns exist
try:
    migrate_add_calculation_columns()
except Exception as e:
    # Log error but don't block app startup
    import logging
    logging.warning(f"Schema migration skipped or failed: {e}")

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

    # LL87 Audit info
    st.subheader("LL87 Audit Data")
    if data.get('ll87_raw'):
        st.write(f"**Audit Period:** {data.get('ll87_period', 'Unknown')}")
        st.write(f"**Audit ID:** {data.get('ll87_audit_id', 'Unknown')}")
        with st.expander("View Raw LL87 Data", expanded=False):
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


def display_narratives(narratives: dict):
    """Display AI-generated system narratives."""
    st.subheader("System Narratives")
    st.markdown("*AI-generated descriptions based on available building data*")

    if not narratives:
        st.info("No narratives generated yet")
        return

    for category in NARRATIVE_CATEGORIES:
        narrative = narratives.get(category, "Not generated")
        with st.expander(f"{category} Narrative", expanded=False):
            if narrative.startswith("Error"):
                st.error(narrative)
            else:
                st.write(narrative)


# Main App
st.title("Fischer 50K Building Lead Tool")
st.markdown("Enter a BBL to retrieve building energy data, compliance status, and system narratives.")

# BBL Input Form
with st.form("bbl_form", clear_on_submit=False):
    col1, col2 = st.columns([3, 1])

    with col1:
        bbl_input = st.text_input(
            "BBL (10-digit numeric)",
            placeholder="1011190036",
            max_chars=10,
            help="Borough-Block-Lot identifier. Example: 1011190036 (Manhattan, Block 01119, Lot 0036)"
        )

    with col2:
        st.write("")  # Spacer for alignment
        submitted = st.form_submit_button("Retrieve Data", use_container_width=True)

# Process form submission
if submitted:
    if not bbl_input:
        st.error("Please enter a BBL number")
    elif not validate_bbl(bbl_input):
        st.error(f"Invalid BBL format: '{bbl_input}'. BBL must be 10 digits with borough 1-5.")
    else:
        # Check if building already processed (cache check)
        cached_ts = check_building_processed(bbl_input)
        refetch = False

        if cached_ts:
            # Parse timestamp to check if recent (within 24 hours)
            try:
                last_updated = datetime.fromisoformat(cached_ts.replace('+00:00', ''))
                age = datetime.utcnow() - last_updated
                is_recent = age < timedelta(hours=24)

                st.info(f"Last processed: {cached_ts}")

                # Offer re-fetch option
                refetch = st.checkbox(
                    "Re-fetch live data",
                    value=not is_recent,  # Default to refetch if older than 24h
                    help="Check this to fetch fresh data from NYC APIs"
                )
            except Exception:
                # If timestamp parsing fails, just refetch
                refetch = True

        # Execute waterfall (either first time or user requested refetch)
        if not cached_ts or refetch:
            with st.spinner("Running data retrieval waterfall (LL97 -> LL84 API -> LL87 -> Penalties -> Narratives)..."):
                try:
                    building_data = fetch_building_waterfall(bbl_input, save_to_db=True)

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

                except Exception as e:
                    st.error(f"Waterfall error: {str(e)}")
                    building_data = None
        else:
            # Use cached data from Building_Metrics
            with st.spinner("Loading cached building data..."):
                try:
                    from lib.database import fetch_building_from_metrics
                    building_data = fetch_building_from_metrics(bbl_input)

                    # If cached data doesn't have ll87_raw, fetch it separately
                    if building_data and not building_data.get('ll87_raw'):
                        # Query ll87_raw separately for display in Energy Data tab
                        ll87_data = fetch_building_by_bbl(bbl_input)
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
            st.warning(f"No data found for BBL {bbl_input}. This building may not be in the LL97 Covered Buildings List or NYC APIs.")
        else:
            st.session_state.building_data = building_data
            st.session_state.current_bbl = bbl_input
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
        display_narratives(st.session_state.narratives)

# Footer with building count
st.divider()
try:
    total_buildings = get_building_count()
    st.caption(f"Database contains {total_buildings:,} covered buildings")
except Exception:
    st.caption("Fischer 50K Building Lead Tool")
