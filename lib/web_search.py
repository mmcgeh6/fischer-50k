"""
Web search fallback for building data (Waterfall Step 6).

When primary APIs (LL84, LL87, LL97, PLUTO) return incomplete data,
this module fills gaps using three layers:

  Layer 1: PLUTO Enrichment — extract fields already in _pluto_api_raw (free)
  Layer 2: Firecrawl Scrapers — targeted government site scraping (DOF, DOB BIS, ZoLa, Landmarks GIS)
  Layer 3: Claude Web Search — general web research (replaces manual Gemini gem workflow)

Merge rule: NEVER overwrite data from primary sources (Steps 1-5).
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import backoff
import requests

logger = logging.getLogger(__name__)

# ============================================================================
# Target fields that web search can fill
# ============================================================================

# Critical: fields that trigger web search when missing
CRITICAL_FIELDS = {
    'year_built',
    'property_type',
    'gfa',
    'building_owner',
    'num_floors',
}

# Enrichment: additional fields worth searching for
ENRICHMENT_FIELDS = {
    'landmark_status',
    'num_residential_units',
    'num_elevators',
    'floors_above_grade',
    'floors_below_grade',
    'dof_address',
}

ALL_TARGET_FIELDS = CRITICAL_FIELDS | ENRICHMENT_FIELDS


# ============================================================================
# Helpers
# ============================================================================

def _safe_int(value) -> Optional[int]:
    """Convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _borough_from_bbl(bbl: str) -> str:
    """Get borough name from BBL first digit."""
    boroughs = {
        "1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
        "4": "Queens", "5": "Staten Island"
    }
    return boroughs.get(bbl[0] if bbl else "", "New York City")


def _bbl_parts(bbl: str) -> Tuple[str, str, str]:
    """Split 10-digit BBL into borough, block, lot."""
    return bbl[0], bbl[1:6], bbl[6:]


def _merge_missing(
    accumulator: Dict[str, Any],
    original_result: Dict[str, Any],
    new_data: Dict[str, Any],
):
    """
    Merge new_data into accumulator, NEVER overwriting original_result fields.

    Keys starting with '_' are metadata — always merged.
    """
    for key, value in new_data.items():
        if value is None:
            continue
        if key.startswith('_'):
            if isinstance(value, list):
                accumulator.setdefault(key, []).extend(value)
            else:
                accumulator[key] = value
        elif not original_result.get(key) and not accumulator.get(key):
            accumulator[key] = value


# ============================================================================
# Layer 1: PLUTO Enrichment (FREE — uses already-fetched _pluto_api_raw)
# ============================================================================

def extract_pluto_enrichment(pluto_raw: Optional[Dict]) -> Dict[str, Any]:
    """
    Extract additional fields from PLUTO raw data that the waterfall currently drops.

    PLUTO API returns ~80 fields but the waterfall only uses year_built, gfa,
    address, zip_code. This extracts building_owner, num_floors,
    num_residential_units, and landmark_status for free.
    """
    if not pluto_raw or not isinstance(pluto_raw, dict):
        return {}

    result = {}

    owner = pluto_raw.get('ownername')
    if owner and str(owner).strip():
        result['building_owner'] = str(owner).strip()

    num_floors = pluto_raw.get('numfloors')
    val = _safe_int(num_floors)
    if val and val > 0:
        result['num_floors'] = val

    units_res = pluto_raw.get('unitsres')
    val = _safe_int(units_res)
    if val and val > 0:
        result['num_residential_units'] = val

    # Landmark from PLUTO histdist or landmark fields
    hist_dist = pluto_raw.get('histdist')
    if hist_dist and str(hist_dist).strip():
        result['landmark_status'] = f"Historic District: {hist_dist.strip()}"

    return result


# ============================================================================
# Layer 2: Firecrawl Scrapers (government websites)
# ============================================================================

def _get_firecrawl_client():
    """Get Firecrawl client from env or Streamlit secrets."""
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("FIRECRAWL_API_KEY")
        except Exception:
            pass

    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY not available")

    from firecrawl import Firecrawl
    return Firecrawl(api_key=api_key)


@backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=30,
                      jitter=backoff.full_jitter)
