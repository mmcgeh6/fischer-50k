# Phase 1: Web UI Foundation - Research

**Researched:** 2026-02-06
**Domain:** Web UI Development (Streamlit + PostgreSQL + Claude API)
**Confidence:** HIGH

## Summary

Phase 1 requires building a simple web interface for manual building data retrieval using Streamlit (Python-native web framework), PostgreSQL/Supabase for database access, and Anthropic Claude API for narrative generation. The research confirms this is a well-established stack with mature patterns.

**Key findings:**
- Streamlit 1.28+ provides native PostgreSQL connection management via `st.connection()` with built-in caching, secrets management, and retry logic
- Anthropic Python SDK (`anthropic` package) offers straightforward integration with environment-based authentication and simple message/response patterns
- The existing codebase uses `psycopg2` directly, which is appropriate for this use case (simple queries, PostgreSQL-specific features)
- Streamlit's reactive model (top-to-bottom script execution on interaction) requires careful session state management to avoid unnecessary reruns

**Primary recommendation:** Use Streamlit's native `st.connection()` for database access (cleaner than raw psycopg2), leverage `st.form()` for BBL input to batch widget interactions, and implement proper loading states with `st.spinner()` during API calls. Structure code with clear separation between UI (main app file) and business logic (separate modules for database queries and API calls).

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Streamlit | >= 1.28 | Web UI framework | Python-native, reactive model, built-in widgets for forms/tables/JSON display. Official PostgreSQL connection support. |
| anthropic | Latest (3.x+) | Claude API client | Official Anthropic SDK, simple Messages API, supports streaming and structured outputs |
| psycopg2-binary | 2.9.x | PostgreSQL adapter | Low-level driver, PostgreSQL-specific features, existing codebase uses it |
| python-dotenv | 1.0.x | Environment variable management | Industry standard for .env file loading, works with Streamlit secrets |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | Latest | Data manipulation | If complex data transformations needed (likely not for Phase 1) |
| SQLAlchemy | 2.0.x | ORM/query builder | Only if complex queries or ORM needed (psycopg2 sufficient for Phase 1) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg2 | SQLAlchemy + st.connection("sql") | More abstraction, but psycopg2 already in use and sufficient for simple queries |
| Streamlit forms | Individual widgets | Forms batch interactions (better UX), prevent partial updates |
| Direct psycopg2 | st.connection() wrapper | st.connection() adds caching/retries/secrets management (recommended upgrade path) |

**Installation:**
```bash
pip install streamlit anthropic psycopg2-binary python-dotenv
```

## Architecture Patterns

### Recommended Project Structure
```
.
├── .streamlit/
│   ├── config.toml           # App theme, server settings
│   └── secrets.toml          # Database credentials, API keys (gitignored)
├── app.py                    # Main Streamlit entry point (UI only)
├── lib/
│   ├── database.py           # Database connection, query functions
│   ├── api_client.py         # Claude API calls for narratives
│   └── validators.py         # BBL validation, data cleaning
├── requirements.txt          # Dependencies
└── .gitignore                # Must include .streamlit/secrets.toml
```

### Pattern 1: Streamlit Database Connection
**What:** Use `st.connection()` for PostgreSQL access with automatic caching and secrets management
**When to use:** All database queries (replaces manual psycopg2 connection management)

**Example:**
```python
# Source: https://docs.streamlit.io/develop/tutorials/databases/postgresql
import streamlit as st

# Connection reads from .streamlit/secrets.toml automatically
conn = st.connection("postgresql", type="sql")

# Query with TTL caching (10 minutes)
df = conn.query('SELECT * FROM ll87_raw WHERE bbl = :bbl;',
                params={"bbl": bbl_input},
                ttl="10m")
```

**Secrets configuration (.streamlit/secrets.toml):**
```toml
[connections.postgresql]
dialect = "postgresql"
host = "aws-0-us-west-2.pooler.supabase.com"
port = "5432"
database = "postgres"
username = "postgres.lhtuvtfqjovfuwuxckcw"
password = "U4Y$A9$x1GBRooAF"
```

