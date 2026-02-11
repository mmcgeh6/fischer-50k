"""
Claude API client for system narrative generation.

Generates 6 building system narratives using Anthropic Claude:
1. Building Envelope
2. Heating System
3. Cooling System
4. Air Distribution System
5. Ventilation System
6. Domestic Hot Water System

Uses data-only approach per CLAUDE.md — no inferences,
explicit "not documented" fallbacks for missing data.
"""

import os
import streamlit as st
from anthropic import Anthropic
from typing import Dict, Any, Optional
import backoff


# Six narrative categories per CLAUDE.md
NARRATIVE_CATEGORIES = [
    "Building Envelope",
    "Heating System",
    "Cooling System",
    "Air Distribution System",
    "Ventilation System",
    "Domestic Hot Water System"
]


def get_claude_client() -> Anthropic:
    """
    Get Anthropic client with API key from environment or Streamlit secrets.

    Returns:
        Configured Anthropic client

    Raises:
        ValueError: If no API key found
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment or Streamlit secrets")
    return Anthropic(api_key=api_key)


def _extract_equipment_data(ll87_raw: Optional[Dict], category: str) -> str:
    """
    Extract relevant equipment data from LL87 raw JSONB for a specific category.

    Uses keyword-based pattern matching against actual LL87 field names, which
    use formats like "Wall Construction 1", "Heating Plant Type 1",
    "Cooling Plant Type: Cooling Plant 1", "Fan Control: HVAC Sys 1", etc.

    Args:
        ll87_raw: LL87 audit data as dict
        category: Narrative category to extract for

    Returns:
        Formatted equipment description or "No equipment data available"
    """
    if not ll87_raw:
        return "No LL87 audit data available for this building."

    # Map categories to keyword patterns that match actual LL87 field names
    # LL87 uses descriptive names like "Wall Construction 1", "Heating Plant Type 1"
    category_keywords = {
        "Building Envelope": [
            "wall construction", "wall insulation", "roof ", "window ",
            "glass type", "skylight", "foundation", "enclosure tightness",
            "framing material", "demising wall", "exposed above grade",
        ],
        "Heating System": [
            "heating plant", "heating system", "space heating",
            "boiler", "heat exchanger",
        ],
        "Cooling System": [
            "cooling plant", "cooling system", "chiller", "condenser",
            "cooling tower", "chilled water", "space cooling",
        ],
        "Air Distribution System": [
            "hvac sys", "fan control", "air distribution", "air supply",
            "delivery equipment", "central distribution", "thermal zoning",
            "principle hvac type",
        ],
        "Ventilation System": [
            "ventilation", "outdoor air", "air exhaust", "economizer",
        ],
        "Domestic Hot Water System": [
            "shw sys", "shw system", "hot water", "service water heating",
        ],
    }

    keywords = category_keywords.get(category, [])
    found_data = []

    for field_name, value in ll87_raw.items():
        if value is None or value == "" or value == 0:
            continue
        field_lower = field_name.lower()
        for keyword in keywords:
            if keyword in field_lower:
                found_data.append(f"- {field_name}: {value}")
                break

    if found_data:
        return "\n".join(found_data)
    return f"No {category.lower()} data documented in LL87 audit."


def _extract_all_equipment_data(ll87_raw: Optional[Dict]) -> Dict[str, str]:
    """
    Extract ALL equipment data from LL87 raw JSONB, organized by section.

    Returns a dict with keys for each equipment section. Each value is a
    formatted string of matching LL87 fields, or a "not documented" message.
    """
    sections = {
        "Building Automation System": [
            "building automation", "bas ", "controls",
        ],
        "Heating Equipment Specs": [
            "heating plant", "heating system", "space heating",
            "boiler", "heat exchanger", "hot water pump", "zone equip",
        ],
        "Cooling Equipment Specs": [
            "cooling plant", "cooling system", "chiller", "condenser",
            "cooling tower", "chilled water", "space cooling",
        ],
        "Air Distribution Equipment Specs": [
            "hvac sys", "fan control", "air distribution", "air supply",
            "delivery equipment", "central distribution", "thermal zoning",
            "principle hvac type", "air handling", "rooftop unit", "packaged unit",
        ],
        "Ventilation Equipment Specs": [
            "ventilation", "outdoor air", "air exhaust", "economizer",
            "make-up air", "makeup air", "dedicated outdoor air", "energy recovery",
        ],
        "Building Envelope": [
            "wall construction", "wall insulation", "roof ", "window ",
            "glass type", "skylight", "foundation", "enclosure tightness",
            "framing material", "demising wall", "exposed above grade",
        ],
        "Domestic Hot Water": [
            "shw sys", "shw system", "hot water", "service water heating",
        ],
    }

    if not ll87_raw:
        return {name: "No LL87 audit data available." for name in sections}

    result = {}
    for section_name, keywords in sections.items():
        found = []
        for field_name, value in ll87_raw.items():
            if value is None or value == "" or value == 0:
                continue
            field_lower = field_name.lower()
            for kw in keywords:
                if kw in field_lower:
                    found.append(f"- {field_name}: {value}")
                    break
        result[section_name] = "\n".join(found) if found else f"No {section_name.lower()} documented in LL87 audit."

    return result


@backoff.on_exception(backoff.expo, Exception, max_tries=3, jitter=backoff.full_jitter)
def generate_narrative(
    client: Anthropic,
    category: str,
    building_data: Dict[str, Any],
    all_equipment: Optional[Dict[str, str]] = None
) -> str:
    """
    Generate a single system narrative using Claude.

    Args:
        client: Anthropic client instance
        category: Narrative category (e.g., "Heating System")
        building_data: Building data dict from database
        all_equipment: Pre-extracted equipment data from _extract_all_equipment_data()

    Returns:
        Generated narrative text (1-2 paragraphs)
    """
    # System prompt emphasizing data-only approach
    system_prompt = """You are a mechanical engineering expert writing concise building system narratives for energy audits.

