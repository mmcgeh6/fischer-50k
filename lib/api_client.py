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

    Args:
        ll87_raw: LL87 audit data as dict
        category: Narrative category to extract for

    Returns:
        Formatted equipment description or "No equipment data available"
    """
    if not ll87_raw:
        return "No LL87 audit data available for this building."

    # Map categories to LL87 field paths
    # These field names may vary based on actual LL87 schema
    category_fields = {
        "Building Envelope": ["building_envelope", "envelope", "wall_construction", "roof_construction", "window_type"],
        "Heating System": ["heating_equipment", "boilers", "heat_exchangers", "heating_plants"],
        "Cooling System": ["cooling_equipment", "chillers", "cooling_towers", "chilled_water_plants"],
        "Air Distribution System": ["air_handling_units", "rooftop_units", "packaged_units", "ahu"],
        "Ventilation System": ["ventilation", "makeup_air_units", "doas", "energy_recovery"],
        "Domestic Hot Water System": ["domestic_hot_water", "dhw", "water_heaters"]
    }

    fields_to_check = category_fields.get(category, [])
    found_data = []

    for field in fields_to_check:
        if field in ll87_raw and ll87_raw[field]:
            found_data.append(f"{field}: {ll87_raw[field]}")

    if found_data:
        return "\n".join(found_data)
    return f"No {category.lower()} data documented in LL87 audit."


def generate_narrative(
    client: Anthropic,
    category: str,
    building_data: Dict[str, Any]
) -> str:
    """
    Generate a single system narrative using Claude.

    Args:
        client: Anthropic client instance
        category: Narrative category (e.g., "Heating System")
        building_data: Building data dict from database

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

    # Extract equipment data for this category
    equipment_data = _extract_equipment_data(
        building_data.get('ll87_raw'),
        category
    )

    # Build context from building data (per CLAUDE.md context fields)
    year_built = building_data.get('year_built') or 'Not documented'
    property_type = building_data.get('property_type') or 'Not documented'
    gfa = building_data.get('gfa') or 0
    electricity = building_data.get('electricity_kwh') or 0
    natural_gas = building_data.get('natural_gas_kbtu') or 0
    fuel_oil = building_data.get('fuel_oil_kbtu') or 0
    steam = building_data.get('steam_kbtu') or 0

    user_message = f"""Generate a {category} Narrative for this building.

BUILDING CONTEXT:
- Year Built: {year_built}
- Property Type: {property_type}
- Gross Floor Area: {gfa:,} sqft
- Electricity Use: {electricity:,} kWh
- Natural Gas Use: {natural_gas:,} kBtu
- Fuel Oil #2 Use: {fuel_oil:,} kBtu
- District Steam Use: {steam:,} kBtu

LL87 AUDIT DATA FOR {category.upper()}:
{equipment_data}

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

    for category in NARRATIVE_CATEGORIES:
        try:
            narratives[category] = generate_narrative(client, category, building_data)
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
    return generate_narrative(client, category, building_data)
