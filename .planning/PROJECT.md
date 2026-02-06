# Fischer 50K Building Lead Tool

## What This Is

A lead generation and building intelligence system for Fischer Energy Partners. Aggregates public NYC building data (LL97 Covered Buildings, LL84 Energy Benchmarking, LL87 Energy Audits), calculates GHG emissions and LL97 carbon penalties, and generates AI-powered engineering narratives for ~27,000 covered buildings. The Fischer team uses a lightweight web UI to test data accuracy, then runs batch processing to pre-populate the full database. Selected building records push on-demand to Airtable for sales pipeline management.

## Core Value

Accurate, pre-calculated building intel with professional system narratives — ready to share with prospective clients without manual research.

## Requirements

### Validated

- ✓ LL87 energy audit data loading to Supabase — existing (`ll87_load_supabase.py`)
- ✓ LL84 energy benchmarking data loading to Supabase — existing (`ll84_load_supabase.py`, `ll84_raw_load_supabase.py`)
- ✓ LL97 covered buildings list loading to Supabase — existing (`ll97_load_supabase.py`)
- ✓ Supabase PostgreSQL database with raw JSONB tables — existing
- ✓ n8n workflow for API orchestration (GeoSearch, PLUTO, LL84) — existing partial

### Active

- [ ] Web UI for manual BBL lookup and testing (Streamlit)
- [ ] 5-step data retrieval waterfall (Identity → LL84 → LL87 → Penalty Calc → Narratives)
- [ ] GHG emissions calculator (2024-2029 and 2030-2034 periods)
- [ ] LL97 penalty calculator ($268/tCO2e formula)
- [ ] AI narrative generation for 6 building systems (Anthropic Claude)
- [ ] Building_Metrics table for aggregated lead data
- [ ] On-demand Airtable push for selected buildings
- [ ] Autonomous batch processing for all ~27K buildings

### Out of Scope

- Real-time continuous sync to Airtable — on-demand push only, not live sync
- Mobile app — web UI only
- Building sensor data integration — separate project, different Supabase tables
- User authentication — internal tool, Fischer team only
- Public-facing API — internal use only

## Context

**Existing Infrastructure:**
- Supabase PostgreSQL (aws-0-us-west-2.pooler.supabase.com) with LL87, LL84, LL97 data already loaded
- Python 3 data loading scripts in `Supabase_script/`
- n8n workflow for API orchestration (`Get Building Data Fischer.json`)
- Windows Server 2022 with nightly pg_dump backups

**Data Sources:**
- LL97 Covered Buildings List (26,982 buildings, primary identity source)
- LL84 NYC Open Data API (live energy benchmarking)
- LL87 Raw Table (2019-2024 and 2012-2018 audit data)
- PLUTO API (fallback for building metrics)
- GeoSearch API (address → BBL/BIN resolution)

**Narrative Prompts:**
- 6 detailed system prompts for Building Envelope, Heating, Cooling, Air Distribution, Ventilation, and Domestic Hot Water
- Data-only approach — no inferences, explicit "not documented" fallbacks
- Prompts stored and ready for implementation

**Field Mapping:**
- 89 total fields defined in spreadsheet
- 11 bare minimum fields (green-highlighted) required for core functionality
- 42 use-type square footage fields for penalty calculations
- Source hierarchy: LL97 CBL > LL84 API > LL87 > PLUTO > Manual

## Constraints

- **Tech Stack**: Python + Streamlit for UI (team not developers, need simple/lightweight)
- **AI Provider**: Anthropic Claude for narrative generation
- **Database**: Supabase PostgreSQL (already in use, shared with sensor data project)
- **Integration**: Airtable for Fischer's project management workflow
- **BBL Format**: 10-digit numeric in SQL, dashed format for DOF browser lookups
- **Rate Limits**: Batch processing ~1,000 buildings/night to respect API limits

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Streamlit for UI | Simple, Python-native, team isn't developers | — Pending |
| Anthropic Claude for narratives | Team preference, quality narratives | — Pending |
| On-demand Airtable push (not sync) | Simpler integration, team controls what goes to pipeline | — Pending |
| Data-only narrative prompts | Accuracy over completeness, no hallucination | — Pending |
| BBL as universal identifier | Single anchor across all data sources | ✓ Good |

---
*Last updated: 2026-02-06 after initialization*