def scrape_landmarks_gis(bbl: str) -> Dict[str, Any]:
    """
    Query NYC Landmarks Preservation Commission ArcGIS REST API.

    This is a free REST endpoint — no Firecrawl needed.
    """
    url = ("https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
           "NYCLPC_LPC_Report/FeatureServer/0/query")

    params = {
        'where': f"BBL='{bbl}'",
        'outFields': '*',
        'f': 'json',
        'returnGeometry': 'false',
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        features = data.get('features', [])
        if features:
            attrs = features[0].get('attributes', {})
            lpc_type = attrs.get('LPC_TYPE', '') or ''
            designation = attrs.get('LPC_DESIG', '') or ''
            status = f"{lpc_type}: {designation}".strip(': ')
            logger.info(f"Landmarks GIS: BBL {bbl} → {status}")
            return {'landmark_status': status if status else 'Listed'}

        logger.info(f"Landmarks GIS: BBL {bbl} not landmarked")
        return {'landmark_status': 'Not landmarked'}

    except Exception as e:
        logger.warning(f"Landmarks GIS query failed for BBL {bbl}: {e}")
        return {}


@backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=45,
                      jitter=backoff.full_jitter)
def scrape_dob_bis(bbl: str, bin_number: Optional[str] = None) -> Dict[str, Any]:
    """
    Scrape DOB Building Information Search for floor counts and elevators.

    Uses Firecrawl with JSON extraction schema.
    """
    boro, block, lot = _bbl_parts(bbl)

    url = (f"http://a810-bisweb.nyc.gov/bisweb/PropertyBrowseByBBLServlet"
           f"?allborough={boro}&allblock={block}&alllot={lot}")

    app = _get_firecrawl_client()
    result = app.scrape(
        url,
        formats=[{
            "type": "json",
            "schema": {
                "type": "object",
                "properties": {
                    "num_stories": {"type": "integer",
                                    "description": "Number of stories/floors in the building"},
                    "num_elevators": {"type": "integer",
                                      "description": "Number of passenger and freight elevators"},
                    "building_class": {"type": "string",
                                       "description": "DOB building class code"},
                },
            },
            "prompt": (f"Extract building information for this NYC DOB BIS property page. "
                       f"Look for number of stories, number of elevators, and building class."),
        }],
    )

    extracted = result.json if hasattr(result, 'json') and result.json else {}
    mapped = {}

    stories = _safe_int(extracted.get('num_stories'))
    if stories and stories > 0:
        mapped['num_floors'] = stories

    elevators = _safe_int(extracted.get('num_elevators'))
    if elevators and elevators > 0:
        mapped['num_elevators'] = elevators

    if mapped:
        logger.info(f"DOB BIS: BBL {bbl} → {mapped}")
    return mapped


@backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=45,
                      jitter=backoff.full_jitter)
def scrape_dof_by_bbl(bbl: str) -> Dict[str, Any]:
    """
    Scrape NYC Department of Finance property page for owner and address.

    Uses Firecrawl with JSON extraction schema.
    """
    boro, block, lot = _bbl_parts(bbl)
    dashed_bbl = f"{boro}-{block}-{lot}"

    url = (f"https://a836-pts-access.nyc.gov/care/search/commonsearch.aspx"
           f"?mode=persprop")

    app = _get_firecrawl_client()
    result = app.scrape(
        url,
        formats=[{
            "type": "json",
            "schema": {
                "type": "object",
                "properties": {
                    "owner_name": {"type": "string",
                                   "description": "Property owner name"},
                    "property_address": {"type": "string",
                                         "description": "DOF property address"},
                    "year_built": {"type": "integer",
                                   "description": "Year the building was built"},
                    "gross_sqft": {"type": "number",
                                   "description": "Gross square footage of the building"},
                    "total_units": {"type": "integer",
                                    "description": "Total number of units"},
                },
            },
            "prompt": (f"Extract property information for BBL {dashed_bbl} from this "
                       f"NYC Department of Finance property page. Find the owner name, "
                       f"property address, year built, gross square footage, and total units."),
        }],
        actions=[
            {"type": "wait", "milliseconds": 2000},
        ],
    )

    extracted = result.json if hasattr(result, 'json') and result.json else {}
    mapped = {}

    owner = extracted.get('owner_name')
    if owner and str(owner).strip():
        mapped['building_owner'] = str(owner).strip()

    addr = extracted.get('property_address')
    if addr and str(addr).strip():
        mapped['dof_address'] = str(addr).strip()

    yr = _safe_int(extracted.get('year_built'))
    if yr and 1700 < yr < 2030:
        mapped['year_built'] = yr

    sqft = _safe_float(extracted.get('gross_sqft'))
    if sqft and sqft > 0:
        mapped['gfa'] = sqft

    units = _safe_int(extracted.get('total_units'))
    if units and units > 0:
        mapped['num_residential_units'] = units

    if mapped:
        logger.info(f"DOF: BBL {bbl} → {list(mapped.keys())}")
    return mapped


@backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=45,
                      jitter=backoff.full_jitter)
