"""
Claude API client for system narrative generation.

Generates 5 building system narratives using Anthropic Claude:
1. Ventilation
2. Controls
3. Heating
4. Cooling
5. Domestic Hot Water

Narratives run sequentially - each references completed preceding narratives.
Uses explicit LL87 JSONB column lists per category (not keyword matching).
"""

import os
import streamlit as st
from anthropic import Anthropic
from typing import Dict, Any, Optional, List
import backoff


# Five narrative categories in generation order
NARRATIVE_CATEGORIES = [
    "Ventilation",
    "Controls",
    "Heating",
    "Cooling",
    "Domestic Hot Water",
]


def _build_sys_columns(prefix, sys_label, count):
    """Helper to build column name lists like 'Prefix: HVAC Sys 1' through count."""
    return [f"{prefix}: {sys_label} {i}" for i in range(1, count + 1)]


# Explicit LL87 JSONB column names per category.
CATEGORY_COLUMNS: Dict[str, List[str]] = {
    "Ventilation": (
        _build_sys_columns("Air Exhaust Bathrooms", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Corridors", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Garage", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Kitchens", "HVAC Sys", 6)
        + _build_sys_columns("Air Exhaust Other", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Common Area", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Corridors", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Other", "HVAC Sys", 6)
        + _build_sys_columns("Air Supply Tenant Spaces", "HVAC Sys", 6)
        + _build_sys_columns("Central Distribution Type", "HVAC Sys", 6)
        + _build_sys_columns("Delivery Equipment Type", "HVAC Sys", 6)
        + _build_sys_columns("Demand Control Ventilation", "HVAC Sys", 6)
        + _build_sys_columns("Direct Digital Controls", "HVAC Sys", 6)
        + _build_sys_columns("Energy Recovery Ventilation", "HVAC Sys", 6)
        + _build_sys_columns("Fan Control", "HVAC Sys", 6)
        + _build_sys_columns("Manual Thermostat Controls", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 1", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 2", "HVAC Sys", 6)
        + _build_sys_columns("Name: Space Function 3", "HVAC Sys", 6)
        + _build_sys_columns("No Controls", "HVAC Sys", 6)
        + _build_sys_columns("Outdoor Air", "HVAC Sys", 6)
        + _build_sys_columns("Packged Terminal Equipment Type", "HVAC Sys", 6)
        + _build_sys_columns("PnuematicControls", "HVAC Sys", 6)
        + _build_sys_columns("Programmable Thermostat Controls", "HVAC Sys", 6)
        + _build_sys_columns("Reheat Type", "HVAC Sys", 6)
        + _build_sys_columns("Supply Air Temperature Control", "HVAC Sys", 6)
        + _build_sys_columns("Terminal Unit Type", "HVAC Sys", 6)
        + _build_sys_columns("Thermal Zoning", "HVAC Sys", 6)
        + _build_sys_columns("Ventilation System > 5 HP", "HVAC Sys", 6)
    ),

    "Controls": (
        _build_sys_columns("Direct Digital Controls", "HVAC Sys", 6)
        + _build_sys_columns("Manual Thermostat Controls", "HVAC Sys", 6)
        + _build_sys_columns("No Controls", "HVAC Sys", 6)
        + _build_sys_columns("Pneumatic Controls", "Cooling Plant", 4)
        + _build_sys_columns("Pneumatic Controls", "Heating Plant", 4)
        + _build_sys_columns("PnuematicControls", "HVAC Sys", 6)
        + _build_sys_columns("Programmable Thermostat Controls", "HVAC Sys", 6)
        + ["Building automation system? (Y/N)"]
    ),

    "Heating": (
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

    "Cooling": (
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
        + _build_sys_columns("Fan Static Pressure Reset Control", "HVAC Sys", 6)
        + _build_sys_columns("Fuel Type", "Cooling Plant", 4)
        + _build_sys_columns("Number of Pieces of Equipment", "Cooling Plant", 4)
        + _build_sys_columns("Other Central Distribution Type", "HVAC Sys", 6)
        + _build_sys_columns("Other Delivery Equipment Type", "HVAC Sys", 6)
        + _build_sys_columns("Output Capacity", "Cooling Plant", 4)
        + _build_sys_columns("Pneumatic Controls", "Cooling Plant", 4)
        + _build_sys_columns("Principle HVAC Type", "Space Function", 6)
        # Condensing Plant fields (Plant 1 missing from Condenser Pump Control per spec)
        + [f"Condenser Pump Control: Condensing Plant {i}" for i in range(2, 5)]
        + _build_sys_columns("Condensing Plant Type", "Condenser Plant", 4)
        + _build_sys_columns("Cooling Tower Fan Control", "Condensing Plant", 4)
    ),

    "Domestic Hot Water": (
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
}

# Per-category instructions supplementing the main system prompt
CATEGORY_INSTRUCTIONS = {
    "Ventilation": """Focus on ventilation and air distribution systems (HVAC Sys 1-6).
Describe exhaust systems (bathrooms, corridors, garage, kitchens, other), supply air systems
(common area, corridors, tenant spaces, other), central distribution and delivery equipment types,
demand control ventilation, energy recovery ventilation, fan control, terminal units, thermal zoning,
and outdoor air provisions. There are up to 6 systems; prioritize System 1.""",

    "Controls": """Focus on building controls across all HVAC systems and plants.
Describe direct digital controls, manual thermostat controls, programmable thermostat controls,
pneumatic controls (for HVAC systems, heating plants, and cooling plants), and building automation
system presence. There are up to 6 HVAC systems and up to 4 heating/cooling plants; prioritize
System/Plant 1. Reference the Ventilation narrative for this building.""",

    "Heating": """Focus on heating plants (up to 4) and HVAC system heating components (up to 6).
Describe heating plant types, fuel types, burner types and installation years, number of equipment
pieces, venting types, and heating system types per HVAC system. There are up to 4 heating plants
and 6 HVAC systems; prioritize Plant/System 1. Reference the Ventilation and Controls narratives
for this building.""",

    "Cooling": """Focus on cooling plants (up to 4), HVAC system cooling components (up to 6),
and condensing plants (up to 4). Describe chiller compressor types, condenser types, chilled water
reset, pump controls, fuel types, cooling system types per HVAC system, fan static pressure reset,
and cooling tower fan control. There are up to 4 cooling plants, 6 HVAC systems, and 4 condensing
plants; prioritize Plant/System 1. Reference the Ventilation, Controls, and Heating narratives
for this building.""",

    "Domestic Hot Water": """Focus on service hot water (SHW) systems (up to 6).
Describe SHW system types, hot water plant connections, fuel sources, venting types, equipment
locations, distribution types, tank volumes and insulation, and control types (time-based,
aquastat, demand-based, EMS/BMS). There are up to 6 SHW systems; prioritize System 1.
Reference all preceding system narratives for this building.""",
}


def get_claude_client() -> Anthropic:
    """Get Anthropic client with API key from environment or Streamlit secrets."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment or Streamlit secrets")
    return Anthropic(api_key=api_key)


def _extract_category_data(ll87_raw: Optional[Dict], category: str) -> str:
    """
    Extract relevant equipment data from LL87 raw JSONB for a specific category.

    Uses explicit column name lists from CATEGORY_COLUMNS with case-insensitive fallback.
    """
    if not ll87_raw:
        return "No LL87 audit data was available for this building."

    columns = CATEGORY_COLUMNS.get(category, [])
    if not columns:
        return f"No column mapping defined for {category}."

    # Build case-insensitive lookup of all LL87 fields
    field_lookup = {}
    for key in ll87_raw:
        field_lookup[key.lower().strip()] = key

    found_data = []
    for col_name in columns:
        # Try exact match first, then case-insensitive
        value = ll87_raw.get(col_name)
        if value is None:
            actual_key = field_lookup.get(col_name.lower().strip())
            if actual_key:
                value = ll87_raw[actual_key]

        if value is None or value == "" or value == 0:
            continue

        found_data.append(f"- {col_name}: {value}")

    if found_data:
        return "\n".join(found_data)
    return f"Detailed {category.lower()} specifications were not available in the provided data."


def _extract_all_category_data(ll87_raw: Optional[Dict]) -> Dict[str, str]:
    """Extract equipment data for all 5 narrative categories from LL87 raw JSONB."""
    return {
        category: _extract_category_data(ll87_raw, category)
        for category in NARRATIVE_CATEGORIES
    }


SYSTEM_PROMPT = (
    'You are supporting an engineering consultant by digesting a large database '
    'of information. For each building, you are expected to provide a brief '
    'description of the HVAC systems on site along with general functionality. '
    'This should be in paragraph form, not to exceed 3 paragraphs. Please include '
    'system type, noteworthy equipment within each system along with quantity and '
    'how it is controlled. Please exclude system ratings and capacities. Only '
    'discuss what is present; do not mention systems that are not present. There '
    'may be multiple systems present (for example, "sys 1" and "sys 2"); please '
    'prioritize system 1. Please also reference other system narratives for this '
    'building.\n\n'
    'CRITICAL RULES:\n'
    '1. Include ONLY information explicitly provided in the data\n'
    '2. Do NOT infer system type, configuration, controls, or operation from assumptions\n'
    '3. Do NOT recommend measures, estimate savings, or describe future work\n'
    '4. Use a professional, third-person engineering tone\n'
    '5. Maximum three paragraphs\n'
    '6. If data is missing, state: "Detailed system specifications were not available '
    'in the provided data."\n'
    '7. Exclude system ratings and capacities from the narrative'
)


@backoff.on_exception(backoff.expo, Exception, max_tries=3, jitter=backoff.full_jitter)
def generate_narrative(
    client: Anthropic,
    category: str,
    building_data: Dict[str, Any],
    all_equipment: Optional[Dict[str, str]] = None,
    preceding_narratives: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate a single system narrative using Claude.

    Args:
        client: Anthropic client instance
        category: Narrative category (e.g., "Heating")
        building_data: Building data dict from database
        all_equipment: Pre-extracted equipment data
        preceding_narratives: Completed narratives from earlier categories in this run

    Returns:
        Generated narrative text (1-3 paragraphs)
    """
    if all_equipment is None:
        all_equipment = _extract_all_category_data(building_data.get('ll87_raw'))

    year_built = building_data.get('year_built') or 'Not documented'
    property_type = building_data.get('property_type') or 'Not documented'
    gfa = building_data.get('gfa') or 0
    site_eui = building_data.get('site_eui')
    site_eui_str = f"{site_eui:,.1f} kBtu/sqft" if site_eui else 'Not documented'
    electricity = building_data.get('electricity_kwh') or 0
    natural_gas = building_data.get('natural_gas_kbtu') or 0
    fuel_oil = building_data.get('fuel_oil_kbtu') or 0
    steam = building_data.get('steam_kbtu') or 0

    # Build preceding narratives section
    if preceding_narratives:
        narr_parts = []
        for cat_name, narr_text in preceding_narratives.items():
            if narr_text and not narr_text.startswith("Error"):
                narr_parts.append(f"{cat_name}:\n{narr_text}")
        narratives_section = "\n\n".join(narr_parts) if narr_parts else "No preceding narratives available yet."
    else:
        narratives_section = "No preceding narratives available yet (this is the first narrative)."

    cat_instructions = CATEGORY_INSTRUCTIONS.get(category, '')
    category_data = all_equipment.get(category, 'Not documented')

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

{category.upper()} DATA:
{category_data}

PRECEDING SYSTEM NARRATIVES (completed for this building - reference these):
{narratives_section}

CATEGORY-SPECIFIC INSTRUCTIONS:
{cat_instructions}

Write a 1-3 paragraph narrative about the {category.lower()} system based strictly on the data above. If system data is incomplete or unavailable, use: "Detailed system specifications were not available in the provided data.\""""

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
    Generate all 5 system narratives for a building, sequentially.

    Each narrative receives the completed preceding narratives as context,
    enabling cross-referencing between system descriptions.
    """
    client = get_claude_client()
    narratives = {}
    completed = {}

    all_equipment = _extract_all_category_data(building_data.get('ll87_raw'))

    for category in NARRATIVE_CATEGORIES:
        try:
            narratives[category] = generate_narrative(
                client, category, building_data, all_equipment, completed
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
    all_equipment = _extract_all_category_data(building_data.get('ll87_raw'))
    return generate_narrative(client, category, building_data, all_equipment)
