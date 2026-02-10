# Phase 3: Calculations & Narratives - Research

**Researched:** 2026-02-10
**Domain:** Carbon emissions calculations, AI narrative generation with Anthropic Claude
**Confidence:** HIGH

## Summary

Phase 3 implements two distinct but complementary systems: (1) LL97 penalty calculations using Python's Decimal library for precise financial arithmetic, and (2) AI-generated system narratives using Anthropic's Python SDK. The phase builds on Phase 2's waterfall data retrieval.

The LL97 penalty calculator is a pure calculation engine implementing a three-step formula (GHG emissions → emissions limits → penalty projection) with period-specific carbon coefficients and emissions factors for 57 building use types. Python's Decimal library is the standard for financial calculations requiring precision, avoiding float representation errors that could compound across thousands of buildings.

The narrative generation system uses Anthropic's Claude via the official Python SDK (`anthropic` library). The existing codebase already implements narrative generation in `lib/api_client.py` with temperature=0.3 for factual consistency and explicit "not documented" fallbacks per the data-only approach. The key architectural pattern is per-narrative error handling — one narrative failure doesn't break the batch.

**Primary recommendation:** Use Python's Decimal library for all penalty calculations with string initialization to prevent precision loss. Use existing `anthropic` SDK with temperature 0.2-0.3 for factual narratives. Store calculation results and narratives as new columns in building_metrics table via dynamic upsert pattern.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | Latest (pip) | Claude API client | Official Anthropic SDK, type-safe, async support |
| decimal | stdlib | Precise financial calculations | Python standard library, prevents float precision errors |
| psycopg2 | 2.9+ | PostgreSQL database client | Direct SQL access for batch processing (already in use) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| backoff | Latest (pip) | Retry with exponential backoff | API call resilience for narrative generation |
| pydantic | 2.x | Structured output validation | Optional - if validating calculation results structurally |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| anthropic SDK | OpenAI GPT-4 | Claude specifically chosen per STATE.md team preference |
| Decimal | float | Float 3x faster but has precision errors (0.1+0.1+0.1 != 0.3) |
| Direct API calls | LangChain/LlamaIndex | Adds complexity, project only needs simple message API |

**Installation:**
```bash
pip install anthropic backoff
# decimal and psycopg2 already installed
```

## Architecture Patterns

### Recommended Project Structure
```
lib/
├── calculations.py      # LL97 penalty calculator (new)
├── narratives.py        # Refactor from api_client.py (optional)
├── api_client.py        # Existing narrative generation (keep)
├── storage.py           # Extend with calculation columns
└── waterfall.py         # Orchestrate Steps 4-5 (extend)
```

### Pattern 1: Decimal-Based Calculation Engine
**What:** Pure Python calculation module using Decimal for all monetary and emissions values
**When to use:** All LL97 penalty calculations to prevent precision loss
**Example:**
```python
from decimal import Decimal, ROUND_HALF_UP

def calculate_ghg_emissions(
    electricity_kwh: float,
    natural_gas_kbtu: float,
    fuel_oil_kbtu: float,
    steam_kbtu: float,
    period: str  # "2024-2029" or "2030-2034"
) -> Decimal:
    """Calculate GHG emissions for a compliance period using Decimal precision."""

    # Period-specific carbon coefficients (tCO2e per unit)
    coefficients = {
        "2024-2029": {
            "electricity": Decimal("0.000288962"),  # tCO2e/kWh
            "natural_gas": Decimal("0.00005311"),   # tCO2e/kBtu
            "fuel_oil": Decimal("0.00007421"),      # tCO2e/kBtu
            "steam": Decimal("0.00004493")          # tCO2e/kBtu
        },
        "2030-2034": {
            "electricity": Decimal("0.000145"),
            "natural_gas": Decimal("0.00005311"),
            "fuel_oil": Decimal("0.00007421"),
            "steam": Decimal("0.0000432")
        }
    }

    coef = coefficients[period]

    # Convert floats to Decimal using string to preserve precision
    elec = Decimal(str(electricity_kwh)) * coef["electricity"]
    gas = Decimal(str(natural_gas_kbtu)) * coef["natural_gas"]
    oil = Decimal(str(fuel_oil_kbtu)) * coef["fuel_oil"]
    stm = Decimal(str(steam_kbtu)) * coef["steam"]

    total_emissions = elec + gas + oil + stm

    # Round to 2 decimal places for tCO2e
    return total_emissions.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

### Pattern 2: Use-Type Emissions Factor Lookup
**What:** Dictionary-based lookup for 57 use-type emissions factors with period-specific values
**When to use:** Step 2 of penalty calculation (emissions limits)
**Example:**
```python
# Emissions factors by use type (tCO2e per sqft)
EMISSIONS_FACTORS = {
    "2024-2029": {
        "adult_education": Decimal("0.00758"),
        "ambulatory_surgical_center": Decimal("0.01181"),
        "automobile_dealership": Decimal("0.00675"),
        # ... 54 more use types
    },
    "2030-2034": {
        "adult_education": Decimal("0.003565528"),
        "ambulatory_surgical_center": Decimal("0.008980612"),
        # ... 54 more use types
    }
}