### Pattern 2: Form-Based Input
**What:** Use `st.form()` context manager to batch widget interactions
**When to use:** When multiple inputs need to be submitted together (prevents partial state updates)

**Example:**
```python
# Source: Streamlit best practices + official docs
with st.form("bbl_input_form"):
    bbl = st.text_input("Enter BBL (10-digit numeric)",
                        placeholder="1011190036",
                        max_chars=10)
    submitted = st.form_submit_button("Retrieve Building Data")

    if submitted:
        # Validation happens after form submission
        if validate_bbl(bbl):
            # Trigger data retrieval
            fetch_building_data(bbl)
        else:
            st.error("Invalid BBL format. Must be 10 digits (borough, block, lot).")
```

### Pattern 3: Session State Management
**What:** Initialize session state variables before use, avoid overusing for large data
**When to use:** Persisting form state, caching API responses across reruns

**Example:**
```python
# Source: https://docs.streamlit.io/develop/concepts/architecture/session-state
# Initialize at app start
if 'building_data' not in st.session_state:
    st.session_state.building_data = None
if 'narratives' not in st.session_state:
    st.session_state.narratives = {}

# Update in callbacks or conditional blocks
if retrieved_data:
    st.session_state.building_data = retrieved_data
```

### Pattern 4: Loading States with Spinners
**What:** Display spinner during long-running operations (API calls, database queries)
**When to use:** Any operation taking >500ms

**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/status/st.spinner
with st.spinner("Retrieving building data from LL97, LL84, LL87..."):
    building_data = fetch_all_sources(bbl)

with st.spinner("Generating system narratives with Claude..."):
    narratives = generate_narratives(building_data)
```

### Pattern 5: Claude API Integration
**What:** Simple messages API with environment-based authentication
**When to use:** All narrative generation (6 system narratives per building)

**Example:**
```python
# Source: https://github.com/anthropics/anthropic-sdk-python
import os
from anthropic import Anthropic

client = Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")  # or st.secrets["ANTHROPIC_API_KEY"]
)

def generate_narrative(category: str, context_data: dict) -> str:
    """Generate a system narrative using Claude."""
    system_prompt = "You are a mechanical engineering expert writing concise building system narratives."

    user_message = f"""
    Generate a {category} narrative based on this data:
    - Year Built: {context_data['year_built']}
    - Property Type: {context_data['property_type']}
    - GFA: {context_data['gfa']} sqft
    - Equipment: {context_data['equipment']}
    """

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",  # Current Sonnet model
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    return message.content[0].text
```

### Pattern 6: Displaying Structured Data
**What:** Use `st.json()` for expandable JSON, `st.dataframe()` for tabular data
**When to use:** Displaying building fields (JSON for nested data, dataframe for flat tables)

**Example:**
```python
# Source: https://docs.streamlit.io/develop/api-reference/data/st.json
# Display raw LL87 data as expandable JSON
st.subheader("LL87 Audit Data")
st.json(building_data['ll87_raw'], expanded=False)  # Collapsed by default

