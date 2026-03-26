"""
Claude API client for system narrative generation.

Generates 6 building system narratives using Anthropic Claude:
1. Building Envelope
2. Ventilation
3. Heating
4. Cooling
5. Domestic Hot Water
6. Controls

Narratives run sequentially - each references completed preceding narratives.
All equipment data sections are sent to every narrative call for cross-referencing.
Supports both New LL87 (2019-2024) and Old LL87 (2012-2018) column name formats.
"""

import os
import streamlit as st
from anthropic import Anthropic
from typing import Dict, Any, Optional, List
import backoff


# Six narrative categories in generation order
NARRATIVE_CATEGORIES = [
    "Building Envelope",
    "Ventilation",
    "Heating",
    "Cooling",
    "Domestic Hot Water",
    "Controls",
]


def _build_sys_columns(prefix, sys_label, count):
    """Helper to build column name lists like 'Prefix: HVAC Sys 1' through count."""
    return [f"{prefix}: {sys_label} {i}" for i in range(1, count + 1)]


def _build_old_columns(prefix, system_label, count, fields):
    """Helper to build old LL87 column names like 'Prefix_System 1_field'."""
    cols = []
    for i in range(1, count + 1):
        for field in fields:
            cols.append(f"{prefix}_{system_label} {i}_{field}")
    return cols


# ============================================================================
# Section-level column lists for the user message template.
# Each section maps to a labeled block sent to Claude in every narrative call.
# ============================================================================

