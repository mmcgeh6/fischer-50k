# Requirements: Fischer 50K Building Lead Tool

**Defined:** 2026-02-06
**Core Value:** Accurate, pre-calculated building intel with professional system narratives — ready to share with prospective clients without manual research.

## v1 Requirements

### User Interface

- [x] **UI-01**: User can enter a BBL number to trigger data retrieval ✓
- [x] **UI-02**: User can view all retrieved building data fields (11 minimum + additional fields) ✓
- [x] **UI-03**: User can view 6 generated system narratives for the building ✓
- [x] **UI-04**: User can view GHG emissions and penalty calculations for both compliance periods ✓
- [ ] **UI-05**: User can select a building and push its record to Airtable

### Data Retrieval

- [x] **DATA-01**: System resolves BBL to canonical identity from LL97 Covered Buildings List ✓
- [x] **DATA-02**: System falls back to GeoSearch API if BBL not found in LL97 list ✓
- [x] **DATA-03**: System fetches live energy data from LL84 API using BIN ✓
- [x] **DATA-04**: System retrieves mechanical audit data from LL87 raw table (2019-2024 first, 2012-2018 fallback) ✓
- [x] **DATA-05**: System falls back to PLUTO API for building metrics if LL84 data missing ✓
- [x] **DATA-06**: System retrieves all 11 bare minimum fields (BBL, addresses, year built, use type, GFA, 5 energy metrics) ✓
- [x] **DATA-07**: System retrieves 42 use-type square footage fields for penalty calculations ✓

### Calculations

- [ ] **CALC-01**: System calculates GHG emissions for 2024-2029 period using period-specific carbon coefficients
- [ ] **CALC-02**: System calculates GHG emissions for 2030-2034 period using period-specific carbon coefficients
- [ ] **CALC-03**: System calculates emissions limits from use-type sqft multiplied by emissions factors
- [ ] **CALC-04**: System calculates LL97 penalty projection ($268 per tCO2e excess emissions)
- [ ] **CALC-05**: System handles all 57 use types with their respective emissions factors

### AI Narratives

- [ ] **NARR-01**: System generates Building Envelope narrative using Anthropic Claude
- [ ] **NARR-02**: System generates Heating System narrative using Anthropic Claude
- [ ] **NARR-03**: System generates Cooling System narrative using Anthropic Claude
- [ ] **NARR-04**: System generates Air Distribution System narrative using Anthropic Claude
- [ ] **NARR-05**: System generates Ventilation System narrative using Anthropic Claude
- [ ] **NARR-06**: System generates Domestic Hot Water System narrative using Anthropic Claude
- [ ] **NARR-07**: System uses data-only approach (no inferences, explicit "not documented" fallbacks)
- [ ] **NARR-08**: System passes context fields (year built, use type, GFA, energy metrics) to all narrative prompts

### Storage

- [x] **STOR-01**: System saves retrieved data and narratives to Building_Metrics table in Supabase ✓
- [x] **STOR-02**: System handles upsert logic (update existing, insert new) based on BBL ✓
- [x] **STOR-03**: System tracks which buildings have been processed with timestamps ✓

### Airtable Integration

- [ ] **SYNC-01**: User can push selected building record to Airtable on demand
- [ ] **SYNC-02**: System maps Supabase fields to corresponding Airtable columns
- [ ] **SYNC-03**: System handles Airtable API authentication and rate limits

### Batch Processing

- [ ] **BATCH-01**: System can process all ~27K buildings autonomously
- [ ] **BATCH-02**: System tracks progress (which buildings processed, which pending)
- [ ] **BATCH-03**: System handles API failures with retry logic
- [ ] **BATCH-04**: System respects API rate limits (~1,000 buildings/night)
- [ ] **BATCH-05**: System can resume from last processed building after interruption

## v2 Requirements

### Enhanced UI

- **UI-V2-01**: User can filter/search buildings by various criteria (use type, penalty amount, borough)
- **UI-V2-02**: User can view building on map
- **UI-V2-03**: User can compare multiple buildings side-by-side

### Enhanced Narratives

- **NARR-V2-01**: System generates ECM (Energy Conservation Measure) recommendations
- **NARR-V2-02**: System estimates ROI for recommended improvements

### Reporting

- **RPT-V2-01**: User can export building report as PDF
- **RPT-V2-02**: User can generate portfolio summary across multiple buildings

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time Airtable sync | On-demand push is simpler; team controls what enters pipeline |
| Mobile app | Web UI sufficient for internal team use |
| User authentication | Internal tool, Fischer team only |
| Public API | Internal use only, not exposing to external consumers |
| Building sensor data | Separate project with different Supabase tables |
| Continuous monitoring | This is a lead gen tool, not an operational dashboard |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UI-01 | Phase 1 | Complete |
| UI-02 | Phase 1 | Complete |
| UI-03 | Phase 1 | Complete |
| UI-04 | Phase 1 | Complete |
| UI-05 | Phase 4 | Pending |
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 2 | Complete |
| DATA-04 | Phase 2 | Complete |
| DATA-05 | Phase 2 | Complete |
| DATA-06 | Phase 2 | Complete |
| DATA-07 | Phase 2 | Complete |
| CALC-01 | Phase 3 | Pending |
| CALC-02 | Phase 3 | Pending |
| CALC-03 | Phase 3 | Pending |
| CALC-04 | Phase 3 | Pending |
| CALC-05 | Phase 3 | Pending |
| NARR-01 | Phase 3 | Pending |
| NARR-02 | Phase 3 | Pending |
| NARR-03 | Phase 3 | Pending |
| NARR-04 | Phase 3 | Pending |
| NARR-05 | Phase 3 | Pending |
| NARR-06 | Phase 3 | Pending |
| NARR-07 | Phase 3 | Pending |
| NARR-08 | Phase 3 | Pending |
| STOR-01 | Phase 2 | Complete |
| STOR-02 | Phase 2 | Complete |
| STOR-03 | Phase 2 | Complete |
| SYNC-01 | Phase 4 | Pending |
| SYNC-02 | Phase 4 | Pending |
| SYNC-03 | Phase 4 | Pending |
| BATCH-01 | Phase 5 | Pending |
| BATCH-02 | Phase 5 | Pending |
| BATCH-03 | Phase 5 | Pending |
| BATCH-04 | Phase 5 | Pending |
| BATCH-05 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-06*
*Last updated: 2026-02-06 after roadmap creation*