# Display calculated penalties as table
st.subheader("LL97 Penalty Calculations")
penalty_data = {
    "Period": ["2024-2029", "2030-2034"],
    "GHG Emissions (tCO2e)": [1234.5, 1150.2],
    "Emissions Limit (tCO2e)": [1000.0, 800.0],
    "Annual Penalty": ["$62,846", "$93,854"]
}
st.dataframe(penalty_data)
```

### Anti-Patterns to Avoid
- **Global database connection**: Don't create psycopg2 connection at module level (Streamlit reruns script). Use `st.connection()` or connection inside functions with proper cleanup.
- **Expensive operations outside forms**: Don't trigger API calls or queries on widget change without form wrapper (causes reruns on every keystroke).
- **Session state for large data**: Don't store entire DataFrames in session_state (memory issues). Use `@st.cache_data` instead.
- **Unsafe HTML rendering**: Don't use `unsafe_allow_html=True` unless absolutely necessary (XSS vulnerability).

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database connection pooling | Custom connection manager | `st.connection()` or Supabase pooler (port 5432) | Handles retries, caching, secrets, cleanup automatically |
| Secrets management | Hardcoded credentials or manual .env parsing | `.streamlit/secrets.toml` + `st.secrets` | Native Streamlit integration, works locally and in deployment |
| Input validation | Custom regex for BBL | Simple digit checks + length validation | BBL format is well-defined (10 digits: 1 borough + 5 block + 4 lot) |
| JSON display | Manual HTML formatting | `st.json(data, expanded=False)` | Built-in expand/collapse, tooltips showing full path (2026 feature) |
| Loading indicators | Custom CSS spinners | `st.spinner()` context manager | Native integration, consistent UX |
| API error handling | Try/except everywhere | Anthropic SDK has built-in retries | SDK handles transient failures automatically |

**Key insight:** Streamlit provides high-level abstractions for common web app patterns (forms, connections, caching, state). Use these instead of low-level implementations—they handle edge cases and work across deployment environments.

## Common Pitfalls

### Pitfall 1: Tab Content Executes Immediately
**What goes wrong:** Putting expensive operations in different tabs doesn't defer execution—all tab code runs on every rerun
**Why it happens:** Streamlit's reactive model runs entire script top-to-bottom, tabs are just display wrappers
**How to avoid:** Use session state flags to track which tab is active, only execute expensive operations when tab is selected
**Warning signs:** App slows down even when viewing simple tabs, API calls fire when user hasn't clicked tab yet

**Example solution:**
```python
tab1, tab2 = st.tabs(["Building Data", "Narratives"])

with tab1:
    st.write("Building data content")

with tab2:
    # Only generate narratives when user clicks this tab
    if 'narratives_generated' not in st.session_state:
        if st.button("Generate Narratives"):
            with st.spinner("Generating..."):
                st.session_state.narratives = generate_all_narratives(bbl)
                st.session_state.narratives_generated = True

    if st.session_state.get('narratives_generated'):
        st.json(st.session_state.narratives)
```

### Pitfall 2: Callback Error Handling
**What goes wrong:** Try/except blocks around button callbacks don't catch errors—Streamlit's error handler intercepts them
**Why it happens:** Callbacks execute in Streamlit's event loop before main script runs
**How to avoid:** Put error handling INSIDE callback functions, or use session state to store error messages
**Warning signs:** Uncaught exceptions displayed as red error boxes, try/except doesn't work as expected

**Example solution:**
```python
def retrieve_building_callback():
    try:
        data = fetch_building_data(st.session_state.bbl_input)
        st.session_state.building_data = data
        st.session_state.error = None
    except Exception as e:
        st.session_state.error = str(e)

st.button("Retrieve", on_click=retrieve_building_callback)

if st.session_state.get('error'):
    st.error(st.session_state.error)
```

### Pitfall 3: PostgreSQL Connection Pool Exhaustion
**What goes wrong:** Too many concurrent connections to Supabase, connection errors under load
**Why it happens:** Direct connections (port 5432) have connection limits, need pooler configuration
**How to avoid:** Use Supabase pooler endpoint (aws-0-region.pooler.supabase.com:5432) in transaction mode for serverless or session mode for persistent apps
**Warning signs:** "Too many connections" errors, connection timeouts during peak usage

**Supabase configuration:**
```toml
# For Streamlit (persistent app), use session mode
[connections.postgresql]
host = "aws-0-us-west-2.pooler.supabase.com"  # Pooler endpoint
port = "5432"  # Session mode
```

### Pitfall 4: Session State Persistence Assumptions
**What goes wrong:** Expecting session state to persist after tab close or server restart
**Why it happens:** Session state is memory-based, tied to browser tab connection
**How to avoid:** Never rely on session state for critical data—treat it as temporary cache only
**Warning signs:** Users report "lost data" after tab refresh, development changes lost on Streamlit rerun

### Pitfall 5: BBL Format Inconsistency
**What goes wrong:** Database uses 10-digit numeric BBL (1011190036), but DOF websites expect dashed format (1-01119-0036)
**Why it happens:** Different NYC systems use different BBL formats
**How to avoid:** Store BBL as 10-digit string internally, provide conversion utility for external lookups
**Warning signs:** BBL lookups fail when copied from one system to another

**Conversion utility:**
```python
def bbl_to_dashed(bbl: str) -> str:
    """Convert 10-digit BBL to dashed format (1011190036 -> 1-01119-0036)."""
    if len(bbl) != 10:
        raise ValueError("BBL must be 10 digits")
    return f"{bbl[0]}-{bbl[1:6]}-{bbl[6:]}"

