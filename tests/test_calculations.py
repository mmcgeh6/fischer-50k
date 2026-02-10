"""Verify LL97 penalty calculation engine."""
from decimal import Decimal
from lib.calculations import (
    calculate_ll97_penalty, calculate_ghg_emissions,
    calculate_emissions_limit, extract_use_type_sqft,
    CARBON_COEFFICIENTS, EMISSIONS_FACTORS
)

# Test 1: Known values — 10M kWh electricity, 5M kBtu gas, 100k sqft office
result = calculate_ll97_penalty(
    electricity_kwh=10000000,
    natural_gas_kbtu=5000000,
    fuel_oil_kbtu=0,
    steam_kbtu=0,
    use_type_sqft={'office': 100000}
)
print('GHG 2024-2029:', result['ghg_emissions_2024_2029'])
print('Limit 2024-2029:', result['emissions_limit_2024_2029'])
print('Penalty 2024-2029:', result['penalty_2024_2029'])
# Expected: GHG = 10M*0.000288962 + 5M*0.00005311 = 2889.62 + 265.55 = 3155.17
# Limit = 100000 * 0.00758 = 758.00
# Penalty = (3155.17 - 758.00) * 268 = ~642,401.56
assert isinstance(result['penalty_2024_2029'], Decimal), "Penalty must be Decimal"
assert result['penalty_2024_2029'] > Decimal("600000"), f"Penalty too low: {result['penalty_2024_2029']}"

# Test 2: None handling
none_result = calculate_ll97_penalty(None, None, None, None, {})
assert none_result['penalty_2024_2029'] is None, "None inputs should return None penalty"
print('None handling: OK')

# Test 3: extract_use_type_sqft bridges DB column names to calculator keys
test_building = {'office_sqft': 50000, 'hotel_sqft': 30000, 'bbl': '1234567890', 'gfa': 80000}
extracted = extract_use_type_sqft(test_building)
assert 'office' in extracted and extracted['office'] == 50000, "Should strip _sqft suffix"
assert 'hotel' in extracted and extracted['hotel'] == 30000, "Should strip _sqft suffix"
assert 'bbl' not in extracted, "Should only extract use-type columns"
# Verify extracted keys match EMISSIONS_FACTORS keys
for key in extracted:
    assert key in EMISSIONS_FACTORS['2024-2029'], f"Key '{key}' not in EMISSIONS_FACTORS"
print('extract_use_type_sqft: OK')

# Test 4: Emissions factors completeness
print(f'Emissions factor count (2024-2029): {len(EMISSIONS_FACTORS["2024-2029"])}')
print(f'Emissions factor count (2030-2034): {len(EMISSIONS_FACTORS["2030-2034"])}')
assert len(EMISSIONS_FACTORS['2024-2029']) >= 54, "Should have at least 54 use-type factors"

print('\nAll tests passed!')