CRITICAL RULES:
1. Write 1-2 paragraphs ONLY based on the provided data
2. If specific data is missing, explicitly state "not documented" — do NOT infer or assume
3. Focus on factual descriptions, not recommendations
4. Use professional engineering terminology
5. Be specific about equipment when data is available"""

    # Extract all equipment data if not pre-computed
    if all_equipment is None:
        all_equipment = _extract_all_equipment_data(building_data.get('ll87_raw'))

    # Build context from building data
    year_built = building_data.get('year_built') or 'Not documented'
    property_type = building_data.get('property_type') or 'Not documented'
    gfa = building_data.get('gfa') or 0
    site_eui = building_data.get('site_eui')
    site_eui_str = f"{site_eui:,.1f} kBtu/sqft" if site_eui else 'Not documented'
    electricity = building_data.get('electricity_kwh') or 0
    natural_gas = building_data.get('natural_gas_kbtu') or 0
    fuel_oil = building_data.get('fuel_oil_kbtu') or 0
    steam = building_data.get('steam_kbtu') or 0

    # Collect any existing narratives from building_data (from DB cache)
    narrative_col_map = {
        "Building Envelope": "envelope_narrative",
        "Heating System": "heating_narrative",
        "Cooling System": "cooling_narrative",
        "Air Distribution System": "air_distribution_narrative",
        "Ventilation System": "ventilation_narrative",
        "Domestic Hot Water System": "dhw_narrative",
    }
    existing_narratives = []
    for cat_name, col_name in narrative_col_map.items():
        val = building_data.get(col_name)
        if val:
            existing_narratives.append(f"{cat_name}:\n{val}")
    narratives_section = "\n\n".join(existing_narratives) if existing_narratives else "No previously generated narratives available."

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
{all_equipment.get('Building Automation System', 'Not documented')}

HEATING EQUIPMENT SPECS (Boilers, Heat Exchangers, Hot Water Pumps, Zone Equip):
{all_equipment.get('Heating Equipment Specs', 'Not documented')}

COOLING EQUIPMENT SPECS (Chillers, Chilled Water Pumps, Cooling Towers, Condenser Water Pumps, Heat Exchangers):
{all_equipment.get('Cooling Equipment Specs', 'Not documented')}

AIR DISTRIBUTION EQUIPMENT SPECS (Air Handling Units, Rooftop Units, Packaged Units):
{all_equipment.get('Air Distribution Equipment Specs', 'Not documented')}

VENTILATION EQUIPMENT SPECS (Make-up Air Units, Dedicated Outdoor Air Systems, Energy Recovery Ventilators):
{all_equipment.get('Ventilation Equipment Specs', 'Not documented')}

BUILDING ENVELOPE DATA:
{all_equipment.get('Building Envelope', 'Not documented')}

DOMESTIC HOT WATER DATA:
{all_equipment.get('Domestic Hot Water', 'Not documented')}

EXISTING NARRATIVES:
{narratives_section}

Write a factual 1-2 paragraph narrative about the {category.lower()}. If equipment details are not available, state that the specific systems are not documented in the available audit data."""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system=system_prompt,
        temperature=0.3,  # Low temperature for analytical consistency
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    return message.content[0].text


def generate_all_narratives(building_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generate all 6 system narratives for a building.

    Args:
        building_data: Building data dict from database.fetch_building_by_bbl()

    Returns:
        Dict mapping category name to narrative text

    Raises:
        ValueError: If ANTHROPIC_API_KEY not configured
    """
    client = get_claude_client()
    narratives = {}

    # Extract all equipment data once for reuse across all 6 narratives
    all_equipment = _extract_all_equipment_data(building_data.get('ll87_raw'))

    for category in NARRATIVE_CATEGORIES:
        try:
            narratives[category] = generate_narrative(client, category, building_data, all_equipment)
        except Exception as e:
            # Store error message if narrative generation fails
            narratives[category] = f"Error generating narrative: {str(e)}"

    return narratives


def generate_single_narrative(
    building_data: Dict[str, Any],
    category: str
) -> str:
    """
    Generate a single narrative for testing or selective regeneration.

    Args:
        building_data: Building data dict
        category: One of NARRATIVE_CATEGORIES

    Returns:
        Generated narrative text

    Raises:
        ValueError: If category not in NARRATIVE_CATEGORIES
    """
    if category not in NARRATIVE_CATEGORIES:
        raise ValueError(f"Invalid category. Must be one of: {NARRATIVE_CATEGORIES}")

    client = get_claude_client()
    all_equipment = _extract_all_equipment_data(building_data.get('ll87_raw'))
    return generate_narrative(client, category, building_data, all_equipment)