def bbl_from_dashed(dashed: str) -> str:
    """Convert dashed BBL to 10-digit format (1-01119-0036 -> 1011190036)."""
    return dashed.replace("-", "")
```

## Code Examples

Verified patterns from official sources:

### Complete App Structure
```python
# app.py - Main Streamlit application
# Source: Composite from Streamlit docs + Anthropic SDK docs

import streamlit as st
from lib.database import fetch_building_by_bbl
from lib.api_client import generate_all_narratives
from lib.validators import validate_bbl, bbl_to_dashed

# Page configuration
st.set_page_config(
    page_title="Fischer 50K Building Lead Tool",
    layout="wide"
)

# Initialize session state
if 'building_data' not in st.session_state:
    st.session_state.building_data = None
if 'narratives' not in st.session_state:
    st.session_state.narratives = None

# Title
st.title("Building Data Retrieval")
st.markdown("Enter a BBL to retrieve building energy data and system narratives.")

# Input form
with st.form("bbl_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        bbl = st.text_input(
            "BBL (10-digit numeric)",
            placeholder="1011190036",
            max_chars=10,
            help="Borough-Block-Lot identifier (no dashes)"
        )
    with col2:
        st.write("")  # Spacer
        submitted = st.form_submit_button("Retrieve Data", use_container_width=True)

# Process form submission
if submitted:
    if not validate_bbl(bbl):
        st.error("Invalid BBL. Must be 10 digits (1-5 for borough, then block and lot).")
    else:
        # Fetch building data
        with st.spinner("Retrieving building data from LL97, LL84, LL87..."):
            building_data = fetch_building_by_bbl(bbl)

        if not building_data:
            st.warning(f"No data found for BBL {bbl}")
        else:
            st.session_state.building_data = building_data
            st.success(f"Retrieved data for {building_data['address']}")

            # Generate narratives
            with st.spinner("Generating system narratives with Claude..."):
                narratives = generate_all_narratives(building_data)
                st.session_state.narratives = narratives

# Display results
if st.session_state.building_data:
    data = st.session_state.building_data

    # Tabs for different data sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "Building Info",
        "Energy Data",
        "System Narratives",
        "LL97 Penalties"
    ])

    with tab1:
        st.subheader("Building Identity")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("BBL", data['bbl'])
            st.metric("BIN", data.get('bin', 'N/A'))
            st.write(f"**Address:** {data['address']}")
        with col2:
            st.metric("Year Built", data.get('year_built', 'N/A'))
            st.metric("GFA", f"{data.get('gfa', 0):,} sqft")
            st.write(f"**Property Type:** {data.get('property_type', 'N/A')}")

        # LL97 compliance info
        st.subheader("LL97 Compliance")
        st.write(f"**Pathway:** {data.get('compliance_pathway', 'N/A')}")

    with tab2:
        st.subheader("LL84 Energy Benchmarking")
        energy_metrics = st.columns(4)
        energy_metrics[0].metric("Electricity", f"{data.get('electricity_kwh', 0):,} kWh")
        energy_metrics[1].metric("Natural Gas", f"{data.get('natural_gas_kbtu', 0):,} kBtu")
        energy_metrics[2].metric("Fuel Oil #2", f"{data.get('fuel_oil_kbtu', 0):,} kBtu")
        energy_metrics[3].metric("District Steam", f"{data.get('steam_kbtu', 0):,} kBtu")

        st.subheader("LL87 Audit Data")
        if data.get('ll87_raw'):
            st.json(data['ll87_raw'], expanded=False)
        else:
            st.info("No LL87 audit data available for this building")

    with tab3:
        if st.session_state.narratives:
            for category, narrative in st.session_state.narratives.items():
                with st.expander(category, expanded=False):
                    st.write(narrative)
        else:
            st.info("Narratives not generated yet")

    with tab4:
        st.subheader("GHG Emissions & Penalties")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Period 1: 2024-2029**")
            st.metric("GHG Emissions", f"{data.get('ghg_2024_2029', 0):.1f} tCO2e")
            st.metric("Emissions Limit", f"{data.get('limit_2024_2029', 0):.1f} tCO2e")
            st.metric("Annual Penalty", f"${data.get('penalty_2024_2029', 0):,.0f}")

        with col2:
            st.markdown("**Period 2: 2030-2034**")
            st.metric("GHG Emissions", f"{data.get('ghg_2030_2034', 0):.1f} tCO2e")
            st.metric("Emissions Limit", f"{data.get('limit_2030_2034', 0):.1f} tCO2e")
            st.metric("Annual Penalty", f"${data.get('penalty_2030_2034', 0):,.0f}")