def calculate_emissions_limit(use_type_sqft: Dict[str, float], period: str) -> Decimal:
    """Calculate building emissions limit from use-type square footages."""
    factors = EMISSIONS_FACTORS[period]
    limit = Decimal("0")

    for use_type, sqft in use_type_sqft.items():
        if sqft and use_type in factors:
            sqft_decimal = Decimal(str(sqft))
            limit += sqft_decimal * factors[use_type]

    return limit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

### Pattern 3: Per-Narrative Error Isolation
**What:** Generate all 6 narratives with try/except per narrative, store error messages for failed ones
**When to use:** Batch narrative generation where partial success is acceptable
**Example:**
```python
# Source: Existing lib/api_client.py implementation (verified pattern)
def generate_all_narratives(building_data: Dict[str, Any]) -> Dict[str, str]:
    """Generate all 6 system narratives with per-narrative error handling."""
    client = get_claude_client()
    narratives = {}

    for category in NARRATIVE_CATEGORIES:
        try:
            narratives[category] = generate_narrative(client, category, building_data)
        except Exception as e:
            # Store error message - one failure doesn't break entire batch
            narratives[category] = f"Error generating narrative: {str(e)}"

    return narratives
```

### Pattern 4: Dynamic Upsert for Incremental Columns
**What:** Storage upsert accepts partial dicts, only updates provided columns
**When to use:** Adding calculation/narrative results to existing building_metrics rows
**Example:**
```python
# Source: Existing lib/storage.py pattern (verified)
# Waterfall Step 4: Add penalty calculations
penalty_data = {
    'bbl': bbl,
    'ghg_emissions_2024_2029': Decimal("123.45"),
    'emissions_limit_2024_2029': Decimal("100.00"),
    'penalty_2024_2029': Decimal("6279.60")  # (123.45 - 100.00) * 268
}
upsert_building_metrics(penalty_data)  # Only updates these 4 columns

# Waterfall Step 5: Add narratives
narrative_data = {
    'bbl': bbl,
    'envelope_narrative': "The building envelope consists of...",
    'heating_narrative': "Heating systems are not documented..."
}
upsert_building_metrics(narrative_data)  # Only updates these 3 columns
```

### Pattern 5: Anthropic SDK with Low Temperature
**What:** Use official anthropic SDK with temperature 0.2-0.3 for factual content
**When to use:** All narrative generation requiring consistency and minimal creativity
**Example:**
```python
# Source: Verified from official Anthropic SDK documentation
from anthropic import Anthropic

client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment

message = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    system="You are a mechanical engineering expert...",
    temperature=0.3,  # Low temp for factual consistency (range: 0.0-1.0)
    messages=[{"role": "user", "content": "Generate narrative..."}]
)

narrative_text = message.content[0].text
```