# --- NEW LL87 (2019-2024) ---
SECTION_COLUMNS_NEW: Dict[str, List[str]] = {
    "bas": [
        "Building automation system? (Y/N)",
    ],

    "envelope": [
        # Exterior Walls (types 1-5)
        *[f"Exterior Walls_Exterior wall type {i}_{f}"
          for i in range(1, 6) for f in ["wall type", "if other, specify"]],
        "Exterior Walls_total exposed above grade wall area",
        "Exterior Walls_vertical glazing % of wall",
        # Windows (types 1-5)
        *[f"Envelope_Window Type {i}_{f}"
          for i in range(1, 6) for f in [
              "framing material type", "if other, specify", "# of panes",
              "glass coating type", "Operable?",
              "Sealant and weather strippping installed?"]],
        # Roof
        "Envelope_Roof_Roof type",
        "Envelope_Roof_if other, specify",
        "Envelope_Roof_Roof Area",
        "Envelope_Roof_Pitch",
        "Envelope_Roof_Roof R value",
        "Envelope_Roof_Percent of roof made up of terrace/setback",
        "Envelope_Roof_terrace/setback R value",
        "Envelope_Roof_Alternative roof system",
        "Envelope_Roof_Skylight Area",
    ],

    "ventilation": (
        _build_sys_columns("Air Exhaust Bathrooms", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Corridors", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Garage", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Kitchens", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Other", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Common Area", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Corridors", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Other", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Tenant Spaces", "HVAC Sys", 6)
        + _build_sys_columns("Demand Control Ventilation", "HVAC Sys", 6)
        + _build_sys_columns("Energy Recovery Ventilation", "HVAC Sys", 6)
        + _build_sys_columns("Outdoor Air", "HVAC Sys", 6)
        + _build_sys_columns("Ventilation System > 5 HP", "HVAC Sys", 6)
        + _build_sys_columns("Thermal Zoning", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 1", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 2", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 3", "HVAC Sys", 6)
    ),

    "air_distribution": (
        _build_sys_columns("Central Distribution Type", "HVAC Sys", 6)
        + _build_sys_columns("Delivery Equipment Type", "HVAC Sys", 6)
        + _build_sys_columns("Packged Terminal Equipment Type", "HVAC Sys", 6)
        + _build_sys_columns("Terminal Unit Type", "HVAC Sys", 6)
        + _build_sys_columns("Reheat Type", "HVAC Sys", 6)
        + _build_sys_columns("Supply Air Temperature Control", "HVAC Sys", 6)
        + _build_sys_columns("Fan Control", "HVAC Sys", 6)
        + _build_sys_columns("Fan Static Pressure Reset Control", "HVAC Sys", 6)
        + _build_sys_columns("Other Central Distribution Type", "HVAC Sys", 6)
        + _build_sys_columns("Other Delivery Equipment Type", "HVAC Sys", 6)
    ),

    "heating": (
        _build_sys_columns("Building Automation System", "Heating Plant", 4)
        + _build_sys_columns("Burner Type", "Heating Plant", 4)
        + _build_sys_columns("Burner Year Installed", "Heating Plant", 4)
        + _build_sys_columns("Direct Digital Controls", "Heating Plant", 4)
        + _build_sys_columns("Fuel Type", "Heating Plant", 4)
        + [f"Heating Plant Type {i}" for i in range(1, 5)]
        + _build_sys_columns("Heating System Type", "HVAC Sys", 6)
        + _build_sys_columns("Heating System Venting Type", "HVAC Sys", 6)
        + _build_sys_columns("Number of Pieces of Equipment", "Heating Plant", 4)
        + _build_sys_columns("Output Capacity", "Heating Plant", 4)
        + _build_sys_columns("Plant Name", "Heating Plant", 4)
        + _build_sys_columns("Rated Efficiency", "Heating Plant", 4)
        + _build_sys_columns("Venting Type", "Heating Plant", 4)
    ),

    "cooling": (
        _build_sys_columns("Approximate Year Installed", "Cooling Plant", 4)
        + _build_sys_columns("Building Automation System", "Cooling Plant", 4)
        + _build_sys_columns("Chilled Water Reset", "Cooling Plant", 4)
        + _build_sys_columns("Chiller Compressor Type", "Cooling Plant", 4)
        + _build_sys_columns("Chiller Pump Control", "Cooling Plant", 4)
        + _build_sys_columns("Condenser Type", "Cooling Plant", 4)
        + _build_sys_columns("Condition", "Cooling Plant", 4)
        + _build_sys_columns("Cooling System Approximate Year Installed", "HVAC Sys", 6)
        + _build_sys_columns("Cooling System Fuel Source", "HVAC Sys", 6)
        + _build_sys_columns("Cooling System Linked Cooling Plant", "HVAC Sys", 6)
        + _build_sys_columns("Cooling System Number of Pieces of Equipment", "HVAC Sys", 6)
        # Note: Sys 5 has a typo "SystemType" in original data
        + ["Cooling System Type: HVAC Sys 1", "Cooling System Type: HVAC Sys 2",
           "Cooling System Type: HVAC Sys 3", "Cooling System Type: HVAC Sys 4",
           "Cooling SystemType: HVAC Sys 5", "Cooling System Type: HVAC Sys 6"]
        + _build_sys_columns("Direct Digital Controls", "Cooling Plant", 4)
        + _build_sys_columns("Fuel Type", "Cooling Plant", 4)
        + _build_sys_columns("Number of Pieces of Equipment", "Cooling Plant", 4)
        + _build_sys_columns("Output Capacity", "Cooling Plant", 4)
        + _build_sys_columns("Pneumatic Controls", "Cooling Plant", 4)
        + _build_sys_columns("Principle HVAC Type", "Space Function", 6)
        + [f"Condenser Pump Control: Condensing Plant {i}" for i in range(2, 5)]
        + _build_sys_columns("Condensing Plant Type", "Condenser Plant", 4)
        + _build_sys_columns("Cooling Tower Fan Control", "Condensing Plant", 4)
    ),

    "dhw": (
        _build_sys_columns("Type", "SHW Sys", 6)
        + _build_sys_columns("Hot Water Plant", "SHW Sys", 6)
        + _build_sys_columns("Fuel Source", "SHW Sys", 6)
        + _build_sys_columns("Venting Type", "SHW Sys", 6)
        + _build_sys_columns("Efficiency units", "SHW Sys", 6)
        + _build_sys_columns("Rated Efficiency", "SHW Sys", 6)
        + _build_sys_columns("Approximate Year Installed", "SHW Sys", 6)
        + _build_sys_columns("Location of Equipment", "SHW Sys", 6)
        + _build_sys_columns("Distribution Type", "SHW Sys", 6)
        + _build_sys_columns("Tank Volume", "SHW Sys", 6)
        + _build_sys_columns("Tank Insulation Thickness", "SHW Sys", 6)
        + _build_sys_columns("Tank Insulation R-Value", "SHW Sys", 6)
        + _build_sys_columns("No Controls", "SHW Sys", 6)
        + _build_sys_columns("Time Based Controls", "SHW Sys", 6)
        + _build_sys_columns("Aquastat Based Controls", "SHW Sys", 6)
        + _build_sys_columns("Demand Based Controls", "SHW Sys", 6)
        + _build_sys_columns("EMS/BMS Controls", "SHW Sys", 6)
        + _build_sys_columns("Other Controls", "SHW Sys", 6)
    ),

    "controls": (
        _build_sys_columns("Direct Digital Controls", "HVAC Sys", 6)
        + _build_sys_columns("Manual Thermostat Controls", "HVAC Sys", 6)
        + _build_sys_columns("No Controls", "HVAC Sys", 6)
        + _build_sys_columns("Pneumatic Controls", "Cooling Plant", 4)
        + _build_sys_columns("Pneumatic Controls", "Heating Plant", 4)
        + _build_sys_columns("PnuematicControls", "HVAC Sys", 6)
        + _build_sys_columns("Programmable Thermostat Controls", "HVAC Sys", 6)
        + ["Building automation system? (Y/N)"]
    ),
}


# --- OLD LL87 (2012-2018) ---
_EXHAUST_FIELDS = ["location", "space served", "quantity", "Equipment tag #",
                   "Year Installed", "Motor HP"]
_SUPPLY_FIELDS = ["Equipment Type", "if other, specify", "Economizer",
                  "location", "space served", "quantity", "Equipment Tag#",
                  "Year Installed", "Motor HP"]
_HEATING_SYS_FIELDS = ["Heating System Type", "If other, specify", "Quantity",
                       "Equipment Tag#", "Spaces served", "Year Installed",
                       "Fuel sources", "If other, specify", "Controls",
                       "If other, specify"]
_COOLING_SYS_FIELDS = ["cooling system type", "if other, specify",
                       "Air/Water Cooled?", "Quantity", "Equipment Tag#",
                       "Spaces served", "Year Installed", "Fuel Source",
                       "If other, specify", "Controls", "If other, specify"]
_DHW_SYS_FIELDS = ["DHW system type", "if other, specify", "quantity",
                   "Equipment Tag#", "spaces served", "Year Installed",
                   "Fuel source", "If other, specify", "Controls",
                   "If other, specify", "DHW from Space heating boiler"]

SECTION_COLUMNS_OLD: Dict[str, List[str]] = {
    "bas": [
        "Building automation system? (Y/N)",
    ],

    # Envelope uses same columns for old/new (structure unchanged across periods)
    "envelope": SECTION_COLUMNS_NEW["envelope"],

    "ventilation": (
        _build_old_columns("Mechanical Ventilation System", "Exhaust System", 5, _EXHAUST_FIELDS)
        + _build_old_columns("Mechanical Ventilation System", "Supply System", 5, _SUPPLY_FIELDS)
    ),

    # Old LL87 doesn't have separate air distribution columns
    "air_distribution": [],

    "heating": (
        _build_old_columns("Heating Component", "Heating System", 5, _HEATING_SYS_FIELDS)
        + _build_old_columns("Heating Component", "Burners", 5,
                             ["Equipment Type", "quantity", "year installed"])
        + [f"Heating Component_Distribution System {i}_Central Distribution Type"
           for i in range(1, 6)]
        + _build_old_columns("Heating Component", "Terminal Type", 5,
                             ["Equipment Type", "If other, specify", "Controls",
                              "If other, specify"])
    ),

    "cooling": (
        _build_old_columns("Cooling Component", "Cooling System", 5, _COOLING_SYS_FIELDS)
    ),

    "dhw": (
        _build_old_columns("DHW System", "DHW System", 5, _DHW_SYS_FIELDS)
    ),

    "controls": (
        # Old LL87 controls are embedded in heating/cooling system records
        [f"Heating Component_Heating System {i}_{f}"
         for i in range(1, 6) for f in ["Controls", "If other, specify"]]
        + [f"Heating Component_Terminal Type {i}_{f}"
           for i in range(1, 6) for f in ["Controls", "If other, specify"]]
        + [f"Cooling Component_Cooling System {i}_{f}"
           for i in range(1, 6) for f in ["Controls", "If other, specify"]]
    ),
}


# Per-category instructions supplementing the main system prompt
CATEGORY_INSTRUCTIONS = {
    "Building Envelope": """Focus on the building envelope: exterior wall types, window types
(framing, glazing, panes, operability, sealant condition), and roof characteristics
(type, area, insulation R-value, skylights, terraces). Describe the general condition
and composition of the building shell.""",

    "Ventilation": """Focus on how air enters, circulates, and exits the building. We can
expect systems to be constant volume or variable volume, or a mix of both. There are up to
6 systems for each building. Assume System 1 is the most important, followed by system 2,
and so on. It is OK to mention equipment quantity (for example, number of fans). Please do
not mention equipment ratings, such as motor horsepower or fan cfm. Steam is not a
ventilation type, even though it may be mentioned in the data; please disregard.""",

    "Heating": """Focus on heating plants and HVAC system heating components. There are up
to 4 systems for each building. Assume System 1 is the most important, followed by system 2,
and so on.""",

    "Cooling": """Focus on cooling plants, HVAC system cooling components, and condensing
plants. There are up to 4 systems for each building. Assume System 1 is the most important,
followed by system 2, and so on.""",

    "Domestic Hot Water": """Focus on domestic hot water (DHW/SHW) systems. There are up to
6 systems for each building. Assume System 1 is the most important, followed by system 2,
and so on. The primary goal is to understand how many Domestic Hot Water Systems there are,
if they are centralized or local systems, and how they are heated/fueled.""",

    "Controls": """Focus on building controls across all HVAC systems and plants. There are
up to 6 systems for each building. Assume System 1 is the most important, followed by
system 2, and so on. The goal is to understand if there is a centralized building automation
system, with dominant control devices being digital, pneumatic, or other.""",
}


SYSTEM_PROMPT = (
    'You are supporting an engineering consultant by digesting a large database '
    'of information. For each building, you are expected to provide a brief '
    'description of the HVAC systems on site along with general functionality. '
    'This should be in paragraph form, not to exceed 3 paragraphs. Please include '
    'system type, noteworthy equipment within each system along with quantity and '
    'how it is controlled. Please exclude system ratings and capacities. There '
    'may be multiple systems present (for example, "sys 1" and "sys 2"); please '
    'prioritize system 1. Please also reference other system narratives for this '
    'building.\n\n'
    'Only discuss what is present; do not mention systems that are not present.\n\n'
    'Avoid referring to the data and documents provided in the narrative. For '
    'example, do not say "from the data provided" or "in the documentation".\n\n'
    'If a conclusion cannot be made for a specific narrative, please leave it blank.\n\n'
    'Fuel type of "other" is generally District Steam, unless otherwise noted.\n\n'
    'Do not provide energy consumption data or estimated loads for any narrative.'
)


def get_claude_client() -> Anthropic:
    """Get Anthropic client with API key from environment or Streamlit secrets."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment or Streamlit secrets")
    return Anthropic(api_key=api_key)


def _extract_columns(ll87_raw: Optional[Dict], columns: List[str]) -> str:
    """
    Extract data from LL87 raw JSONB for a list of column names.

    Uses case-insensitive fallback matching. Returns formatted string of found data.
    """
    if not ll87_raw or not columns:
        return ""

    # Build case-insensitive lookup
    field_lookup = {}
    for key in ll87_raw:
        field_lookup[key.lower().strip()] = key

    found_data = []
    for col_name in columns:
        value = ll87_raw.get(col_name)
        if value is None:
            actual_key = field_lookup.get(col_name.lower().strip())
            if actual_key:
                value = ll87_raw[actual_key]

        if value is None or value == "" or value == 0:
            continue

        found_data.append(f"- {col_name}: {value}")

    return "\n".join(found_data)


def _extract_all_sections(
    ll87_raw: Optional[Dict],
    ll87_period: Optional[str] = None,
) -> Dict[str, str]:
    """
    Extract all equipment data sections from LL87 raw JSONB.

    Selects column sets based on ll87_period:
    - '2012-2018' uses SECTION_COLUMNS_OLD
    - '2019-2024' (or anything else) uses SECTION_COLUMNS_NEW

    Returns dict with keys matching template section names.
    """
    if not ll87_raw:
        no_data = "No LL87 audit data was available for this building."
        return {
            "building_automation_system": no_data,
            "heating_equipment_specs": no_data,
            "cooling_equipment_specs": no_data,
            "air_distribution_equipment_specs": no_data,
            "ventilation_equipment_specs": no_data,
            "building_envelope_data": no_data,
            "domestic_hot_water_data": no_data,
            "controls_data": no_data,
        }

    columns = SECTION_COLUMNS_OLD if ll87_period == '2012-2018' else SECTION_COLUMNS_NEW

    def _get(section_key):
        result = _extract_columns(ll87_raw, columns.get(section_key, []))
        return result or "No data available for this section."

    return {
        "building_automation_system": _get("bas"),
        "heating_equipment_specs": _get("heating"),
        "cooling_equipment_specs": _get("cooling"),
        "air_distribution_equipment_specs": _get("air_distribution"),
        "ventilation_equipment_specs": _get("ventilation"),
        "building_envelope_data": _get("envelope"),
        "domestic_hot_water_data": _get("dhw"),
        "controls_data": _get("controls"),
    }


@backoff.on_exception(backoff.expo, Exception, max_tries=3, jitter=backoff.full_jitter)
def generate_narrative(
    client: Anthropic,
    category: str,
    building_data: Dict[str, Any],
    all_sections: Optional[Dict[str, str]] = None,
    preceding_narratives: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate a single system narrative using Claude.

    Args:
        client: Anthropic client instance
        category: Narrative category (e.g., "Heating")
        building_data: Building data dict from database
        all_sections: Pre-extracted equipment data sections for the template
        preceding_narratives: Completed narratives from earlier categories in this run

    Returns:
        Generated narrative text (1-2 paragraphs)
    """
    if all_sections is None:
        all_sections = _extract_all_sections(
            building_data.get('ll87_raw'),
            building_data.get('ll87_period'),
        )

    year_built = building_data.get('year_built') or 'Not documented'
    property_type = building_data.get('property_type') or 'Not documented'
    gfa = building_data.get('gfa') or 0
    site_eui = building_data.get('site_eui')
    site_eui_str = f"{site_eui:,.1f} kBtu/sqft" if site_eui else 'Not documented'
    electricity = building_data.get('electricity_kwh') or 0
    natural_gas = building_data.get('natural_gas_kbtu') or 0
    fuel_oil = building_data.get('fuel_oil_kbtu') or 0
    steam = building_data.get('steam_kbtu') or 0

    # Build existing narratives section
    if preceding_narratives:
        narr_parts = []
        for cat_name, narr_text in preceding_narratives.items():
            if narr_text and not narr_text.startswith("Error"):
                narr_parts.append(f"{cat_name}:\n{narr_text}")
        narratives_section = "\n\n".join(narr_parts) if narr_parts else "No preceding narratives available yet."
    else:
        narratives_section = "No preceding narratives available yet (this is the first narrative)."

    cat_instructions = CATEGORY_INSTRUCTIONS.get(category, '')

    user_message = f"""Generate a {category} Narrative for this building.

BUILDING CONTEXT:
- Year Built: {year_built}
- Building Use Type: {property_type}
- Total Gross Floor Area: {gfa:,} sqft
- Site Energy Use: {site_eui_str}
- Fuel Oil #2 Use: {fuel_oil:,} kBtu
- District Steam Use: {steam:,} kBtu
- Natural Gas Use: {natural_gas:,} kBtu
- Electricity Use - Grid Purchase: {electricity:,} kWh

BUILDING AUTOMATION SYSTEM:
{all_sections['building_automation_system']}

HEATING EQUIPMENT SPECS (Boilers, Heat Exchangers, Hot Water Pumps, Zone Equip, Service Hot Water):
{all_sections['heating_equipment_specs']}

COOLING EQUIPMENT SPECS (Chillers, Chilled Water Pumps, Cooling Towers, Condenser Water Pumps, Heat Exchangers):
{all_sections['cooling_equipment_specs']}

AIR DISTRIBUTION EQUIPMENT SPECS (Air Handling Units, Rooftop Units, Packaged Units):
{all_sections['air_distribution_equipment_specs']}

VENTILATION EQUIPMENT SPECS (Make-up Air Units, Dedicated Outdoor Air Systems, Energy Recovery Ventilators):
{all_sections['ventilation_equipment_specs']}

BUILDING ENVELOPE DATA:
{all_sections['building_envelope_data']}

DOMESTIC HOT WATER DATA:
{all_sections['domestic_hot_water_data']}

EXISTING NARRATIVES:
{narratives_section}

CATEGORY-SPECIFIC INSTRUCTIONS:
{cat_instructions}

Write a 1-2 paragraph narrative about the {category.lower()} based strictly on the data above. If system data is incomplete or unavailable, use: "Detailed system specifications were not available in the provided data.\""""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=10000,
        system=SYSTEM_PROMPT,
        temperature=0.3,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    return message.content[0].text


def generate_all_narratives(building_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate all 6 system narratives for a building, sequentially.

    Each narrative receives the completed preceding narratives as context,
    enabling cross-referencing between system descriptions.
    """
    client = get_claude_client()
    narratives = {}
    completed = {}

    all_sections = _extract_all_sections(
        building_data.get('ll87_raw'),
        building_data.get('ll87_period'),
    )

    for category in NARRATIVE_CATEGORIES:
        try:
            narratives[category] = generate_narrative(
                client, category, building_data, all_sections, completed
            )
            if not narratives[category].startswith("Error"):
                completed[category] = narratives[category]
        except Exception as e:
            narratives[category] = f"Error generating narrative: {str(e)}"

    return narratives


def generate_single_narrative(
    building_data: Dict[str, Any],
    category: str
) -> str:
    """Generate a single narrative for testing or selective regeneration."""
    if category not in NARRATIVE_CATEGORIES:
        raise ValueError(f"Invalid category. Must be one of: {NARRATIVE_CATEGORIES}")

    client = get_claude_client()
    all_sections = _extract_all_sections(
        building_data.get('ll87_raw'),
        building_data.get('ll87_period'),
    )
    return generate_narrative(client, category, building_data, all_sections)
