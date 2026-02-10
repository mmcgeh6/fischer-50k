# Roadmap: Fischer 50K Building Lead Tool

## Overview

This roadmap transforms the Fischer 50K Building Lead Tool from existing data loaders into a complete lead generation system. Starting with a Streamlit UI for manual testing, we build the 5-step data retrieval waterfall, add GHG penalty calculations and AI-powered system narratives, integrate with Airtable for pipeline management, and finally enable autonomous batch processing for all 27,000 buildings. The progression follows test-then-scale: manual verification first, batch automation last.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Web UI Foundation** - Build Streamlit interface for manual BBL lookup and testing ✓
- [ ] **Phase 2: Data Retrieval Waterfall** - Implement 5-step data pipeline with storage
- [ ] **Phase 3: Calculations & Narratives** - Add GHG/penalty calculations and AI narrative generation
- [ ] **Phase 4: Airtable Integration** - Enable on-demand push to Airtable for sales pipeline
- [ ] **Phase 5: Batch Processing** - Autonomous processing for all 27K buildings with resume capability

## Phase Details

### Phase 1: Web UI Foundation
**Goal**: Users can manually test building data retrieval through a simple web interface
**Depends on**: Nothing (first phase)
**Requirements**: UI-01, UI-02, UI-03, UI-04
**Success Criteria** (what must be TRUE):
  1. User can enter a BBL number and trigger data retrieval
  2. User can view all retrieved building fields in organized sections
  3. User can view the 6 generated system narratives for any building
  4. User can view GHG emissions and penalty calculations for both compliance periods
**Plans**: 3 plans in 3 waves

Plans:
- [x] 01-01-PLAN.md — Project setup, dependencies, and BBL validation utilities ✓
- [x] 01-02-PLAN.md — Database module and Claude API client for narratives ✓
- [x] 01-03-PLAN.md — Main Streamlit application with all UI components ✓

### Phase 2: Data Retrieval Waterfall
**Goal**: System can fetch, aggregate, and store all building data from multiple sources via live API calls
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, STOR-01, STOR-02, STOR-03
**Success Criteria** (what must be TRUE):
  1. System resolves BBL to canonical identity from LL97 Covered Buildings List (or GeoSearch fallback)
  2. System retrieves live energy data from LL84 API and mechanical data from LL87 raw table
  3. System retrieves all 11 bare minimum fields plus 42 use-type square footage fields
  4. System saves retrieved data to Building_Metrics table with upsert logic
  5. System tracks which buildings have been processed with timestamps
**Plans**: 3 plans in 2 waves

Plans:
- [ ] 02-01-PLAN.md — Building_Metrics table schema and storage upsert module
- [ ] 02-02-PLAN.md — NYC Open Data API clients (GeoSearch, LL84, PLUTO) with retry logic
- [ ] 02-03-PLAN.md — Waterfall orchestrator and Streamlit UI integration

### Phase 3: Calculations & Narratives
**Goal**: System generates accurate penalty projections and professional system narratives
**Depends on**: Phase 2
**Requirements**: CALC-01, CALC-02, CALC-03, CALC-04, CALC-05, NARR-01, NARR-02, NARR-03, NARR-04, NARR-05, NARR-06, NARR-07, NARR-08
**Success Criteria** (what must be TRUE):
  1. System calculates GHG emissions for both 2024-2029 and 2030-2034 periods using period-specific coefficients
  2. System calculates emissions limits from use-type square footage and emissions factors for all 57 use types
  3. System calculates LL97 penalty projections ($268 per tCO2e excess) for both periods
  4. System generates all 6 system narratives (Envelope, Heating, Cooling, Air Distribution, Ventilation, DHW) using Anthropic Claude
  5. System uses data-only approach with explicit "not documented" fallbacks (no inferences)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD during planning
- [ ] 03-02: TBD during planning
- [ ] 03-03: TBD during planning

### Phase 4: Airtable Integration
**Goal**: Users can push selected building records to Airtable for sales pipeline management
**Depends on**: Phase 3
**Requirements**: UI-05, SYNC-01, SYNC-02, SYNC-03
**Success Criteria** (what must be TRUE):
  1. User can select a building and push its complete record to Airtable on demand
  2. System maps all Supabase fields to corresponding Airtable columns
  3. System handles Airtable API authentication and respects rate limits
**Plans**: TBD

Plans:
- [ ] 04-01: TBD during planning
- [ ] 04-02: TBD during planning

### Phase 5: Batch Processing
**Goal**: System can autonomously process all 27K buildings with progress tracking and recovery
**Depends on**: Phase 4
**Requirements**: BATCH-01, BATCH-02, BATCH-03, BATCH-04, BATCH-05
**Success Criteria** (what must be TRUE):
  1. System can process all ~27K buildings autonomously without manual intervention
  2. System tracks progress (which buildings processed, which pending, success/failure counts)
  3. System handles API failures with retry logic and continues processing
  4. System respects API rate limits (~1,000 buildings/night) without manual throttling
  5. System can resume from last processed building after interruption
**Plans**: TBD

Plans:
- [ ] 05-01: TBD during planning
- [ ] 05-02: TBD during planning
- [ ] 05-03: TBD during planning

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Web UI Foundation | 3/3 | Complete | 2026-02-06 |
| 2. Data Retrieval Waterfall | 0/3 | Planned | - |
| 3. Calculations & Narratives | 0/TBD | Not started | - |
| 4. Airtable Integration | 0/TBD | Not started | - |
| 5. Batch Processing | 0/TBD | Not started | - |