```

### Database Module
```python
# lib/database.py
# Source: https://docs.streamlit.io/develop/tutorials/databases/postgresql

import streamlit as st
from typing import Optional, Dict, Any

def get_connection():
    """Get PostgreSQL connection using Streamlit's connection management."""
    return st.connection("postgresql", type="sql")

def fetch_building_by_bbl(bbl: str) -> Optional[Dict[str, Any]]:
    """
    Fetch building data from all sources (LL97, LL84, LL87) for given BBL.
    Returns None if building not found.
    """
    conn = get_connection()

    # Step 1: Get LL97 covered building info (identity, compliance pathway)
    ll97_query = """
        SELECT bbl, bin_preliminary as bin, address_canonical as address,
               compliance_pathway
        FROM ll97_covered_buildings
        WHERE bbl = :bbl
    """
    ll97_data = conn.query(ll97_query, params={"bbl": bbl}, ttl="1h")

    if ll97_data.empty:
        return None

    building = ll97_data.iloc[0].to_dict()

    # Step 2: Get LL84 energy data (deduplicated table)
    ll84_query = """
        SELECT year_built, property_gfa, largest_property_use_type,
               electricity_use_grid_purchase_kwh, natural_gas_use_kbtu,
               fuel_oil_2_use_kbtu, district_steam_use_kbtu,
               ghg_emissions_2024_2029, emissions_limit_2024_2029, penalty_2024_2029,
               ghg_emissions_2030_2034, emissions_limit_2030_2034, penalty_2030_2034
        FROM ll84_data
        WHERE bbl = :bbl
    """
    ll84_data = conn.query(ll84_query, params={"bbl": bbl}, ttl="10m")

    if not ll84_data.empty:
        building.update(ll84_data.iloc[0].to_dict())

    # Step 3: Get LL87 audit data (latest audit from 2019-2024, fallback to 2012-2018)
    ll87_query = """
        SELECT DISTINCT ON (bbl)
               bbl, audit_template_id, reporting_period, raw_data
        FROM ll87_raw
        WHERE bbl = :bbl
        ORDER BY bbl,
                 CASE WHEN reporting_period = '2019-2024' THEN 1 ELSE 2 END,
                 audit_template_id DESC
    """
    ll87_data = conn.query(ll87_query, params={"bbl": bbl}, ttl="1h")

    if not ll87_data.empty:
        building['ll87_raw'] = ll87_data.iloc[0]['raw_data']
        building['ll87_period'] = ll87_data.iloc[0]['reporting_period']

    return building
```

### API Client Module
```python
# lib/api_client.py
# Source: https://github.com/anthropics/anthropic-sdk-python

import os
import streamlit as st
from anthropic import Anthropic
from typing import Dict, Any