def scrape_zola_gis(bbl: str) -> Dict[str, Any]:
    """
    Scrape NYC ZoLa (Zoning and Land Use Application) for building data.

    Uses Firecrawl with JSON extraction schema.
    """
    boro, block, lot = _bbl_parts(bbl)
    # ZoLa URLs use stripped block/lot (no leading zeros)
    block_stripped = block.lstrip('0') or '0'
    lot_stripped = lot.lstrip('0') or '0'

    url = f"https://zola.planning.nyc.gov/lot/{boro}/{block_stripped}/{lot_stripped}"

    app = _get_firecrawl_client()
    result = app.scrape(
        url,
        formats=[{
            "type": "json",
            "schema": {
                "type": "object",
                "properties": {
                    "year_built": {"type": "integer",
                                   "description": "Year the building was constructed"},
                    "num_floors": {"type": "integer",
                                   "description": "Number of floors/stories"},
                    "building_class": {"type": "string",
                                       "description": "Building class description"},
                    "land_use": {"type": "string",
                                 "description": "Primary land use category"},
                    "residential_units": {"type": "integer",
                                          "description": "Number of residential units"},
                },
            },
            "prompt": ("Extract building information from this NYC ZoLa page. "
                       "Find year built, number of floors, building class, "
                       "land use, and residential units."),
        }],
        actions=[
            {"type": "wait", "milliseconds": 3000},
        ],
    )

    extracted = result.json if hasattr(result, 'json') and result.json else {}
    mapped = {}

    yr = _safe_int(extracted.get('year_built'))
    if yr and 1700 < yr < 2030:
        mapped['year_built'] = yr

    floors = _safe_int(extracted.get('num_floors'))
    if floors and floors > 0:
        mapped['num_floors'] = floors

    units = _safe_int(extracted.get('residential_units'))
    if units and units > 0:
        mapped['num_residential_units'] = units

    land_use = extracted.get('land_use')
    if land_use and str(land_use).strip():
        mapped['property_type'] = str(land_use).strip()

    if mapped:
        logger.info(f"ZoLa: BBL {bbl} → {list(mapped.keys())}")
    return mapped


# ============================================================================
# Layer 3: Claude Web Search (Gemini gem replacement)
# ============================================================================

@backoff.on_exception(backoff.expo, Exception, max_tries=2, max_time=60,
                      jitter=backoff.full_jitter)
