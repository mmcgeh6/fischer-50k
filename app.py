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
    initial_sidebar_state="expanded"
)


# --- Password Gate ---
def check_password():
    """Simple password gate using st.secrets['APP_PASSWORD']."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("### Fischer 50K Building Lead Tool")
    st.markdown("Enter the team password to continue.")
    password = st.text_input("Password", type="password", key="pw_input")
    if st.button("Log in", type="primary"):
        if password == st.secrets.get("APP_PASSWORD", ""):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# Run schema migration once per session to ensure penalty and narrative columns exist
if 'migration_done' not in st.session_state:
    try:
        migrate_add_calculation_columns()
        from lib.storage import migrate_phase4_columns, migrate_phase4_native_units
        migrate_phase4_columns()
        migrate_phase4_native_units()
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
if 'edited_narratives' not in st.session_state:
    st.session_state.edited_narratives = {}
if 'edited_energy_inputs' not in st.session_state:
    st.session_state.edited_energy_inputs = {}
if 'recalculated_penalties' not in st.session_state:
    st.session_state.recalculated_penalties = None


def flush_all_session_caches():
    """Nuke all building-specific caches and widget keys on new search.

    Called immediately when the user clicks 'Retrieve Data' so the next
    building starts with a completely clean slate — no stale narratives,
    penalty edits, or widget values carried over from the previous run.
    """
    from lib.storage import USE_TYPE_SQFT_COLUMNS

    # --- 1. Reset session-state dicts/values ---
    st.session_state.building_data = None
    st.session_state.narratives = None
    st.session_state.edited_narratives = {}
    st.session_state.recalculated_penalties = None
    st.session_state.edited_energy_inputs = {}
    st.session_state.current_bbl = None
    st.session_state.data_source = None
    st.session_state.last_processed = None

    # --- 2. Delete narrative widget keys ---
    for cat in NARRATIVE_CATEGORIES:
        wk = f"narrative_{cat}"
        if wk in st.session_state:
            del st.session_state[wk]

    # --- 3. Delete penalty / energy-input widget keys ---
    for wk in [
        "penalty_elec_kwh", "penalty_gas_therms", "penalty_oil_gal",
        "penalty_steam_mlbs", "rate_elec", "rate_gas", "rate_steam", "rate_oil",
        "recalc_penalties", "save_penalties",
    ]:
        if wk in st.session_state:
            del st.session_state[wk]

    # --- 4. Delete use-type sqft widget keys ---
    for col in USE_TYPE_SQFT_COLUMNS:
        wk = f"ut_{col}"
        if wk in st.session_state:
            del st.session_state[wk]

    # --- 5. Delete narrative save button key ---
    if "save_narratives" in st.session_state:
        del st.session_state["save_narratives"]


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
    from lib.storage import USE_TYPE_SQFT_COLUMNS

    # Building Name (large) — from LL84 property_name or PLUTO owner_name
    building_name = data.get('building_name', 'Unknown Building')
    st.markdown('<p style="font-size: 0.875rem; color: rgba(49, 51, 63, 0.6); margin-bottom: -1rem;">Building Name</p>', unsafe_allow_html=True)
    st.header(building_name if building_name else "Unknown Building")

    # Address and Borough (prominent)
    address = data.get('address', 'N/A')
    borough = get_borough_name(data.get('bbl', ''))
    st.markdown('<p style="font-size: 0.875rem; color: rgba(49, 51, 63, 0.6); margin-bottom: -1rem;">Address</p>', unsafe_allow_html=True)
    st.subheader(f"{address}")
    st.write(f"**Borough:** {borough}")

    # BBL, BIN, DOF, Compliance — small underneath
    bbl = data.get('bbl', '')
    bin_val = data.get('bin', 'N/A')
    dashed = bbl_to_dashed(bbl) if bbl else 'N/A'
    pathway = data.get('compliance_pathway', 'N/A')
    cal_year = data.get('ll84_calendar_year')
    cal_year_str = f" | LL84 Data Year: **{cal_year}**" if cal_year else ""

    st.caption(f"BBL: {bbl} | BIN: {bin_val} | DOF: {dashed} | Compliance Pathway: {pathway}{cal_year_str}")

    # Building characteristics
    st.subheader("Building Characteristics")
    char_cols = st.columns(3)
    char_cols[0].metric("Year Built", data.get('year_built', 'N/A'))
    char_cols[1].metric("Property Type", data.get('property_type', 'N/A'))
    char_cols[2].metric("Energy Star Score", data.get('energy_star_score', 'N/A'))

    # GFA — Self Reported vs Calculated
    gfa_cols = st.columns(2)
    gfa_sr = data.get('gfa_self_reported') or data.get('gfa')
    gfa_calc = data.get('gfa_calculated')
    gfa_cols[0].metric("GFA — Self Reported", format_number(gfa_sr, " sqft"))
    gfa_cols[1].metric("GFA — Calculated", format_number(gfa_calc, " sqft"))

    # Non-zero use types with square footage
    st.subheader("Use Types")
    use_types_found = {}
    for col in USE_TYPE_SQFT_COLUMNS:
        value = data.get(col)
        if value and value > 0:
            readable_name = col.replace('_sqft', '').replace('_', ' ').title()
            use_types_found[readable_name] = value

    if use_types_found:
        # Display as columns of chips/text
        ut_cols = st.columns(min(len(use_types_found), 4))
        for i, (name, sqft) in enumerate(sorted(use_types_found.items(), key=lambda x: -x[1])):
            ut_cols[i % len(ut_cols)].write(f"**{name}:** {sqft:,.0f} sqft")
    else:
        st.info("No use-type square footage data available")

    # Debug info is now in the sidebar — see render_debug_sidebar()


def display_energy_data(data: dict):
    """Display LL84 energy benchmarking data with native + kBtu units."""
    from lib.conversions import kwh_to_kbtu, kbtu_to_therms, kbtu_to_gallons_fuel_oil, kbtu_to_mlbs_steam

    st.subheader("Energy Usage (LL84)")

    # Show calendar year if available
    cal_year = data.get('ll84_calendar_year')
    if cal_year:
        st.caption(f"LL84 Data Year: {cal_year}")

    energy_cols = st.columns(4)

    # Electricity: native is kWh, show kBtu conversion
    elec_kwh = data.get('electricity_kwh')
    if elec_kwh and elec_kwh > 0:
        energy_cols[0].metric("Electricity", f"{elec_kwh:,.0f} kWh")
        energy_cols[0].caption(f"{kwh_to_kbtu(elec_kwh):,.0f} kBtu")
    else:
        energy_cols[0].metric("Electricity", "N/A")

    # Natural Gas: stored as kBtu, show therms conversion
    gas_kbtu = data.get('natural_gas_kbtu')
    if gas_kbtu and gas_kbtu > 0:
        energy_cols[1].metric("Natural Gas", f"{kbtu_to_therms(gas_kbtu):,.0f} therms")
        energy_cols[1].caption(f"{gas_kbtu:,.0f} kBtu")
    else:
        energy_cols[1].metric("Natural Gas", "N/A")

    # Fuel Oil #2: stored as kBtu, show gallons conversion
    oil_kbtu = data.get('fuel_oil_kbtu')
    if oil_kbtu and oil_kbtu > 0:
        energy_cols[2].metric("Fuel Oil #2", f"{kbtu_to_gallons_fuel_oil(oil_kbtu):,.0f} gal")
        energy_cols[2].caption(f"{oil_kbtu:,.0f} kBtu")
    else:
        energy_cols[2].metric("Fuel Oil #2", "N/A")

    # District Steam: stored as kBtu, show Mlbs conversion
    steam_kbtu = data.get('steam_kbtu')
    if steam_kbtu and steam_kbtu > 0:
        energy_cols[3].metric("District Steam", f"{kbtu_to_mlbs_steam(steam_kbtu):,.1f} Mlbs")
        energy_cols[3].caption(f"{steam_kbtu:,.0f} kBtu")
    else:
        energy_cols[3].metric("District Steam", "N/A")

    # Site EUI if available
    site_eui = data.get('site_eui')
    if site_eui:
        st.metric("Site EUI", f"{site_eui:.1f} kBtu/sqft")

    # Debug info is now in the sidebar — see render_debug_sidebar()

    # LL87 Audit info (debug raw data is in the sidebar)
    st.subheader("LL87 Audit Data")
    if data.get('ll87_raw'):
        st.write(f"**Audit Period:** {data.get('ll87_period', 'Unknown')}")
        st.write(f"**Audit ID:** {data.get('ll87_audit_id', 'Unknown')}")
    else:
        st.info("No LL87 audit data available for this building (not in ll87_raw table)")


def _display_penalty_results(ghg, limit, penalty, period_label):
    """Display penalty results for a single compliance period."""
    st.markdown(f"### {period_label}")
    if ghg is not None:
        st.metric("GHG Emissions", f"{float(ghg):,.1f} tCO2e")
        st.metric("Emissions Limit", f"{float(limit):,.1f} tCO2e" if limit else "N/A")

        excess = (float(ghg) - float(limit)) if limit else 0
        if excess > 0:
            st.metric("Excess Emissions", f"{excess:,.1f} tCO2e", delta=f"+{excess:,.1f}", delta_color="inverse")
        else:
            st.metric("Excess Emissions", "0 tCO2e (compliant)")

        st.metric("Annual Penalty", format_currency(float(penalty) if penalty else 0))
    else:
        st.info(f"No penalty data available for {period_label}")


def display_penalties(data: dict):
    """Display editable LL97 penalty calculator with recalculation."""
    from lib.calculations import calculate_ll97_penalty, extract_use_type_sqft
    from lib.storage import USE_TYPE_SQFT_COLUMNS, upsert_building_metrics

    st.subheader("LL97 Carbon Penalties")

    st.markdown("""
    LL97 imposes penalties on buildings that exceed emissions limits.
    Penalty rate: **$268 per metric ton CO2e** above the limit.
    Edit energy inputs below to model scenarios, then recalculate.
    """)

    # Show calendar year
    cal_year = data.get('ll84_calendar_year')
    if cal_year:
        st.caption(f"LL84 Data Year: {cal_year}")

    # Check if this is stale cached data
    data_source = data.get('data_source', '')
    if data_source and 'calculated' not in data_source and data.get('ghg_emissions_2024_2029') is None:
        st.warning("This building was cached before penalty calculations were enabled. Check **Re-fetch live data** and submit again to calculate penalties.")

    # --- Editable Energy Inputs (native units with kBtu conversion) ---
    st.markdown("#### Energy Inputs")
    from lib.conversions import (
        kwh_to_kbtu, kbtu_to_therms, kbtu_to_gallons_fuel_oil, kbtu_to_mlbs_steam,
        therms_to_kbtu, gallons_to_kbtu, mlbs_to_kbtu
    )

    input_cols = st.columns(4)

    # Electricity: kWh is already the native unit
    elec_kwh_val = input_cols[0].number_input(
        "Electricity (kWh)", value=float(data.get('electricity_kwh') or 0),
        min_value=0.0, step=1000.0, format="%.0f", key="penalty_elec_kwh"
    )

    # Natural Gas: stored as kBtu, input in therms
    gas_kbtu_stored = float(data.get('natural_gas_kbtu') or 0)
    gas_therms_val = input_cols[1].number_input(
        "Natural Gas (therms)", value=kbtu_to_therms(gas_kbtu_stored),
        min_value=0.0, step=100.0, format="%.0f", key="penalty_gas_therms"
    )
    gas_kbtu_val = therms_to_kbtu(gas_therms_val)
    input_cols[1].caption(f"= {gas_kbtu_val:,.0f} kBtu")

    # Fuel Oil #2: stored as kBtu, input in gallons
    oil_kbtu_stored = float(data.get('fuel_oil_kbtu') or 0)
    oil_gal_val = input_cols[2].number_input(
        "Fuel Oil #2 (gal)", value=kbtu_to_gallons_fuel_oil(oil_kbtu_stored),
        min_value=0.0, step=100.0, format="%.0f", key="penalty_oil_gal"
    )
    oil_kbtu_val = gallons_to_kbtu(oil_gal_val)
    input_cols[2].caption(f"= {oil_kbtu_val:,.0f} kBtu")

    # District Steam: stored as kBtu, input in Mlbs
    steam_kbtu_stored = float(data.get('steam_kbtu') or 0)
    steam_mlbs_val = input_cols[3].number_input(
        "District Steam (Mlbs)", value=kbtu_to_mlbs_steam(steam_kbtu_stored),
        min_value=0.0, step=1.0, format="%.1f", key="penalty_steam_mlbs"
    )
    steam_kbtu_val = mlbs_to_kbtu(steam_mlbs_val)
    input_cols[3].caption(f"= {steam_kbtu_val:,.0f} kBtu")

    # --- Blended Utility Rates & Annual Energy Cost ---
    st.markdown("#### Blended Utility Rates")
    st.caption("Edit rates to estimate annual energy costs. These are blended averages.")

    rate_cols = st.columns(4)

    elec_rate = rate_cols[0].number_input(
        "Electricity ($/kWh)", value=0.26,
        min_value=0.0, step=0.01, format="%.2f", key="rate_elec"
    )
    gas_rate = rate_cols[1].number_input(
        "Nat. Gas ($/therm)", value=1.60,
        min_value=0.0, step=0.10, format="%.2f", key="rate_gas"
    )
    steam_rate = rate_cols[2].number_input(
        "Steam ($/Mlb)", value=50.00,
        min_value=0.0, step=1.0, format="%.2f", key="rate_steam"
    )

    # Fuel oil rate: only show if building has fuel oil data
    has_fuel_oil = oil_gal_val > 0
    if has_fuel_oil:
        oil_rate = rate_cols[3].number_input(
            "Fuel Oil ($/gal)", value=4.00,
            min_value=0.0, step=0.25, format="%.2f", key="rate_oil"
        )
    else:
        oil_rate = 0.0

    # Calculate estimated annual energy cost
    elec_cost = elec_kwh_val * elec_rate
    gas_cost = gas_therms_val * gas_rate
    steam_cost = steam_mlbs_val * steam_rate
    oil_cost = oil_gal_val * oil_rate if has_fuel_oil else 0.0
    total_energy_cost = elec_cost + gas_cost + steam_cost + oil_cost

    st.markdown("#### Estimated Annual Energy Cost")
    num_cost_cols = 4 + (1 if has_fuel_oil else 0)
    cost_cols = st.columns(num_cost_cols)
    cost_cols[0].metric("Electricity", format_currency(elec_cost))
    cost_cols[1].metric("Natural Gas", format_currency(gas_cost))
    cost_cols[2].metric("Steam", format_currency(steam_cost))
    idx = 3
    if has_fuel_oil:
        cost_cols[idx].metric("Fuel Oil", format_currency(oil_cost))
        idx += 1
    cost_cols[idx].metric("Total Energy Cost", format_currency(total_energy_cost))

    # --- Editable Use-Type Square Footage ---
    st.markdown("#### Use-Type Square Footage")
    use_types_with_data = {}
    for col in USE_TYPE_SQFT_COLUMNS:
        value = data.get(col)
        if value and value > 0:
            readable_name = col.replace('_sqft', '').replace('_', ' ').title()
            use_types_with_data[col] = (readable_name, value)

    edited_use_types = {}
    if use_types_with_data:
        ut_cols = st.columns(min(len(use_types_with_data), 3))
        for i, (col, (name, sqft)) in enumerate(use_types_with_data.items()):
            edited_val = ut_cols[i % len(ut_cols)].number_input(
                f"{name} (sqft)", value=float(sqft),
                min_value=0.0, step=1000.0, format="%.0f",
                key=f"ut_{col}"
            )
            edited_use_types[col.replace('_sqft', '')] = edited_val
    else:
        st.info("No use-type square footage data available")

    # --- Recalculate Button ---
    btn_cols = st.columns([1, 1, 3])

    if btn_cols[0].button("Recalculate Penalties", key="recalc_penalties"):
        recalc = calculate_ll97_penalty(
            electricity_kwh=elec_kwh_val if elec_kwh_val > 0 else None,
            natural_gas_kbtu=gas_kbtu_val if gas_kbtu_val > 0 else None,
            fuel_oil_kbtu=oil_kbtu_val if oil_kbtu_val > 0 else None,
            steam_kbtu=steam_kbtu_val if steam_kbtu_val > 0 else None,
            use_type_sqft=edited_use_types
        )
        st.session_state.recalculated_penalties = recalc
        st.session_state.edited_energy_inputs = {
            'electricity_kwh': elec_kwh_val if elec_kwh_val > 0 else None,
            'natural_gas_kbtu': gas_kbtu_val if gas_kbtu_val > 0 else None,
            'fuel_oil_kbtu': oil_kbtu_val if oil_kbtu_val > 0 else None,
            'steam_kbtu': steam_kbtu_val if steam_kbtu_val > 0 else None,
            'natural_gas_therms': gas_therms_val if gas_therms_val > 0 else None,
            'fuel_oil_gallons': oil_gal_val if oil_gal_val > 0 else None,
            'steam_mlbs': steam_mlbs_val if steam_mlbs_val > 0 else None,
        }
        st.rerun()

    # --- Display Results ---
    penalties = st.session_state.recalculated_penalties
    if penalties and any(v is not None for v in penalties.values()):
        st.success("Showing recalculated penalties (edited inputs)")
    else:
        penalties = {
            'ghg_emissions_2024_2029': data.get('ghg_emissions_2024_2029'),
            'emissions_limit_2024_2029': data.get('emissions_limit_2024_2029'),
            'penalty_2024_2029': data.get('penalty_2024_2029'),
            'ghg_emissions_2030_2034': data.get('ghg_emissions_2030_2034'),
            'emissions_limit_2030_2034': data.get('emissions_limit_2030_2034'),
            'penalty_2030_2034': data.get('penalty_2030_2034'),
        }

    col1, col2 = st.columns(2)
    with col1:
        _display_penalty_results(
            penalties.get('ghg_emissions_2024_2029'),
            penalties.get('emissions_limit_2024_2029'),
            penalties.get('penalty_2024_2029'),
            "2024-2029 Period"
        )
    with col2:
        _display_penalty_results(
            penalties.get('ghg_emissions_2030_2034'),
            penalties.get('emissions_limit_2030_2034'),
            penalties.get('penalty_2030_2034'),
            "2030-2034 Period"
        )

    # --- Save Edits to Supabase ---
    if btn_cols[1].button("Save Edits to Supabase", key="save_penalties"):
        save_data = {'bbl': data.get('bbl')}

        # Save edited energy inputs if any
        edited_energy = st.session_state.edited_energy_inputs
        if edited_energy:
            save_data.update({k: v for k, v in edited_energy.items() if v is not None})

        # Save edited use-type sqft
        for col in USE_TYPE_SQFT_COLUMNS:
            key = col.replace('_sqft', '')
            if key in edited_use_types and edited_use_types[key] > 0:
                save_data[col] = edited_use_types[key]

        # Save recalculated penalties
        recalc = st.session_state.recalculated_penalties
        if recalc:
            for k, v in recalc.items():
                if v is not None:
                    save_data[k] = float(v)

        try:
            upsert_building_metrics(save_data)
            st.success("Penalty edits saved to Supabase!")
        except Exception as e:
            st.error(f"Save failed: {e}")

    # Debug info is now in the sidebar — see render_debug_sidebar()


def display_narratives(narratives: dict, data: dict):
    """Display editable AI-generated system narratives."""
    from lib.storage import upsert_building_metrics

    st.subheader("System Narratives")
    st.markdown("*AI-generated descriptions based on available building data. Edit below and save.*")

    narrative_col_map = {
        'Building Envelope': 'envelope_narrative',
        'Heating System': 'heating_narrative',
        'Cooling System': 'cooling_narrative',
        'Air Distribution System': 'air_distribution_narrative',
        'Ventilation System': 'ventilation_narrative',
        'Domestic Hot Water System': 'dhw_narrative',
    }

    if not narratives:
        st.info("No narratives generated yet")
    else:
        for category in NARRATIVE_CATEGORIES:
            narrative = narratives.get(category, "Not generated")
            with st.expander(f"{category} Narrative", expanded=False):
                if narrative.startswith("Error"):
                    st.error(narrative)
                else:
                    edited = st.text_area(
                        f"Edit {category}",
                        value=narrative,
                        height=200,
                        key=f"narrative_{category}",
                        label_visibility="collapsed"
                    )
                    st.session_state.edited_narratives[category] = edited

    # Save button
    if st.button("Save Narratives to Supabase", key="save_narratives"):
        save_data = {'bbl': data.get('bbl')}
        for category, col in narrative_col_map.items():
            edited_val = st.session_state.edited_narratives.get(category)
            if edited_val:
                save_data[col] = edited_val

        try:
            upsert_building_metrics(save_data)
            st.success("Narratives saved to Supabase!")
        except Exception as e:
            st.error(f"Save failed: {e}")

    # Debug info is now in the sidebar — see render_debug_sidebar()


def render_debug_sidebar(data: dict):
    """Render all debug/raw data in the sidebar for side-by-side viewing.

    Uses Streamlit's native st.sidebar which provides independent scrolling
    from the main page content. Teal background is applied via CSS injection.
    """
    st.sidebar.markdown("### 🛠️ Debug Panel")
    st.sidebar.caption("Raw data from each waterfall step")

    # Section 1: Raw Identity Data (from Building Info tab)
    with st.sidebar.expander("Raw Identity Data (Step 1)", expanded=False):
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

        if data.get('input_type') == 'address':
            st.markdown("#### Address Resolution")
            st.text(f"  Input: {data.get('resolved_from_address', 'N/A')}")
            st.text(f"  Resolved BBL: {data.get('resolved_bbl', 'N/A')}")
            st.text(f"  Confidence: {data.get('geosearch_confidence', 'N/A')}")

    # Section 2: Raw LL84 API Response (from Energy Data tab)
    with st.sidebar.expander("Raw LL84 API Response (Step 2)", expanded=False):
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

    # Section 3: Raw LL87 Data (from Energy Data tab)
    with st.sidebar.expander("Raw LL87 Data (Step 3)", expanded=False):
        if data.get('ll87_raw'):
            st.json(data.get('ll87_raw'))
        else:
            st.info("No LL87 audit data available for this building")

    # Section 4: Calculation Inputs (from Penalties tab)
    with st.sidebar.expander("Calculation Inputs (Step 4)", expanded=False):
        st.markdown("**Data Sources:** `{}`".format(data.get('data_source', 'N/A')))

        st.markdown("#### Energy Inputs")
        st.code(f"electricity_kwh: {data.get('electricity_kwh')}")
        st.code(f"natural_gas_kbtu: {data.get('natural_gas_kbtu')}")
        st.code(f"fuel_oil_kbtu: {data.get('fuel_oil_kbtu')}")
        st.code(f"steam_kbtu: {data.get('steam_kbtu')}")

        has_energy = any([
            data.get('electricity_kwh') and data.get('electricity_kwh') > 0,
            data.get('natural_gas_kbtu') and data.get('natural_gas_kbtu') > 0,
            data.get('fuel_oil_kbtu') and data.get('fuel_oil_kbtu') > 0,
            data.get('steam_kbtu') and data.get('steam_kbtu') > 0,
        ])
        st.markdown(f"**Has energy data:** {'Yes' if has_energy else 'No (all None/zero — penalty will be None)'}")

        st.markdown("#### Use-Type Square Footage")
        from lib.storage import USE_TYPE_SQFT_COLUMNS as _UT_COLS_DBG
        use_types_debug = {col.replace('_sqft', ''): data.get(col) for col in _UT_COLS_DBG if data.get(col)}
        if use_types_debug:
            for ut, sqft in use_types_debug.items():
                st.text(f"  {ut}: {sqft:,.0f} sqft")
        else:
            st.text("  (none found in data)")

        st.markdown("#### Penalty Fields in Data")
        penalty_fields = ['ghg_emissions_2024_2029', 'emissions_limit_2024_2029', 'penalty_2024_2029',
                          'ghg_emissions_2030_2034', 'emissions_limit_2030_2034', 'penalty_2030_2034']
        for field in penalty_fields:
            val = data.get(field)
            st.text(f"  {field}: {val}")

    # Section 5: Narrative Generation Inputs (from Narratives tab)
    with st.sidebar.expander("Narrative Inputs (Step 5)", expanded=False):
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
        narrative_cols_dbg = {
            'Building Envelope': 'envelope_narrative',
            'Heating System': 'heating_narrative',
            'Cooling System': 'cooling_narrative',
            'Air Distribution': 'air_distribution_narrative',
            'Ventilation': 'ventilation_narrative',
            'DHW': 'dhw_narrative',
        }
        for label, col in narrative_cols_dbg.items():
            val = data.get(col)
            st.text(f"  {label}: {f'{len(val)} chars' if val else 'None'}")

        st.markdown("#### LL87 Equipment Data Extracted for Prompts")
        from lib.api_client import _extract_all_equipment_data
        equipment = _extract_all_equipment_data(data.get('ll87_raw'))
        for section_name, section_data in equipment.items():
            st.markdown(f"**{section_name}:**")
            st.text(section_data)


def display_database_record(data: dict):
    """Display complete database record from building_metrics table."""
    st.subheader("Database Record")
    st.markdown("*Complete record stored in Supabase `building_metrics` table*")

    # Show record metadata
    meta_cols = st.columns(3)
    meta_cols[0].metric("BBL", data.get('bbl', 'N/A'))
    created = data.get('created_at', 'N/A')
    updated = data.get('updated_at', 'N/A')
    meta_cols[1].write(f"**Created:** {created}")
    meta_cols[2].write(f"**Updated:** {updated}")

    # Section 1: Identity Fields
    with st.expander("Identity Fields (Step 1: LL97/GeoSearch)", expanded=True):
        identity_fields = {
            'Building Name': data.get('building_name'),
            'BBL': data.get('bbl'),
            'BIN': data.get('bin'),
            'Address': data.get('address'),
            'ZIP Code': data.get('zip_code'),
            'Compliance Pathway': data.get('compliance_pathway'),
        }
        for label, value in identity_fields.items():
            st.text(f"{label}: {value if value is not None else 'N/A'}")

    # Section 2: Building Characteristics
    with st.expander("Building Characteristics (Step 2: LL84/PLUTO)", expanded=True):
        char_fields = {
            'Year Built': data.get('year_built'),
            'Property Type': data.get('property_type'),
            'GFA - Self Reported (sqft)': data.get('gfa_self_reported') or data.get('gfa'),
            'GFA - Calculated (sqft)': data.get('gfa_calculated'),
            'Energy Star Score': data.get('energy_star_score'),
        }
        for label, value in char_fields.items():
            st.text(f"{label}: {value if value is not None else 'N/A'}")

    # Section 3: Energy Metrics
    with st.expander("Energy Metrics (Step 2: LL84)", expanded=True):
        energy_fields = {
            'LL84 Calendar Year': data.get('ll84_calendar_year'),
            'Electricity (kWh)': data.get('electricity_kwh'),
            'Natural Gas (kBtu)': data.get('natural_gas_kbtu'),
            'Fuel Oil #2 (kBtu)': data.get('fuel_oil_kbtu'),
            'District Steam (kBtu)': data.get('steam_kbtu'),
            'Site EUI (kBtu/sqft)': data.get('site_eui'),
        }
        for label, value in energy_fields.items():
            st.text(f"{label}: {value if value is not None else 'N/A'}")

    # Section 4: Use-Type Square Footage (67 columns)
    with st.expander("Use-Type Square Footage (Step 2: LL84)", expanded=False):
        from lib.storage import USE_TYPE_SQFT_COLUMNS
        use_types_found = {}
        for col in USE_TYPE_SQFT_COLUMNS:
            value = data.get(col)
            if value and value > 0:
                # Convert column name to readable format
                readable_name = col.replace('_sqft', '').replace('_', ' ').title()
                use_types_found[readable_name] = value

        if use_types_found:
            st.write(f"**Found {len(use_types_found)} use types with square footage:**")
            for name, sqft in sorted(use_types_found.items()):
                st.text(f"  {name}: {sqft:,.0f} sqft")
        else:
            st.info("No use-type square footage data available")

    # Section 5: LL87 Reference
    with st.expander("LL87 Audit Reference (Step 3)", expanded=True):
        ll87_fields = {
            'LL87 Audit ID': data.get('ll87_audit_id'),
            'LL87 Period': data.get('ll87_period'),
        }
        for label, value in ll87_fields.items():
            st.text(f"{label}: {value if value is not None else 'N/A'}")

    # Section 6: LL97 Penalty Calculations
    with st.expander("LL97 Penalty Calculations (Step 4)", expanded=True):
        st.markdown("### 2024-2029 Period")
        period1_fields = {
            'GHG Emissions (tCO2e)': data.get('ghg_emissions_2024_2029'),
            'Emissions Limit (tCO2e)': data.get('emissions_limit_2024_2029'),
            'Annual Penalty ($)': data.get('penalty_2024_2029'),
        }
        for label, value in period1_fields.items():
            st.text(f"  {label}: {f'{value:,.2f}' if value is not None else 'N/A'}")

        st.markdown("### 2030-2034 Period")
        period2_fields = {
            'GHG Emissions (tCO2e)': data.get('ghg_emissions_2030_2034'),
            'Emissions Limit (tCO2e)': data.get('emissions_limit_2030_2034'),
            'Annual Penalty ($)': data.get('penalty_2030_2034'),
        }
        for label, value in period2_fields.items():
            st.text(f"  {label}: {f'{value:,.2f}' if value is not None else 'N/A'}")

    # Section 7: AI-Generated Narratives
    with st.expander("AI-Generated Narratives (Step 5)", expanded=False):
        narrative_fields = {
            'Building Envelope Narrative': data.get('envelope_narrative'),
            'Heating System Narrative': data.get('heating_narrative'),
            'Cooling System Narrative': data.get('cooling_narrative'),
            'Air Distribution System Narrative': data.get('air_distribution_narrative'),
            'Ventilation System Narrative': data.get('ventilation_narrative'),
            'Domestic Hot Water System Narrative': data.get('dhw_narrative'),
        }

        for label, value in narrative_fields.items():
            st.markdown(f"**{label}:**")
            if value:
                st.write(value)
            else:
                st.text("  (not generated)")
            st.divider()

    # Section 8: Data Source Tracking
    with st.expander("Data Source Tracking", expanded=True):
        tracking_fields = {
            'Data Source': data.get('data_source'),
            'Created At': data.get('created_at'),
            'Updated At': data.get('updated_at'),
        }
        for label, value in tracking_fields.items():
            st.text(f"{label}: {value if value is not None else 'N/A'}")


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

        # Flush ALL building-specific caches before processing new entry
        flush_all_session_caches()

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

    # Render debug sidebar (available from any tab, scrolls independently)
    render_debug_sidebar(data)

    # Show data source indicators
    if st.session_state.data_source:
        st.info(f"**Data sources:** {st.session_state.data_source}")

    # Show PLUTO fallback warning if LL84 API was not used
    if st.session_state.data_source and 'll84_api' not in st.session_state.data_source:
        if 'pluto' in st.session_state.data_source:
            st.warning("LL84 energy data not available for this building. Using PLUTO fallback for basic building metrics.")

    # Create tabs for different data sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Building Info",
        "Energy Data",
        "LL97 Penalties",
        "System Narratives",
        "Database Record"
    ])

    with tab1:
        display_building_info(data)

    with tab2:
        display_energy_data(data)

    with tab3:
        display_penalties(data)

    with tab4:
        display_narratives(st.session_state.narratives, data)

    with tab5:
        display_database_record(data)

    # Airtable stub button (Phase 4.1)
    st.divider()
    airtable_col1, airtable_col2, _ = st.columns([1, 1, 3])
    airtable_col2.button("Push to Airtable", key="push_airtable", disabled=True,
                         help="Airtable integration coming in Phase 4.1")

# Footer with building count
st.divider()
try:
    total_buildings = get_building_count()
    st.caption(f"Database contains {total_buildings:,} covered buildings")
except Exception:
    st.caption("Fischer 50K Building Lead Tool")