# Initialize client (reads from environment or st.secrets)
def get_claude_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    return Anthropic(api_key=api_key)

NARRATIVE_CATEGORIES = [
    "Building Envelope Narrative",
    "Heating System Narrative",
    "Cooling System Narrative",
    "Air Distribution System Narrative",
    "Ventilation System Narrative",
    "Domestic Hot Water System Narrative"
]

def generate_narrative(client: Anthropic, category: str, context: Dict[str, Any]) -> str:
    """Generate a single system narrative using Claude."""

    system_prompt = """You are a mechanical engineering expert writing concise building system narratives for energy audits.
    Write 1-2 paragraphs based ONLY on the provided data. Do not make assumptions about missing data."""

    user_message = f"""
Generate a {category} based on this building data:

Context:
- Year Built: {context.get('year_built', 'Unknown')}
- Property Type: {context.get('largest_property_use_type', 'Unknown')}
- GFA: {context.get('property_gfa', 0):,} sqft
- Site Energy Use: {context.get('site_energy_use_kbtu', 0):,} kBtu
- Fuel Oil #2: {context.get('fuel_oil_2_use_kbtu', 0):,} kBtu
- District Steam: {context.get('district_steam_use_kbtu', 0):,} kBtu
- Natural Gas: {context.get('natural_gas_use_kbtu', 0):,} kBtu
- Electricity: {context.get('electricity_use_grid_purchase_kwh', 0):,} kWh

LL87 Equipment Data:
{context.get('ll87_equipment', 'No equipment data available')}
"""

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
    """Generate all 6 system narratives for a building."""
    client = get_claude_client()
    narratives = {}

    for category in NARRATIVE_CATEGORIES:
        narratives[category] = generate_narrative(client, category, building_data)

    return narratives
```

### Validators Module
```python
# lib/validators.py
# Source: NYC BBL format specification

def validate_bbl(bbl: str) -> bool:
    """
    Validate NYC BBL format (10 digits: 1 borough + 5 block + 4 lot).
    Borough must be 1-5 (Manhattan, Bronx, Brooklyn, Queens, Staten Island).
    """
    if not bbl or len(bbl) != 10:
        return False

    if not bbl.isdigit():
        return False

    borough = int(bbl[0])
    if borough < 1 or borough > 5:
        return False

    return True

def bbl_to_dashed(bbl: str) -> str:
    """Convert 10-digit BBL to dashed format (1011190036 -> 1-01119-0036)."""
    if len(bbl) != 10:
        raise ValueError("BBL must be 10 digits")
    return f"{bbl[0]}-{bbl[1:6]}-{bbl[6:]}"

def bbl_from_dashed(dashed: str) -> str:
    """Convert dashed BBL to 10-digit format (1-01119-0036 -> 1011190036)."""
    return dashed.replace("-", "")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual psycopg2 connection management | `st.connection("postgresql")` | Streamlit 1.28 (2023) | Built-in caching, secrets, retries, cleaner code |
| Try/except for errors in callbacks | Error handling inside callback functions | Long-standing limitation | Must handle errors within callback scope |
| Hardcoded credentials | `.streamlit/secrets.toml` | Native from v1.0 | Secure, works locally and in deployment |
| Manual JSON tree rendering | `st.json(data, expanded=False)` | Enhanced in 2026 | Auto tooltips with full path on hover |
| SQLAlchemy for simple queries | psycopg2-binary directly | Ongoing debate | psycopg2 better for PostgreSQL-specific features, less overhead |
| Anthropic legacy API | Messages API with `anthropic` SDK | Current standard (v3.x) | Cleaner interface, streaming support, structured outputs |

**Deprecated/outdated:**
- **st.cache (decorator)**: Replaced by `@st.cache_data` and `@st.cache_resource` for clearer semantics
- **Manual secrets in code**: Use `.streamlit/secrets.toml` + `st.secrets` dict instead
- **psycopg2 without pooler**: Use Supabase pooler endpoint to avoid connection exhaustion

## Open Questions