def claude_building_research(
    bbl: str,
    address: str,
    known_data: Dict[str, Any],
    missing_fields: List[str],
) -> Dict[str, Any]:
    """
    Use Claude's web search tool to research building information.

    Replaces the Google Gemini custom gem workflow. Claude searches the web
    for building-specific data and returns structured JSON.
    """
    from lib.api_client import get_claude_client

    client = get_claude_client()

    # Build context about what we already know
    known_lines = []
    if known_data.get('building_name'):
        known_lines.append(f"Building Name: {known_data['building_name']}")
    if known_data.get('year_built'):
        known_lines.append(f"Year Built: {known_data['year_built']}")
    if known_data.get('property_type'):
        known_lines.append(f"Use Type: {known_data['property_type']}")
    if known_data.get('gfa'):
        known_lines.append(f"GFA: {known_data['gfa']:,.0f} sqft")
    if known_data.get('num_floors'):
        known_lines.append(f"Floors: {known_data['num_floors']}")
    if known_data.get('building_owner'):
        known_lines.append(f"Owner: {known_data['building_owner']}")

    known_str = "\n".join(known_lines) if known_lines else "Very little is known about this building."
    missing_str = ", ".join(missing_fields)
    borough = _borough_from_bbl(bbl)
    boro, block, lot = _bbl_parts(bbl)
    dashed_bbl = f"{boro}-{block}-{lot}"

    system_prompt = """You are a building research assistant for Fischer Energy Partners, \
an engineering firm that performs energy audits on NYC buildings.

Your job is to research building characteristics using web search.
Return ONLY factual data you can verify from search results.
Do NOT guess or estimate. If you cannot find a specific piece of data, \
set its value to null.

Return your findings as a JSON object with these possible keys:
- building_name: string (commonly known name of the building)
- year_built: integer (year the building was constructed)
- property_type: string (primary use type, e.g. "Office", "Multifamily Housing")
- gfa: number (gross floor area in square feet)
- building_owner: string (current property owner or management company)
- num_floors: integer (total number of floors including below grade)
- floors_above_grade: integer (floors above ground level)
- floors_below_grade: integer (basement/cellar levels)
- num_elevators: integer (total elevators)
- num_residential_units: integer (residential units/apartments)
- landmark_status: string (individual landmark, historic district, or not landmarked)

Only include fields where you found verifiable data.
Wrap the JSON in ```json``` markers."""

    user_message = f"""Research this NYC building and find the following missing data:

BUILDING IDENTITY:
- BBL: {bbl} (DOF format: {dashed_bbl})
- Address: {address}
- Borough: {borough}

WHAT WE ALREADY KNOW:
{known_str}

FIELDS STILL NEEDED:
{missing_str}

Search for this building on NYC property databases, real estate sites, \
Wikipedia, and building directories. Focus specifically on the missing fields listed above."""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=system_prompt,
        temperature=0,
        tools=[{
            "name": "web_search",
            "type": "web_search_20250305",
            "max_uses": 5,
        }],
        messages=[{"role": "user", "content": user_message}],
    )

    # Parse response — Claude interleaves text blocks with web_search_tool_result
    # blocks.  Only the LAST text block contains the JSON answer; earlier ones
    # are reasoning/narrative that can't be parsed.
    result_data = {}
    text_blocks: list[str] = []
    search_urls = []
    searches_used = 0

    if hasattr(message, 'usage') and hasattr(message.usage, 'server_tool_use'):
        if message.usage.server_tool_use:
            searches_used = getattr(message.usage.server_tool_use,
                                    'web_search_requests', 0)

    for block in message.content:
        if block.type == "text":
            text_blocks.append(block.text)
        elif block.type == "web_search_tool_result":
            for item in block.content:
                if hasattr(item, 'url'):
                    search_urls.append({
                        'url': item.url,
                        'title': getattr(item, 'title', ''),
                    })

    # Try text blocks in reverse order (last block most likely has JSON)
    reversed_blocks = list(reversed(text_blocks))
    for i, txt in enumerate(reversed_blocks):
        is_last_attempt = (i == len(reversed_blocks) - 1)
        result_data = _parse_json_from_text(txt, warn_on_failure=is_last_attempt)
        if result_data:
            break

    # Type-coerce and clean results
    cleaned = _clean_search_results(result_data, missing_fields)

    # Add audit metadata
    cleaned['_web_search_metadata'] = {
        'source': 'claude_web_search',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'search_urls': search_urls[:10],
        'fields_found': [k for k in cleaned if not k.startswith('_')],
        'searches_used': searches_used,
    }

    logger.info(f"Claude web search for BBL {bbl}: found "
                f"{len(cleaned) - 1} fields, used {searches_used} searches")
    return cleaned


def _parse_json_from_text(text: str, warn_on_failure: bool = False) -> Dict[str, Any]:
    """Extract JSON from Claude's text response (may be wrapped in markdown).

    Returns empty dict if no valid JSON found.  Set warn_on_failure=True to
    log a warning (used only for the final attempt so intermediate narrative
    blocks don't spam the log).
    """
    json_str = text.strip()

    # Try markdown code block extraction
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        parts = json_str.split("```")
        if len(parts) >= 3:
            json_str = parts[1].strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object anywhere in the text
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    if warn_on_failure:
        logger.warning(f"Failed to parse web search response as JSON: {text[:200]}")
    return {}


def _clean_search_results(
    raw_data: Dict[str, Any],
    target_fields: List[str],
) -> Dict[str, Any]:
    """Type-coerce and validate web search results."""
    cleaned = {}

    int_fields = {'year_built', 'num_floors', 'floors_above_grade',
                  'floors_below_grade', 'num_elevators', 'num_residential_units'}
    float_fields = {'gfa'}
    str_fields = {'building_name', 'building_owner', 'property_type',
                  'landmark_status', 'dof_address'}

    for key, value in raw_data.items():
        if key not in ALL_TARGET_FIELDS and key not in {'building_name'}:
            continue
        if value is None or str(value).lower() in ('not found', 'unknown', 'n/a', 'null', ''):
            continue

        if key in int_fields:
            val = _safe_int(value)
            if val is not None and val > 0:
                if key == 'year_built' and not (1700 < val < 2030):
                    continue
                cleaned[key] = val
        elif key in float_fields:
            val = _safe_float(value)
            if val is not None and val > 0:
                cleaned[key] = val
        elif key in str_fields:
            val = str(value).strip()
            if val:
                cleaned[key] = val

    return cleaned


# ============================================================================
# Orchestrator
# ============================================================================

