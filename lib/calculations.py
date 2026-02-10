"""
LL97 Penalty Calculation Engine.

Implements the 3-step LL97 penalty formula:
1. Calculate GHG Emissions from energy usage and carbon coefficients
2. Calculate Emissions Limit from use-type square footage and emissions factors
3. Calculate Penalty = max(GHG - Limit, 0) × $268 per tCO2e

All calculations use Decimal precision to avoid floating-point errors.
Supports both compliance periods: 2024-2029 and 2030-2034.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional
from lib.storage import USE_TYPE_SQFT_COLUMNS


# Carbon coefficients by compliance period (tCO2e per unit)
CARBON_COEFFICIENTS = {
    "2024-2029": {
        "electricity": Decimal("0.000288962"),  # tCO2e per kWh
        "natural_gas": Decimal("0.00005311"),    # tCO2e per kBtu
        "fuel_oil": Decimal("0.00007421"),       # tCO2e per kBtu
        "steam": Decimal("0.00004493")           # tCO2e per kBtu
    },
    "2030-2034": {
        "electricity": Decimal("0.000145"),      # tCO2e per kWh
        "natural_gas": Decimal("0.00005311"),    # tCO2e per kBtu
        "fuel_oil": Decimal("0.00007421"),       # tCO2e per kBtu
        "steam": Decimal("0.0000432")            # tCO2e per kBtu
    }
}


# Emissions factors by use type and compliance period (tCO2e per sqft)
# Keys match column names WITHOUT the _sqft suffix
EMISSIONS_FACTORS = {
    "2024-2029": {
        "adult_education": Decimal("0.00758"),
        "ambulatory_surgical_center": Decimal("0.01181"),
        "automobile_dealership": Decimal("0.00675"),
        "bank_branch": Decimal("0.00987"),
        "bowling_alley": Decimal("0.00574"),
        "college_university": Decimal("0.00987"),
        "convenience_store_without_gas_station": Decimal("0.00675"),
        "courthouse": Decimal("0.00426"),
        "data_center": Decimal("0.02381"),
        "distribution_center": Decimal("0.00574"),
        "enclosed_mall": Decimal("0.01074"),
        "financial_office": Decimal("0.00846"),
        "fitness_center_health_club_gym": Decimal("0.00987"),
        "food_sales": Decimal("0.01181"),
        "food_service": Decimal("0.01181"),
        "hospital_general_medical_surgical": Decimal("0.02381"),
        "hotel": Decimal("0.00987"),
        "k_12_school": Decimal("0.00675"),
        "laboratory": Decimal("0.02381"),
        "library": Decimal("0.00675"),
        "lifestyle_center": Decimal("0.00846"),
        "mailing_center_post_office": Decimal("0.00426"),
        "medical_office": Decimal("0.01074"),
        "movie_theater": Decimal("0.01181"),
        "multifamily_housing": Decimal("0.00675"),
        "museum": Decimal("0.01181"),
        "non_refrigerated_warehouse": Decimal("0.00426"),
        "office": Decimal("0.00758"),
        "other": Decimal("0.02381"),  # Other - Restaurant/Bar
        "other_education": Decimal("0.00846"),
        "other_entertainment_public_assembly": Decimal("0.00987"),
        "other_lodging_residential": Decimal("0.00758"),
        "other_mall": Decimal("0.01074"),
        "other_public_services": Decimal("0.00758"),
        "other_recreation": Decimal("0.00987"),
        "other_services": Decimal("0.01074"),
        "other_technology_science": Decimal("0.02381"),
        "outpatient_rehabilitation_physical_therapy": Decimal("0.01181"),
        "parking": Decimal("0.00426"),
        "performing_arts": Decimal("0.00846"),
        "personal_services": Decimal("0.00574"),
        "pre_school_daycare": Decimal("0.00675"),
        "refrigerated_warehouse": Decimal("0.00987"),
        "residence_hall_dormitory": Decimal("0.00758"),
        "restaurant": Decimal("0.01181"),
        "retail_store": Decimal("0.00758"),
        "self_storage_facility": Decimal("0.00426"),
        "senior_care_community": Decimal("0.01138"),
        "social_meeting_hall": Decimal("0.00987"),
        "strip_mall": Decimal("0.01181"),
        "supermarket_grocery_store": Decimal("0.02381"),
        "urgent_care_clinic_other_outpatient": Decimal("0.01181"),
        "vocational_school": Decimal("0.00574"),
        "wholesale_club_supercenter": Decimal("0.01138"),
        "worship_facility": Decimal("0.00574"),
    },
    "2030-2034": {
        "adult_education": Decimal("0.003565528"),
        "ambulatory_surgical_center": Decimal("0.008980612"),
        "automobile_dealership": Decimal("0.002824097"),
        "bank_branch": Decimal("0.004036172"),
        "bowling_alley": Decimal("0.003103815"),
        "college_university": Decimal("0.002099748"),
        "convenience_store_without_gas_station": Decimal("0.003540032"),
        "courthouse": Decimal("0.001480533"),
        "data_center": Decimal("0.014791131"),
        "distribution_center": Decimal("0.0009916"),
        "enclosed_mall": Decimal("0.003983803"),
        "financial_office": Decimal("0.003697004"),
        "fitness_center_health_club_gym": Decimal("0.003946728"),
        "food_sales": Decimal("0.00520888"),
        "food_service": Decimal("0.007749414"),
        "hospital_general_medical_surgical": Decimal("0.007335204"),
        "hotel": Decimal("0.003850668"),
        "k_12_school": Decimal("0.002230588"),
        "laboratory": Decimal("0.026029868"),
        "library": Decimal("0.002218412"),
        "lifestyle_center": Decimal("0.00470585"),
        "mailing_center_post_office": Decimal("0.00198044"),
        "medical_office": Decimal("0.002912778"),
        "movie_theater": Decimal("0.005395268"),
        "multifamily_housing": Decimal("0.00334664"),
        "museum": Decimal("0.0053958"),
        "non_refrigerated_warehouse": Decimal("0.000883187"),
        "office": Decimal("0.002690852"),
        "other": Decimal("0.008505075"),  # Other - Restaurant/Bar
        "other_education": Decimal("0.002934006"),
        "other_entertainment_public_assembly": Decimal("0.002956738"),
        "other_lodging_residential": Decimal("0.001901982"),
        "other_mall": Decimal("0.001928226"),
        "other_public_services": Decimal("0.003808033"),
        "other_recreation": Decimal("0.00447957"),
        "other_services": Decimal("0.001823381"),
        "other_technology_science": Decimal("0.010446456"),
        "outpatient_rehabilitation_physical_therapy": Decimal("0.006018323"),
        "parking": Decimal("0.000214421"),
        "performing_arts": Decimal("0.002472539"),
        "personal_services": Decimal("0.004843037"),
        "pre_school_daycare": Decimal("0.002362874"),
        "refrigerated_warehouse": Decimal("0.002852131"),
        "residence_hall_dormitory": Decimal("0.002464089"),
        "restaurant": Decimal("0.004038374"),
        "retail_store": Decimal("0.00210449"),
        "self_storage_facility": Decimal("0.00061183"),
        "senior_care_community": Decimal("0.004410123"),
        "social_meeting_hall": Decimal("0.003833108"),
        "strip_mall": Decimal("0.001361842"),
        "supermarket_grocery_store": Decimal("0.00675519"),
        "urgent_care_clinic_other_outpatient": Decimal("0.05772375"),
        "vocational_school": Decimal("0.004613122"),
        "wholesale_club_supercenter": Decimal("0.004264962"),
        "worship_facility": Decimal("0.001230602"),
    }
}


def calculate_ghg_emissions(
    electricity_kwh: Optional[float],
    natural_gas_kbtu: Optional[float],
    fuel_oil_kbtu: Optional[float],
    steam_kbtu: Optional[float],
    period: str
) -> Decimal:
    """
    Calculate total GHG emissions from energy usage.

    Args:
        electricity_kwh: Electricity usage in kWh
        natural_gas_kbtu: Natural gas usage in kBtu
        fuel_oil_kbtu: Fuel oil usage in kBtu
        steam_kbtu: District steam usage in kBtu
        period: Compliance period ("2024-2029" or "2030-2034")

    Returns:
        Total GHG emissions in tCO2e, quantized to 2 decimal places
    """
    coeffs = CARBON_COEFFICIENTS[period]

    # Convert inputs to Decimal, handling None values
    elec = Decimal(str(electricity_kwh or 0))
    gas = Decimal(str(natural_gas_kbtu or 0))
    oil = Decimal(str(fuel_oil_kbtu or 0))
    stm = Decimal(str(steam_kbtu or 0))

    # Calculate emissions for each fuel type
    ghg = (
        elec * coeffs["electricity"] +
        gas * coeffs["natural_gas"] +
        oil * coeffs["fuel_oil"] +
        stm * coeffs["steam"]
    )

    return ghg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_emissions_limit(
    use_type_sqft: Dict[str, float],
    period: str
) -> Decimal:
    """
    Calculate emissions limit from use-type square footage.

    Args:
        use_type_sqft: Dictionary mapping use-type keys (without _sqft suffix)
                      to square footage values
        period: Compliance period ("2024-2029" or "2030-2034")

    Returns:
        Emissions limit in tCO2e, quantized to 2 decimal places
    """
    factors = EMISSIONS_FACTORS[period]
    limit = Decimal("0")

    for use_type, sqft in use_type_sqft.items():
        # Skip None, zero, or negative values
        if not sqft or sqft <= 0:
            continue

        # Skip use types without emissions factors
        if use_type not in factors:
            continue

        # Add contribution from this use type
        sqft_decimal = Decimal(str(sqft))
        limit += sqft_decimal * factors[use_type]

    return limit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_ll97_penalty(
    electricity_kwh: Optional[float],
    natural_gas_kbtu: Optional[float],
    fuel_oil_kbtu: Optional[float],
    steam_kbtu: Optional[float],
    use_type_sqft: Dict[str, float]
) -> Dict[str, Optional[Decimal]]:
    """
    Calculate LL97 penalties for both compliance periods.

    Implements the 3-step LL97 penalty formula:
    1. Calculate GHG emissions from energy usage
    2. Calculate emissions limit from use-type square footage
    3. Calculate penalty = max(GHG - Limit, 0) × $268

    Args:
        electricity_kwh: Electricity usage in kWh
        natural_gas_kbtu: Natural gas usage in kBtu
        fuel_oil_kbtu: Fuel oil usage in kBtu
        steam_kbtu: District steam usage in kBtu
        use_type_sqft: Dictionary mapping use-type keys to square footage

    Returns:
        Dictionary with keys:
        - ghg_emissions_2024_2029
        - emissions_limit_2024_2029
        - penalty_2024_2029
        - ghg_emissions_2030_2034
        - emissions_limit_2030_2034
        - penalty_2030_2034

        All values are None if no energy data is available.
    """
    # Check if we have any energy data
    has_energy_data = any([
        electricity_kwh and electricity_kwh > 0,
        natural_gas_kbtu and natural_gas_kbtu > 0,
        fuel_oil_kbtu and fuel_oil_kbtu > 0,
        steam_kbtu and steam_kbtu > 0
    ])

    if not has_energy_data:
        # Return None for all fields if no energy data
        return {
            "ghg_emissions_2024_2029": None,
            "emissions_limit_2024_2029": None,
            "penalty_2024_2029": None,
            "ghg_emissions_2030_2034": None,
            "emissions_limit_2030_2034": None,
            "penalty_2030_2034": None
        }

    # Calculate for both periods
    results = {}
    penalty_per_tco2e = Decimal("268")

    for period in ["2024-2029", "2030-2034"]:
        # Step 1: Calculate GHG emissions
        ghg = calculate_ghg_emissions(
            electricity_kwh, natural_gas_kbtu, fuel_oil_kbtu, steam_kbtu, period
        )

        # Step 2: Calculate emissions limit
        limit = calculate_emissions_limit(use_type_sqft, period)

        # Step 3: Calculate penalty (excess emissions × $268)
        excess = ghg - limit
        penalty = max(excess, Decimal("0")) * penalty_per_tco2e
        penalty = penalty.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Store results with period-specific keys
        period_key = period.replace("-", "_")
        results[f"ghg_emissions_{period_key}"] = ghg
        results[f"emissions_limit_{period_key}"] = limit
        results[f"penalty_{period_key}"] = penalty

    return results


def extract_use_type_sqft(building_data: Dict) -> Dict[str, float]:
    """
    Extract use-type square footage from building data dict.

    Bridges the gap between database column names (with _sqft suffix)
    and calculator keys (without _sqft suffix).

    Args:
        building_data: Dictionary with building data (from database)

    Returns:
        Dictionary mapping use-type keys (without _sqft) to square footage values
    """
    use_type_sqft = {}

    for col in USE_TYPE_SQFT_COLUMNS:
        # Get value from database column (with _sqft suffix)
        sqft = building_data.get(col)

        # Skip None, zero, or negative values
        if not sqft or sqft <= 0:
            continue

        # Strip _sqft suffix to get the calculator key
        use_type_key = col.replace("_sqft", "")
        use_type_sqft[use_type_key] = sqft

    return use_type_sqft


__all__ = [
    'calculate_ghg_emissions',
    'calculate_emissions_limit',
    'calculate_ll97_penalty',
    'extract_use_type_sqft',
    'CARBON_COEFFICIENTS',
    'EMISSIONS_FACTORS'
]