Things that couldn't be fully resolved:

1. **LL97 Penalty Calculation Implementation**
   - What we know: Formula is well-defined (3-step calculation), coefficients available in docs
   - What's unclear: Should penalties be pre-calculated in database or computed on-demand in UI?
   - Recommendation: Pre-calculate during data load (ll84_load_supabase.py already does this per CLAUDE.md), display in UI. On-demand calculation only if user wants to experiment with "what-if" scenarios (Phase 2+).

2. **Multiple BINs per BBL Handling**
   - What we know: One BBL can have multiple BINs (campus buildings), LL84 API field can be semicolon-delimited
   - What's unclear: How should UI handle buildings with multiple BINs? Show all? Let user select?
   - Recommendation: Phase 1 shows first BIN only with note "Multiple buildings detected". Full multi-BIN support is Phase 2+ (requires human review workflow per CLAUDE.md).

3. **Narrative Generation Failure Handling**
   - What we know: Claude API can fail (rate limits, timeouts, API errors)
   - What's unclear: Should UI retry automatically? Cache partial results? Show placeholder text?
   - Recommendation: Implement simple retry logic (3 attempts with exponential backoff), store error state in session_state, display friendly error message with "Retry" button. Don't cache failed results.

4. **Streamlit Deployment Environment**
   - What we know: Streamlit Community Cloud exists, also self-hostable
   - What's unclear: Where will this be deployed? Internal server? Cloud?
   - Recommendation: Start with local development, deployment strategy is Phase 2+ decision. Code structure (secrets.toml, st.connection) works in all environments.

## Sources

### Primary (HIGH confidence)
- [Streamlit PostgreSQL Connection Tutorial](https://docs.streamlit.io/develop/tutorials/databases/postgresql) - Connection patterns, caching, secrets
- [Streamlit Session State Documentation](https://docs.streamlit.io/develop/concepts/architecture/session-state) - State management patterns and limitations
- [Anthropic Python SDK GitHub](https://github.com/anthropics/anthropic-sdk-python) - Installation, authentication, message patterns
- [Anthropic Messages API Documentation](https://platform.claude.com/docs/en/api/messages) - Python usage, parameters, response handling
- [Supabase Database Connection Guide](https://supabase.com/docs/guides/database/connecting-to-postgres) - Pooler configuration, connection modes

### Secondary (MEDIUM confidence)
- [Streamlit Best Practices for GenAI Apps](https://blog.streamlit.io/best-practices-for-building-genai-apps-with-streamlit/) - Project structure recommendations
- [Streamlit Secrets Management](https://docs.streamlit.io/develop/concepts/connections/secrets-management) - Secrets configuration patterns
- [Supabase Connection Management](https://supabase.com/docs/guides/database/connection-management) - Pooler modes and limits
- [psycopg2 vs SQLAlchemy comparison](https://www.geeksforgeeks.org/python/difference-between-psycopg2-and-sqlalchemy-in-python/) - When to use each

### Tertiary (LOW confidence - community sources)
- [Streamlit Forum: Project Structure Discussion](https://discuss.streamlit.io/t/project-structure-for-medium-and-large-apps-full-example-ui-and-logic-splitted/59967) - Community patterns for code organization
- [Medium: Streamlit Session State Best Practices](https://medium.com/@jashuamrita360/best-practices-for-streamlit-development-structuring-code-and-managing-session-state-0bdcfb91a745) - Session state usage patterns
- [DigitalDefynd: Streamlit Pros & Cons](https://digitaldefynd.com/IQ/pros-cons-of-streamlit/) - Known limitations and gotchas

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries are official/widely adopted, version compatibility verified
- Architecture: HIGH - Patterns from official Streamlit and Anthropic documentation
- Pitfalls: MEDIUM - Based on official docs + community experience (callback errors, tab execution)
- BBL validation: MEDIUM - Format is well-defined but no official Python library found

**Research date:** 2026-02-06
**Valid until:** 2026-03-06 (30 days - stable domain, Streamlit and Anthropic APIs are mature)