def run_web_search_fallback(
    bbl: str,
    result: Dict[str, Any],
    skip_firecrawl: bool = False,
    skip_claude_search: bool = False,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Execute web search fallback pipeline (Step 6).

    Sequence:
    1. Extract PLUTO enrichment (free, instant)
    2. Determine which fields are still missing
    3. Run Firecrawl scrapers for specific government sites
    4. Determine remaining gaps
    5. Run Claude web search for anything still missing
    6. Return merged results + new data sources

    Never overwrites data from primary API sources (Steps 1-5).

    Returns:
        Tuple of (new_fields_dict, new_data_sources_list)
    """
    new_fields: Dict[str, Any] = {}
    new_sources: List[str] = []
    address = result.get('address', '')
    bin_number = result.get('bin')

    # ------------------------------------------------------------------
    # Phase A: PLUTO Enrichment (always runs, free)
    # ------------------------------------------------------------------
    pluto_raw = result.get('_pluto_api_raw')
    if pluto_raw:
        pluto_extras = extract_pluto_enrichment(pluto_raw)
        if pluto_extras:
            _merge_missing(new_fields, result, pluto_extras)
            new_sources.append('pluto_enriched')
            logger.info(f"Step 6A: PLUTO enrichment found "
                        f"{len(pluto_extras)} fields: {list(pluto_extras.keys())}")

    # ------------------------------------------------------------------
    # Phase B: Check which fields are still missing
    # ------------------------------------------------------------------
    def _still_missing() -> List[str]:
        return [f for f in ALL_TARGET_FIELDS
                if not result.get(f) and not new_fields.get(f)]

    missing = _still_missing()
    if not missing:
        logger.info("Step 6: All target fields populated, skipping web search")
        return new_fields, new_sources

    logger.info(f"Step 6B: {len(missing)} fields still missing: {missing}")

    # ------------------------------------------------------------------
    # Phase C: Firecrawl scrapers (targeted government sites)
    # ------------------------------------------------------------------
    if not skip_firecrawl:

        # C1: Landmarks GIS (REST API, no Firecrawl needed, free)
        if 'landmark_status' in missing:
            try:
                landmarks_data = scrape_landmarks_gis(bbl)
                if landmarks_data:
                    _merge_missing(new_fields, result, landmarks_data)
                    new_sources.append('landmarks_gis')
            except Exception as e:
                logger.warning(f"Step 6C1: Landmarks GIS failed: {e}")

        # C2: DOB BIS (floors, elevators)
        dob_fields = {'num_floors', 'floors_above_grade', 'floors_below_grade',
                      'num_elevators'}
        if dob_fields & set(missing):
            try:
                dob_data = scrape_dob_bis(bbl, bin_number)
                if dob_data:
                    _merge_missing(new_fields, result, dob_data)
                    new_sources.append('dob_bis')
            except Exception as e:
                logger.warning(f"Step 6C2: DOB BIS scrape failed: {e}")

        # C3: DOF (owner, address)
        dof_fields = {'building_owner', 'dof_address'}
        if dof_fields & set(missing):
            try:
                dof_data = scrape_dof_by_bbl(bbl)
                if dof_data:
                    _merge_missing(new_fields, result, dof_data)
                    new_sources.append('dof')
            except Exception as e:
                logger.warning(f"Step 6C3: DOF scrape failed: {e}")

        # C4: ZoLa GIS (year_built, floors, use type, units)
        zola_fields = {'year_built', 'num_floors', 'property_type',
                       'num_residential_units'}
        if zola_fields & set(missing):
            try:
                zola_data = scrape_zola_gis(bbl)
                if zola_data:
                    _merge_missing(new_fields, result, zola_data)
                    new_sources.append('zola_gis')
            except Exception as e:
                logger.warning(f"Step 6C4: ZoLa GIS scrape failed: {e}")

    # ------------------------------------------------------------------
    # Phase D: Recalculate remaining gaps after Firecrawl
    # ------------------------------------------------------------------
    still_missing = _still_missing()

    # ------------------------------------------------------------------
    # Phase E: Claude Web Search (general research for remaining gaps)
    # ------------------------------------------------------------------
    if still_missing and not skip_claude_search:
        logger.info(f"Step 6E: {len(still_missing)} fields still missing after "
                    f"Firecrawl, running Claude web search: {still_missing}")
        try:
            merged_known = {**result, **new_fields}
            claude_data = claude_building_research(
                bbl, address, merged_known, still_missing
            )
            if claude_data:
                _merge_missing(new_fields, result, claude_data)
                new_sources.append('claude_web_search')
        except Exception as e:
            logger.warning(f"Step 6E: Claude web search failed: {e}")

    final_found = {k: v for k, v in new_fields.items() if not k.startswith('_')}
    logger.info(f"Step 6 complete: found {len(final_found)} new fields "
                f"from {new_sources}")

    return new_fields, new_sources