### Anti-Patterns to Avoid
- **Float arithmetic for money:** Using float for penalty calculations causes precision errors (0.1+0.1+0.1 != 0.3). Always use Decimal with string initialization.
- **Single try/except for all narratives:** If one narrative fails, entire batch fails. Use per-narrative error handling.
- **Hardcoded API keys:** Never hardcode ANTHROPIC_API_KEY. Use environment variables or Streamlit secrets.
- **High temperature for factual content:** Temperature > 0.5 introduces creativity and inconsistency. Use 0.2-0.3 for technical narratives.
- **Decimal(float_value):** This inherits float imprecision. Always use Decimal(str(float_value)).

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API retry logic | Custom retry loops with sleep | backoff library with @backoff.on_exception decorator | Handles exponential backoff, jitter, max retries correctly |
| Float precision | Custom rounding/formatting | Python's Decimal with quantize() | Float binary representation can't represent 0.1 exactly |
| Emissions factor lookup | Nested if/elif chains | Dictionary with period-keyed nested dicts | Maintainable, supports 57 use types x 2 periods |
| Structured AI output | Parse text with regex | Pydantic AI or structured output features | Built-in validation, type safety (if needed beyond text) |
| Database connection pooling | Manual connection reuse | psycopg2.pool or existing storage.py pattern | Prevents connection leaks, handles concurrency |

**Key insight:** Financial calculations and AI API reliability are solved problems. Use Decimal for money, backoff for retries, official SDKs for APIs.

## Common Pitfalls

### Pitfall 1: Float Precision Loss in Calculations
**What goes wrong:** Using Python floats for penalty calculations causes rounding errors that compound across 50,000 buildings
**Why it happens:** Binary floating point can't represent decimal values exactly (0.1 + 0.1 + 0.1 = 0.30000000000000004)
**How to avoid:**
- Use Decimal for all monetary and emissions values
- Initialize Decimal with strings: `Decimal("0.1")` not `Decimal(0.1)`
- Use quantize() for consistent rounding: `value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`
**Warning signs:** Penalty values with unexpected precision (e.g., $6279.599999999999 instead of $6279.60)

### Pitfall 2: Missing Use-Type Data Breaking Calculation
**What goes wrong:** Building has no use-type square footage data, emissions limit calculation crashes or returns zero incorrectly
**Why it happens:** Not all buildings have complete LL84 use-type data; some use types have emissions factors but no LL84 column
**How to avoid:**
- Check if use_type_sqft dict has any non-zero values before calculating
- Return None or "Insufficient data" instead of $0 penalty when inputs are missing
- Log which buildings lack use-type data for manual review
**Warning signs:** Many buildings showing $0 penalty when they should have penalties

### Pitfall 3: API Rate Limiting Breaking Batch Processing
**What goes wrong:** Anthropic API rate limits hit during batch narrative generation, causing failures or timeouts
**Why it happens:** No exponential backoff or retry logic for transient API failures
**How to avoid:**
- Use backoff library: `@backoff.on_exception(backoff.expo, anthropic.RateLimitError, max_tries=3)`
- Add delay between narrative API calls in batch mode (e.g., time.sleep(0.5))
- Store API errors as narrative text instead of crashing: `f"Error: {str(e)}"`
**Warning signs:** Intermittent narrative generation failures, "Rate limit exceeded" in logs

### Pitfall 4: None Values in Database Breaking Format Strings
**What goes wrong:** Waterfall returns `{'electricity_kwh': None}` instead of missing key, causing format string crashes
**Why it happens:** LL84 API can return explicit None for fields; `.get(key, 0)` doesn't protect against this
**How to avoid:**
- Use `value or 0` pattern: `electricity = building_data.get('electricity_kwh') or 0`
- Validate inputs before calculation: check if all required fields are non-None
- Already fixed in Phase 2 per MEMORY.md, but watch for new calculation fields
**Warning signs:** KeyError or formatting errors when building data is incomplete

### Pitfall 5: Narrative Generation Timeout for Large Batches
**What goes wrong:** Generating 6 narratives × 50,000 buildings = 300,000 API calls takes days or times out
**Why it happens:** Synchronous generation with no batching or async processing
**How to avoid:**
- For Phase 3: Focus on single-building flow, batch optimization is Phase 5
- Use async Anthropic client (AsyncAnthropic) for concurrent requests when ready
- Consider Anthropic's Message Batches API for bulk processing (if available)
- Store narratives as optional — missing narratives shouldn't block other data
**Warning signs:** Phase 3 UI taking minutes per building, Phase 5 batch projections showing weeks of runtime

## Code Examples

Verified patterns from official sources and existing codebase:

### Calculate LL97 Penalty for Both Periods
```python
# Source: CLAUDE.md Section 4.4 + Decimal best practices
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

def calculate_ll97_penalty(
    electricity_kwh: Optional[float],
    natural_gas_kbtu: Optional[float],
    fuel_oil_kbtu: Optional[float],
    steam_kbtu: Optional[float],
    use_type_sqft: Dict[str, float]
) -> Dict[str, Decimal]:
    """
    Calculate LL97 penalty for both compliance periods.

    Returns dict with keys:
    - ghg_emissions_2024_2029, emissions_limit_2024_2029, penalty_2024_2029
    - ghg_emissions_2030_2034, emissions_limit_2030_2034, penalty_2030_2034

    Returns None values if required inputs are missing.
    """
    # Check if we have minimum required data
    if not any([electricity_kwh, natural_gas_kbtu, fuel_oil_kbtu, steam_kbtu]):
        return {
            'ghg_emissions_2024_2029': None,
            'emissions_limit_2024_2029': None,
            'penalty_2024_2029': None,
            'ghg_emissions_2030_2034': None,
            'emissions_limit_2030_2034': None,
            'penalty_2030_2034': None
        }

    results = {}
    penalty_per_tco2e = Decimal("268")  # $268 per ton CO2e excess

    for period in ["2024-2029", "2030-2034"]:
        # Step 1: Calculate GHG emissions
        ghg = calculate_ghg_emissions(
            electricity_kwh or 0,
            natural_gas_kbtu or 0,
            fuel_oil_kbtu or 0,
            steam_kbtu or 0,
            period
        )

        # Step 2: Calculate emissions limit
        limit = calculate_emissions_limit(use_type_sqft, period)

        # Step 3: Calculate penalty
        excess = ghg - limit
        penalty = (excess * penalty_per_tco2e) if excess > 0 else Decimal("0")
        penalty = penalty.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Store results with period-specific keys
        period_key = period.replace("-", "_")
        results[f'ghg_emissions_{period_key}'] = ghg
        results[f'emissions_limit_{period_key}'] = limit
        results[f'penalty_{period_key}'] = penalty

    return results
```

### API Call with Exponential Backoff
```python
# Source: backoff library documentation + Anthropic SDK best practices
import backoff
from anthropic import Anthropic, RateLimitError, APIError

@backoff.on_exception(
    backoff.expo,
    (RateLimitError, APIError),
    max_tries=3,
    jitter=backoff.full_jitter
)
def generate_narrative_with_retry(
    client: Anthropic,
    category: str,
    building_data: Dict[str, Any]
) -> str:
    """Generate narrative with automatic retry on rate limit or API errors."""
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        system="You are a mechanical engineering expert...",
        temperature=0.3,
        messages=[{"role": "user", "content": "..."}]
    )
    return message.content[0].text
```

