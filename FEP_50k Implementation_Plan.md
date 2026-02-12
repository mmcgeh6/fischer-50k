Supabase PW: U4Y$A9$x1GBRooAF   
Supabase API url: [https://lhtuvtfqjovfuwuxckcw.supabase.co](https://lhtuvtfqjovfuwuxckcw.supabase.co)  
Supabase secret key: sb\_secret\_eAUr9JR9ZFnTGowTCJmKXQ\_LdqUROYu  
Supabase publishable secret key: sb\_publishable\_nMdCWcCjDDwaPOrtHoSkbA\_ofATi-qz

FEP Automated 50k Building Lead Tool — Implementation Plan  
Revised February 3, 2026 — Post Meeting \#2 \+ Infrastructure & Field Finalization  
Prepared by: The AI Consulting Lab | For: Fischer Energy Partners

1\. Executive Summary

The goal is to build a Lead Tool capable of programmatically analyzing 50,000+ NYC buildings to generate preliminary energy audits (Roadmaps) using public data.

The Strategy: A Live-Hybrid Aggregator Architecture. We use a Cloud-Hosted PostgreSQL Database (Supabase) as the production hub to store heavy/unavailable datasets (LL87 Audits, LL97 Covered Buildings List), while using verified NYC Open Data APIs to fetch fresh identity, verification, and compliance data. The LL97 penalty calculations are handled by a local Python calculation engine rather than browser-based scraping. FEP's Windows Server 2022 maintains a nightly backup mirror for local data access and disaster recovery.  
\[CHANGED FROM v2: Database hosting moved from FEP's Windows Server to cloud-hosted Supabase PostgreSQL. Windows Server becomes backup/mirror rather than production host. See Section 4 for full rationale.\]

The LL97 Covered Buildings List serves as the master input for both single-building testing and the full 50,000-building batch automation. The BBL (Borough Block Lot) is the universal anchor identifier across all steps.

Reference Documents:  
\- LL87 Temp Headers (Google Sheets — linked separately)  
\- LL97 Covered Buildings List Headers (Google Sheets — linked separately)  
\- Main SQL Columns File: 50k Building Database Prep List (Google Sheets) — DELIVERED by Jesse (02/02/2026)  
\- LL84 Data Dictionary: data.cityofnewyork.us/Environment/NYC-Building-Energy-and-Water-Data-Disclosure-for-/5zyy-y8am/about\_data  
\- System Narrative Key Columns: Delivered by Gabe (02/03/2026) — Column L mapping in Prep List

2\. System Architecture: The Smart Aggregator

The system operates in a streamlined 5-step Waterfall for each building lead. Each step holds its returned data in temporary memory. At the final stage, all data is cross-checked, filtered, and verified before being committed to the master table.

2.1 Core Identifier Rule: BBL as North Star

The BBL (Borough Block Lot) is the sole universal anchor for all data operations. There is a one-to-one ratio between building entity and BBL for compliance purposes, even when a single BBL covers a campus of multiple physical structures.

BIN (Building Identification Number) is retained as a secondary data point and potential merge key. A single BBL can have multiple BINs (campus-style facilities, interconnected buildings), which creates confusion when used as a primary search key. Where an API requires BIN as a query parameter (notably LL84), we use the BIN resolved from the BBL in Step 1 — but BBL remains the anchor. Note: LL84 BIN fields may contain multiple entries delimited by semicolons.

2.2 Source Hierarchy Rule

The Primary/Secondary source hierarchy in the Master Logic Map is a true Hierarchy of Truth. When a field is populated from both sources and the values differ, the Primary source always takes precedence. Example: If PLUTO says 125,000 sqft and LL84 says 135,000 sqft, use whichever is listed as Primary for that field.

The LL97 Covered Buildings List and Department of Buildings (DOB) are the heavyweight pillars for identity and address data. Self-reported data (LL84) and supplementary sources are subordinate.

2.3 Address Resolution Rule

The address returned from the LL97 Covered Buildings List is treated as the canonical address for each building. Addresses from other sources (DOF, LL84 self-reported, PLUTO) are stored as aliases for reference but are not used as primary search keys. This prevents vanity address mismatches and inconsistencies from self-reported data.

2.4 The 5-Step Waterfall

Step 1: Identity & Compliance  
\- Primary Action: Query the LL97 Covered Buildings List (Cloud SQL: LL97\_Covered\_Raw) to check compliance status (Article 320/321) and retrieve the official BBL, BIN, and canonical address.  
\- Failover: If the building is not found in the Covered List, trigger the GeoSearch API (v2) to resolve the address to a BBL/BIN for a Non-Compliance report.  
\- Verification: Use Headless Browser (Playwright) to fetch official address aliases from DOB (BIS) and DOF (Tax Records).  
\- Human Confirmation Gate: Before proceeding to Steps 2–5, the engineer must confirm that the resolved BBL corresponds to the correct property. This is critical for campus-style buildings where one BBL covers multiple physical structures. In the manual workflow (Phase A), this is a UI confirmation step. In batch mode (Phase B), this gate is bypassed with the assumption that the Covered Buildings List data is authoritative.

Step 2: Live Usage Fetch (Verified API)  
\- Source: Query the NYC Open Data LL84 API (Endpoint: 5zyy-y8am).  
\- Key: Use the BIN resolved from Step 1 to query this dataset. Although BBL is the North Star identifier, the LL84 API is indexed by BIN, so we pass the BIN that was resolved from the BBL in Step 1\.  
\- Supplement: If data is missing in LL84, query the NYC Open Data PLUTO API (Endpoint: 64uk-42ks) for structure data (Year Built, GFA).  
\- Treatment: LL84 data is a direct data pull — specific columns, specific values. No AI summarization is applied to LL84 fields. The data is stored as-is in the Building Metrics table.

Step 3: Mechanical Retrieval  
\- Source: Query LL87 Raw Table (Cloud SQL) using BBL as the primary search key.  
\- Action: Retrieve deep mechanical specs (Boilers, Chillers, Envelope) from audit filings stored in the database.  
\- LL87 Dual Dataset Protocol: There are two LL87 datasets: 2019–2024 and 2012–2018. The reporting cycle is every 10 years (compliance years end in 6), so duplicates across the two datasets are unlikely but possible. The search logic is:  
  1\. Search the 2019–2024 dataset first.  
  2\. If no match, search the 2012–2018 dataset.  
  3\. If a match exists in both, take the record from the most recent dataset.  
\- Multiple Systems Handling: The LL87 data is wide (one building \= hundreds of columns). When a building has multiple system variants (e.g., Roof 1 Concrete, Roof 2 Built-up, or Heating Plant 1 Steam Boiler \+ HVAC Sys 1 One-Pipe Steam), all variants are ingested and kept as separate fields. We do not pre-filter for primary vs. secondary importance because the data alone often cannot determine which system covers the majority of the building. The AI narrative engine in Step 5 handles the synthesis.

Step 4: LL97 Penalty Calculations  
\- Source: Local Python calculation script using data collected from Steps 1–3.  
\- Action: Calculate LL97 penalty projections for both compliance periods (2024-2029 and 2030-2034) using the established formulas.  
\[CHANGED FROM v2: Jesse delivered the complete calculation spec. The three-step formula is now fully defined — see Section 4.3 for the complete Carbon Coefficients, Emissions Factors, and Calculator Steps.\]  
\- Calculator Logic (3 Steps):  
  Step 4a — Calculate GHG Emissions: Multiply each utility consumption value by its corresponding Carbon Coefficient. Sum all utilities to get total building emissions (tCO2e).  
  Step 4b — Calculate Emissions Limits: Multiply each Use Type's Gross Floor Area (sqft) by its corresponding Emissions Factor. Sum all use types to get the building's emissions limit (tCO2e).  
  Step 4c — Calculate Penalty: IF \[GHG Emissions \- Emissions Limit\] \> 0, multiply the excess by $268 per tCO2e. ELSE penalty \= $0.  
  Calculate for both compliance periods (2024-2029 and 2030-2034) and report all six values: Emissions, Limit, and Penalty for each period.

Step 5: Narrative Generation  
\[CHANGED FROM v2: Gabe delivered the narrative category mapping. Expanded from 4 to 6 narrative categories plus BAS and 4 equipment spec categories.\]

This step applies only to LL87 mechanical/envelope data. LL84 energy usage data from Step 2 is stored as structured data fields and does not pass through AI narrative generation.

Action: Feed the LL87 mechanical specs into AI System Prompts to generate professional engineering narratives. Each narrative receives context fields (Year Built, Building Use Type, Total GFA, and all energy consumption values) to inform the writing.

Narrative Categories (from Gabe's Column L mapping):  
  1\. Building Envelope Narrative — Source: LL87 Data  
  2\. Heating System Narrative — Source: LL87 Data  
  3\. Cooling System Narrative — Source: LL87 Data  
  4\. Air Distribution System Narrative — Source: LL87 Data  
  5\. Ventilation System Narrative — Source: LL87 Data \[NEW\]  
  6\. Domestic Hot Water System Narrative — Source: LL87 Data \[NEW\]

Additional LL87-Sourced Fields (not AI narratives, but structured data):  
  7\. Building Automation System — Source: LL87 Data (Boolean/Narrative)  
  8\. Heating Equipment Specs — quantity and capacity of Boilers, Heat Exchangers, Hot Water Pumps, Zone Equipment  
  9\. Cooling Equipment Specs — quantity and capacity of Chillers, Chilled Water Pumps, Cooling Towers, Condenser Water Pumps, Heat Exchangers  
  10\. Air Distribution Equipment Specs — quantity and capacity of Air Handling Units, Rooftop Units, Packaged Units  
  11\. Ventilation Equipment Specs — quantity and capacity of Make-up Air Units, Dedicated Outdoor Air Systems, Energy Recovery Ventilators

Context Fields Fed to All Narrative Prompts (from Gabe's Column L/M mapping):  
  \- Year Built  
  \- Largest Property Use Type  
  \- Property GFA \- Calculated (Buildings and Parking) (ft²)  
  \- Site Energy Use (kBtu)  
  \- Fuel Oil \#2 Use (kBtu)  
  \- District Steam Use (kBtu)  
  \- Natural Gas Use (kBtu)  
  \- Electricity Use \- Grid Purchase (kWh)

Open Question (from Gabe, Column G): Equipment Specs (rows 84-87) — "Do we want to break this down into specific line items?" This needs a team decision on whether equipment specs are stored as structured fields (individual columns for each piece of equipment) or as narrative text blocks.

Quality control: System prompts define what goes into each narrative, what doesn't, the target length (1-2 paragraphs per category), and the overall goal. Additional testing is needed to ensure the AI does not hallucinate system types (e.g., steam vs. hot water) when the data is ambiguous.

3\. Master Field Logic Map

The engine follows a strict Primary vs. Secondary Source Waterfall. It attempts the Primary first; if missing, it falls back to Secondary. In cases of conflicting data between Primary and Secondary, the Primary source always wins.

Key Safeguards:  
\- The Dash Protocol: SQL/API operations use BBLs as 10-digit numeric (1011190036). Browser operations (DOF) dynamically convert to dashed format (1-01119-0036).  
\- BBL as North Star: BBL is the universal anchor. BIN is used as a query parameter for LL84 (since the API is indexed by BIN) but is always derived from the BBL resolved in Step 1\.  
\- Canonical Address: The LL97 Covered Buildings List address is the official address. All other addresses are aliases.

Full Master Logic Map:

Field | Primary Source | Primary Key | Secondary Source | Secondary Key | Format Note | Source Location  
\--- | \--- | \--- | \--- | \--- | \--- | \---  
BBL (10-Digit) | LL97 Covered List | Address | GeoSearch API | Address | No Dashes (SQL Index) | LL97\_Covered\_Raw / GeoSearch API  
Preliminary BIN | LL97 Covered List | BBL | DOB BIS | Address | Secondary data point; semicolon-delimited possible | LL97\_Covered\_Raw / Playwright  
DOB Building Address | LL97 Covered List | BBL | DOB BIS | BIN | Canonical address | LL97\_Covered\_Raw / Playwright  
Building Name | LL84 API (5zyy) | BIN (from BBL) | Google/Wikipedia/AI LLM | Address | Narrative String | NYC Open Data / Web  
DOF Property Address | DOF Search | BBL (dashed) | DOF Search | Address | Dashes Required | a836-pts-access.nyc.gov  
ESPM Property ID | LL84 API (5zyy) | BIN (from BBL) | Manual Input | N/A | Numeric ID | NYC Open Data (5zyy-y8am)  
Building Owner | DOF Search | BBL (dashed) | DOF Search | Address | Dashes Required | a836-pts-access.nyc.gov  
Year Built | LL84 API (5zyy) | BIN (from BBL) | PLUTO API (64uk) | BBL | YYYY | NYC Open Data  
Landmark Status | NYC Landmarks | Address | PLUTO API (64uk) | BBL | Yes/No | landmarks.planning.nyc.gov  
Number of Floors | PLUTO API (64uk) | BBL | Manual Input | N/A | Numeric | NYC Open Data (64uk-42ks)  
Floor Breakdown | Google/Wikipedia | Address | AI LLM | Address | Narrative Detail | Web Search / LLM  
Total GFA (sf) | LL84 API (5zyy) | BIN (from BBL) | PLUTO API (64uk) | BBL | Numeric | NYC Open Data  
Building GFA (sf) | LL84 API (5zyy) | BIN (from BBL) | PLUTO API (64uk) | BBL | Numeric | NYC Open Data  
Parking GFA (sf) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Building Use Type | LL84 API (5zyy) | BIN (from BBL) | Manual Input | N/A | Dominant Use Type | NYC Open Data (5zyy-y8am)  
Number of Residential Units | PLUTO API (64uk) | BBL | LL84 API (5zyy) | BIN (from BBL) | Numeric (MF/Hotel) | NYC Open Data  
Occupancy % | LL84 API (5zyy) | BIN (from BBL) | Manual Input | N/A | Percentage | NYC Open Data  
Hours of Operation | LL84 API (5zyy) | BIN (from BBL) | Manual Input | N/A | Tenant/HVAC Hours | NYC Open Data  
Multifamily Units | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Number of Elevators | Google/Wikipedia | Address | Manual Input | N/A | Numeric | Web / Manual  
Source EUI (kBtu/ft²) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Site Energy Use (kBtu) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Fuel Oil \#2 Use (kBtu) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
District Steam Use (kBtu) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Natural Gas Use (kBtu) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Electricity Use (kWh) | LL84 API (5zyy) | BIN (from BBL) | N/A | N/A | Numeric | NYC Open Data  
Use Types 1-42 (Named) | LL84 API (5zyy) | BIN (from BBL) | Manual Input | N/A | Named columns \+ SqFt integer | NYC Open Data  
2024-2029 GHG Emissions | Python Calc Engine | Steps 1-3 data | N/A | N/A | Tons CO2e | Calculated  
2024-2029 Emissions Limit | Python Calc Engine | Steps 1-3 data | N/A | N/A | Tons CO2e | Calculated  
2024-2029 Annual Penalty | Python Calc Engine | Steps 1-3 data | N/A | N/A | USD | Calculated  
2030-2034 GHG Emissions | Python Calc Engine | Steps 1-3 data | N/A | N/A | Tons CO2e | Calculated  
2030-2034 Emissions Limit | Python Calc Engine | Steps 1-3 data | N/A | N/A | Tons CO2e | Calculated  
2030-2034 Annual Penalty | Python Calc Engine | Steps 1-3 data | N/A | N/A | USD | Calculated  
Building Envelope Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
Heating System Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
Cooling System Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
Air Distribution Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
Ventilation Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
DHW Narrative | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | AI-generated paragraph | LL87\_Raw SQL  
BAS Presence | LL87 Raw (2019-24) | BBL | Manual Input | N/A | Boolean/Narrative | LL87\_Raw SQL  
Heating Equipment Specs | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | Structured or Narrative (TBD) | LL87\_Raw SQL  
Cooling Equipment Specs | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | Structured or Narrative (TBD) | LL87\_Raw SQL  
Air Distribution Equip Specs | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | Structured or Narrative (TBD) | LL87\_Raw SQL  
Ventilation Equip Specs | LL87 Raw (2019-24) | BBL | LL87 Raw (2012-18) | BBL | Structured or Narrative (TBD) | LL87\_Raw SQL  
Google Maps Link | Google Maps API | Lat/Lon | Manual Input | N/A | URL | Lat/Lon from PLUTO  
Google Aerial Images | NYC Zola | BBL | Manual Input | N/A | URL | zola.planning.nyc.gov

4\. Database Strategy  
\[CHANGED FROM v2: Major infrastructure revision — cloud-hosted production database with local backup\]

4.1 Infrastructure Architecture

Production Database: Cloud-hosted PostgreSQL on Supabase (free tier to start, Pro tier at $25/month if needed). This is the single source of truth that all tools connect to — Airtable sync, N8N workflows, the sensor data app, and eventually the search UI.

Local Backup: FEP's Windows Server 2022 maintains a nightly backup via pg\_dump from the Supabase instance. This gives Fischer local data access and disaster recovery without making the local machine the production single point of failure.

Rationale for Cloud Over Local:  
\- Eliminates the connectivity/firewall configuration that was blocking development (Cameron's deliverable).  
\- A cloud-hosted database is internet-accessible by default with built-in SSL — no port exposure, no firewall rules, no tunneling.  
\- Removes the "Brian's machine must be on" dependency for production availability.  
\- The sensor data app, N8N workflows, and Airtable sync are all platform-agnostic — they connect via standard PostgreSQL connection strings regardless of host.  
\- For a 50k row database, Supabase's free tier (500MB storage) is more than sufficient for development and initial production.  
\- If Fischer later wants to move to Google Cloud SQL or back to the Windows Server, migration is pg\_dump \+ pg\_restore \+ updating connection strings. No code changes, no schema changes. PostgreSQL is PostgreSQL everywhere.

Connection Architecture:  
\- All tools (Airtable, N8N, sensor app, search UI) connect to a single Supabase PostgreSQL connection string.  
\- Database credentials stored as environment variables / single credential configs in each tool — never hardcoded in functions.  
\- Migration to any other PostgreSQL host requires updating one config per tool, not rewriting any logic.

The database uses a Drop and Replace strategy for raw data. Generic table names avoid year-specific confusion.

4.2 Layer 1: Raw Data Lakes (The Dump Tables)

LL87\_Raw: The mechanical audit dataset. Two source files (2019–2024 and 2012–2018) are stored in a single table with a reporting\_period indicator column. When new data drops, truncate and replace. The automation queries the latest period first, then falls back to the earlier period. LL87 compliance year is every 10 years ending in 6\.

LL97\_Covered\_Raw: The list of all required buildings and their compliance paths. This is also the master input for the 50k batch automation.

Upload Infrastructure: An interface will be provided for the FEP team to upload the latest version of either Excel file. The upload process will truncate the existing table and replace it with the new data, keeping the database current.

4.3 Layer 2: Master Metrics (The Lead Table)

Building\_Metrics: Contains all core fields for all saved leads, populated with verified data from the 5-step waterfall.

Use Type Column Strategy: Flat named columns directly in the Building\_Metrics table. Each column is named for its actual use type with the reported square footage as an integer value. Zeros populate where a use type does not apply. Additionally, a Largest\_Property\_Use\_Type field captures the dominant building classification.

Complete Use Type Column List (42 columns from Jesse's LL84 mapping):  
  1\. Adult Education  
  2\. Ambulatory Surgical Center  
  3\. Automobile Dealership  
  4\. Bank Branch  
  5\. College/University  
  6\. Courthouse  
  7\. Data Center  
  8\. Distribution Center  
  9\. Enclosed Mall  
  10\. Financial Office  
  11\. Fitness Center/Health Club/Gym  
  12\. Food Sales  
  13\. Food Service  
  14\. Hospital (General Medical & Surgical)  
  15\. Hotel  
  16\. K-12 School  
  17\. Laboratory  
  18\. Mailing Center/Post Office  
  19\. Manufacturing/Industrial Plant  
  20\. Medical Office  
  21\. Movie Theater  
  22\. Multifamily Housing  
  23\. Museum  
  24\. Non-Refrigerated Warehouse  
  25\. Office  
  26\. Other  
  27\. Outpatient Rehabilitation/Physical Therapy  
  28\. Parking  
  29\. Performing Arts  
  30\. Pre-school/Daycare  
  31\. Refrigerated Warehouse  
  32\. Residence Hall/Dormitory  
  33\. Restaurant  
  34\. Retail Store  
  35\. Self-Storage Facility  
  36\. Senior Living Community  
  37\. Social/Meeting Hall  
  38\. Strip Mall  
  39\. Supermarket/Grocery  
  40\. Urgent Care/Clinic/Other Outpatient  
  41\. Wholesale Club/Supercenter  
  42\. Worship Facility

LL84 Use Types WITHOUT Emissions Factors (store sqft but exclude from penalty calc):  
  \- Barracks  
  \- Convention Center  
  \- Energy/Power Station  
  \- Hotel \- Gym/Fitness Center Floor Area  
  \- Wastewater Treatment Plant

Emissions Factor Use Types NOT in LL84 (exist in penalty calc but no LL84 column — handle via manual input or "Other" mapping):  
  \- Bowling Alley  
  \- Convenience Store without Gas Station  
  \- Library  
  \- Lifestyle Center  
  \- Personal Services (Health/Beauty, Dry Cleaning, etc.)  
  \- Vocational School  
  \- Other \- Education  
  \- Other \- Entertainment/Public Assembly  
  \- Other \- Lodging/Residential  
  \- Other \- Mall  
  \- Other \- Public Services  
  \- Other \- Recreation  
  \- Other \- Restaurant/Bar  
  \- Other \- Services  
  \- Other \- Specialty Hospital  
  \- Other \- Technology/Science

4.4 Penalty Calculation Engine — Complete Specification

Carbon Coefficients (tCO2e per unit):

Fuel Type | Unit | 2024-2029 | 2030-2034  
\--- | \--- | \--- | \---  
Electricity | tCO2e/kWh | 0.000288962 | 0.000145  
Natural Gas | tCO2e/kBtu | 0.00005311 | 0.00005311  
\#2 Fuel Oil | tCO2e/kBtu | 0.00007421 | 0.00007421  
District Steam | tCO2e/kBtu | 0.00004493 | 0.0000432

Emissions Factors by Use Type (tCO2e per sqft):

Use Type | 2024-2029 | 2030-2034  
\--- | \--- | \---  
Adult Education | 0.00758 | 0.003565528  
Ambulatory Surgical Center | 0.01181 | 0.008980612  
Automobile Dealership | 0.00675 | 0.002824097  
Bank Branch | 0.00987 | 0.004036172  
Bowling Alley | 0.00574 | 0.003103815  
College/University | 0.00987 | 0.002099748  
Convenience Store w/o Gas | 0.00675 | 0.003540032  
Courthouse | 0.00426 | 0.001480533  
Data Center | 0.02381 | 0.014791131  
Distribution Center | 0.00574 | 0.0009916  
Enclosed Mall | 0.01074 | 0.003983803  
Financial Office | 0.00846 | 0.003697004  
Fitness Center/Health Club/Gym | 0.00987 | 0.003946728  
Food Sales | 0.01181 | 0.00520888  
Food Service | 0.01181 | 0.007749414  
Hospital (General Medical & Surgical) | 0.02381 | 0.007335204  
Hotel | 0.00987 | 0.003850668  
K-12 School | 0.00675 | 0.002230588  
Laboratory | 0.02381 | 0.026029868  
Library | 0.00675 | 0.002218412  
Lifestyle Center | 0.00846 | 0.00470585  
Mailing Center/Post Office | 0.00426 | 0.00198044  
Manufacturing/Industrial Plant | 0.00758 | 0.00141703  
Medical Office | 0.01074 | 0.002912778  
Movie Theater | 0.01181 | 0.005395268  
Multifamily Housing | 0.00675 | 0.00334664  
Museum | 0.01181 | 0.0053958  
Non-Refrigerated Warehouse | 0.00426 | 0.000883187  
Office | 0.00758 | 0.002690852  
Other \- Education | 0.00846 | 0.002934006  
Other \- Entertainment/Public Assembly | 0.00987 | 0.002956738  
Other \- Lodging/Residential | 0.00758 | 0.001901982  
Other \- Mall | 0.01074 | 0.001928226  
Other \- Public Services | 0.00758 | 0.003808033  
Other \- Recreation | 0.00987 | 0.00447957  
Other \- Restaurant/Bar | 0.02381 | 0.008505075  
Other \- Services | 0.01074 | 0.001823381  
Other \- Specialty Hospital | 0.02381 | 0.006321819  
Other \- Technology/Science | 0.02381 | 0.010446456  
Outpatient Rehab/Physical Therapy | 0.01181 | 0.006018323  
Parking | 0.00426 | 0.000214421  
Performing Arts | 0.00846 | 0.002472539  
Personal Services | 0.00574 | 0.004843037  
Pre-school/Daycare | 0.00675 | 0.002362874  
Refrigerated Warehouse | 0.00987 | 0.002852131  
Residence Hall/Dormitory | 0.00758 | 0.002464089  
Restaurant | 0.01181 | 0.004038374  
Retail Store | 0.00758 | 0.00210449  
Self-Storage Facility | 0.00426 | 0.00061183  
Senior Living Community | 0.01138 | 0.004410123  
Social/Meeting Hall | 0.00987 | 0.003833108  
Strip Mall | 0.01181 | 0.001361842  
Supermarket/Grocery Store | 0.02381 | 0.00675519  
Urgent Care/Clinic/Other Outpatient | 0.01181 | 0.05772375  
Vocational School | 0.00574 | 0.004613122  
Wholesale Club/Supercenter | 0.01138 | 0.004264962  
Worship Facility | 0.00574 | 0.001230602

Calculator Steps:  
  Step 1: GHG Emissions \= (Electricity\_kWh × Elec\_Coeff) \+ (NatGas\_kBtu × Gas\_Coeff) \+ (FuelOil\_kBtu × Oil\_Coeff) \+ (Steam\_kBtu × Steam\_Coeff)  
  Step 2: Emissions Limit \= SUM of (UseType\_N\_sqft × UseType\_N\_EmissionsFactor) for all use types  
  Step 3: IF (GHG Emissions \- Emissions Limit) \> 0 THEN Penalty \= (GHG Emissions \- Emissions Limit) × $268 ELSE Penalty \= $0  
  Run Steps 1-3 for both 2024-2029 and 2030-2034 periods (different coefficients/factors for each).

5\. UI & Workflow (Testing to Automation)

The transition from Testing to Automation is seamless because they use the same underlying Worker code.

5.1 Phase A: The Search & Verify Workflow (Manual)

Search: User enters an address (or BBL) in the Lightweight UI.  
Step 1 Resolution: The Worker resolves the address to a BBL, BIN, and canonical address from the LL97 Covered Buildings List.  
Human Confirmation: The UI displays the resolved building identity. The engineer confirms: "Yes, this is the correct building." This is especially important for campus-style buildings.  
Live Aggregation: Upon confirmation, the Worker runs Steps 2–5 for that building.  
Display Results: The UI shows the full dashboard.  
Save to SQL: User manually commits the verified record to the Building\_Metrics table.

5.2 Phase B: The Batch Automation (Bulk)

Trigger: A configuration switch (RUN\_MODE=BATCH) or Cron Job.  
Input: The Worker iterates through the list of 50,000 BBLs in LL97\_Covered\_Raw. This is the master input — the automation goes row by row.  
Process: Runs the same aggregation logic as Phase A (Steps 1–5) in a loop (e.g., 1,000 records/night), with the human confirmation gate bypassed.  
Logging: All results are auto-saved to Building\_Metrics.

6\. Implementation Roadmap

Phase 1: Foundation (The Mechanical Layer)  
\- Setup: Provision Supabase PostgreSQL instance (free tier). Configure connection credentials as environment variables across all tools.  
\- Ingestion: Write Python scripts to clean and import the LL87 (both periods) and LL97 Excel files into SQL. Include the upload interface for future updates.  
\- Calculation Engine: Build the Python LL97 penalty calculation engine using Jesse's complete Carbon Coefficients, Emissions Factors, and 3-step formula (see Section 4.4).  
\- Backup: Configure nightly pg\_dump to FEP's Windows Server 2022 for local mirror.  
\- Deliverable: A queryable cloud database of all NYC mechanical audits plus a working penalty calculator.

Phase 2: The Browser UI (Testing)  
\- Build: A simple Web Interface (React/FastAPI) accessible to FEP.  
\- Function: Search → Resolve → Confirm → Aggregate → Verify → Save to SQL loop.  
\- Goal: Allow verified single-record fetching with engineer confirmation before the bulk run.

Phase 3: The Bulk Run  
\- Automation: Flip the switch to BATCH mode.  
\- Output: Populate the Building\_Metrics SQL table with the full 50k dataset.

Appendix A: Verified API Schema

1\. Identity Resolution (GeoSearch)  
Resolves a raw address string to the official BBL and BIN.  
\- Method: GET  
\- Base URL: https://geosearch.planninglabs.nyc/v2/search  
\- Parameters: text: {Input Address} (e.g., "350 5th Ave")  
\- BBL Path: features\[0\].properties.addendum.pad.bbl  
\- BIN Path: features\[0\].properties.addendum.pad.bin

2\. Building Structure (PLUTO)  
Retrieves the Tax Lot structure data (Floors, Owner, Geometry).  
\- Method: GET  
\- Base URL: https://data.cityofnewyork.us/resource/64uk-42ks.json  
\- Parameters: $where: bbl={Target BBL} (10-digit numeric)  
\- Key Fields: ownername, numfloors, bldgarea, yearbuilt

3\. Energy Usage (LL84)  
Retrieves the live 2023–2024 Benchmarking data.  
\- Method: GET  
\- Base URL: https://data.cityofnewyork.us/resource/5zyy-y8am.json  
\- Parameters: $where: nyc\_building\_identification='{Target BIN}'; $order: last\_modified\_date\_property DESC; $limit: 1  
\- Key Fields: electricity\_use\_grid\_purchase\_kbtu, natural\_gas\_use\_kbtu, largest\_property\_use\_type  
\- Note: BIN field may contain semicolon-delimited multiple values

Appendix B: Outstanding Action Items

Owner | Action Item | Status  
\--- | \--- | \---  
Jesse | Deliver 50k Building Database Prep List with field names, sources, penalty calc spec | COMPLETE (02/02/2026)  
Jesse | LL84 column list for all use types plus auxiliary fields | COMPLETE (42 use types \+ 5 no-factor types identified)  
Gabe | Map fields to narrative categories (Column L) \+ define equipment spec categories | COMPLETE (02/03/2026) — 6 narratives \+ BAS \+ 4 equipment spec categories  
Gabe | Open question: Break equipment specs into specific line items? (Column G, rows 84-87) | PENDING — needs team decision  
Team | Confirm handling of Emissions Factor use types that don't appear in LL84 (15 types) | PENDING — manual input vs. "Other" mapping  
Team | Review Primary/Secondary source hierarchy in prep sheet | Confirmed in Meeting 2  
Marcus | Build the N8N workflow for the 5-step waterfall automation | In Progress  
Marcus | Set up Supabase PostgreSQL instance and dump tables for LL87 \+ LL97 | In Progress  
Marcus | Build the Python LL97 penalty calculation engine (complete spec now available) | Not Started  
Marcus | Configure nightly pg\_dump backup to FEP Windows Server | Not Started  
Cameron | Windows Server local PostgreSQL setup for backup mirror | Pending (no longer a development blocker)

Appendix C: System Narrative Context Fields (Gabe's Column L/M Mapping)

Each AI narrative prompt receives the following context fields alongside the LL87 mechanical data for that building:

Context Field (Column L) | Database Field Name (Column M)  
\--- | \---  
Year Built | Year Built  
Building Use Type | Largest Property Use Type  
Total Gross Floor Area (sf) | Property GFA \- Calculated (Buildings and Parking) (ft²)  
Site Energy Use (kBtu) | Site Energy Use (kBtu)  
Fuel Oil \#2 Use (kBtu) | Fuel Oil \#2 Use (kBtu)  
District Steam Use (kBtu) | District Steam Use (kBtu)  
Natural Gas Use (kBtu) | Natural Gas Use (kBtu)  
Electricity Use \- Grid Purchase (kWh) | Electricity Use \- Grid Purchase (kWh)

Revision Log

Date | Version | Changes  
\--- | \--- | \---  
01/27/2026 | v1 — Original | Initial implementation plan drafted from Meeting 1 and Gabe's repo review  
02/02/2026 | v2 — Post Meeting \#2 | Replaced BE-Ex headless browser with Python calc engine; demoted BIN to secondary; flattened use type columns; codified LL87 dual dataset search; added human confirmation gate; defined address resolution rule; separated LL84/LL87 narrative treatment; codified source hierarchy as rule; added action items appendix  
02/03/2026 | v3 — Infrastructure \+ Field Finalization | Moved production database from FEP Windows Server to cloud-hosted Supabase PostgreSQL with local backup mirror; incorporated Jesse's complete penalty calculation spec (Carbon Coefficients, 57 Emissions Factors, 3-step formula); incorporated Gabe's narrative category mapping (expanded from 4 to 6 narratives \+ BAS \+ 4 equipment spec categories); added complete 42 use type column list from LL84; identified 5 LL84 use types without emissions factors and 15 emissions factor types without LL84 columns; added Appendix C for narrative context fields; updated action items to reflect completed deliverables  