### Extend Building_Metrics Table for Calculations
```python
# Source: Existing lib/storage.py pattern
# Add to building_metrics CREATE TABLE statement:

ALTER TABLE building_metrics ADD COLUMN IF NOT EXISTS
    -- LL97 penalty calculations (2024-2029 period)
    ghg_emissions_2024_2029 NUMERIC,
    emissions_limit_2024_2029 NUMERIC,
    penalty_2024_2029 NUMERIC,

    -- LL97 penalty calculations (2030-2034 period)
    ghg_emissions_2030_2034 NUMERIC,
    emissions_limit_2030_2034 NUMERIC,
    penalty_2030_2034 NUMERIC,

    -- System narratives (TEXT columns)
    envelope_narrative TEXT,
    heating_narrative TEXT,
    cooling_narrative TEXT,
    air_distribution_narrative TEXT,
    ventilation_narrative TEXT,
    dhw_narrative TEXT;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual narrative writing | AI-generated with Claude | 2024-2025 | 300,000 narratives automated, consistent tone |
| OpenAI GPT-3.5 for narratives | Anthropic Claude Sonnet 4.5 | 2025-2026 | Better factual accuracy, less hallucination |
| Float for financial calculations | Decimal with string initialization | Longstanding best practice | Prevents precision errors |
| Synchronous API calls | Async with backoff retry | 2024+ | Resilient to transient failures, faster batches |
| Hardcoded emissions factors | Period-specific lookup tables | 2024 (LL97 regulations) | Supports 2024-2029 vs 2030-2034 compliance |

**Deprecated/outdated:**
- Float for penalty calculations: Causes precision errors at scale
- Temperature > 0.5 for factual content: Introduces unwanted creativity (use 0.2-0.3 per 2026 best practices)
- Synchronous-only narrative generation: Batch processing needs async or rate limiting

## Open Questions

Things that couldn't be fully resolved:

1. **Anthropic Message Batches API availability**
   - What we know: Anthropic SDK supports `client.messages.batches` for bulk processing
   - What's unclear: Rate limits, turnaround time, cost differences vs streaming API
   - Recommendation: Implement synchronous generation for Phase 3 (single building), research batches API for Phase 5 (50k batch)

2. **Pydantic validation for calculation outputs**
   - What we know: Pydantic can validate Decimal types and structured outputs
   - What's unclear: Whether validation overhead is worth it for simple calculation results
   - Recommendation: Skip Pydantic for Phase 3 (calculations are deterministic), reconsider if adding complex validation rules

3. **Handling buildings with zero use-type square footage**
   - What we know: Some LL97 covered buildings may have incomplete LL84 data
   - What's unclear: Should penalty be $0, None, or "Insufficient data" when use-type data is missing
   - Recommendation: Return None for penalty fields when use-type data is insufficient, log these BBLs for manual review

4. **Narrative context field standardization**
   - What we know: CLAUDE.md specifies 8 context fields passed to all narratives
   - What's unclear: Whether to include penalty calculation results in narrative context (circular dependency)
   - Recommendation: Keep narratives independent of penalty calculations (Step 5 doesn't depend on Step 4), run in parallel if needed

## Sources

### Primary (HIGH confidence)
- [Anthropic Python SDK Official Repository](https://github.com/anthropics/anthropic-sdk-python) - Installation, usage, async support, error handling
- [Python Decimal Documentation](https://docs.python.org/3/library/decimal.html) - Official stdlib documentation for Decimal
- [EPA Greenhouse Gas Equivalencies Calculator](https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references) - Emissions calculation methodology
- [Energy Star Building Emissions Calculator Technical Reference](https://www.energystar.gov/sites/default/files/tools/Building_Emissions_Calculator_Tech_Reference_Final_1.pdf) - Building energy emissions formulas
- Existing codebase: lib/api_client.py (narrative generation verified implementation)
- Existing codebase: lib/storage.py (dynamic upsert pattern verified)
- CLAUDE.md Section 4.4 (LL97 penalty calculation formula and coefficients)

### Secondary (MEDIUM confidence)
- [Claude API Temperature Settings Best Practices](https://medium.com/@er.nitheeshsudarsanan/understanding-model-parameters-temperature-top-k-and-top-p-235629624920) - Temperature 0.2-0.3 for factual content
- [Python Decimal vs Float for Financial Calculations](https://www.laac.dev/blog/float-vs-decimal-python/) - Decimal best practices verified
- [Backoff Library for Python Retry Patterns](https://pypi.org/project/backoff/) - Exponential backoff implementation
- [Prompt Engineering Guide 2026](https://www.analyticsvidhya.com/blog/2026/01/prompt-engineering-guide-2/) - Handling missing data with explicit fallbacks
- [API Error Handling & Retry Strategies: Python Guide 2026](https://easyparser.com/blog/api-error-handling-retry-strategies-python-guide) - API resilience patterns

### Tertiary (LOW confidence)
- [Pydantic AI Framework](https://ai.pydantic.dev/) - Structured output validation (optional for this phase)
- [Claude Prompt Engineering Best Practices 2026](https://promptbuilder.cc/blog/claude-prompt-engineering-best-practices-2026) - General prompt patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official libraries (anthropic SDK, stdlib Decimal), already in use (psycopg2)
- Architecture: HIGH - Patterns verified in existing codebase (api_client.py, storage.py) and official docs
- Pitfalls: HIGH - Based on MEMORY.md known issues (None handling) + well-documented Decimal/float precision problems
- Calculations formula: HIGH - Specified in CLAUDE.md Section 4.4 with exact coefficients and emissions factors

**Research date:** 2026-02-10
**Valid until:** 60 days (stable domain - financial calculations and LLM APIs are mature technologies)
