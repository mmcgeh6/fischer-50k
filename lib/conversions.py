"""
Energy unit conversion constants and functions.

These conversion factors are used to display energy data in native units
alongside kBtu. Constants are defined here for easy updating by engineering staff.

Last updated: 2026-02-12
Update instructions: Change the constant values below and restart the app.
"""

# ============================================================================
# Conversion Factors
# ============================================================================

# Electricity: 1 kWh = 3.412 kBtu
KWH_TO_KBTU = 3.412

# Natural Gas: 1 therm = 100 kBtu
KBTU_TO_THERMS = 1 / 100

# Fuel Oil #2: 1 gallon = 138.5 kBtu
KBTU_TO_GALLONS_FUEL_OIL = 1 / 138.5

# District Steam: 1 Mlb (thousand pounds) = 1,194 kBtu
KBTU_TO_MLBS_STEAM = 1 / 1194


# ============================================================================
# Conversion Functions
# ============================================================================

def kwh_to_kbtu(kwh: float) -> float:
    """Convert electricity from kWh to kBtu."""
    return kwh * KWH_TO_KBTU


def kbtu_to_therms(kbtu: float) -> float:
    """Convert natural gas from kBtu to therms."""
    return kbtu * KBTU_TO_THERMS


def kbtu_to_gallons_fuel_oil(kbtu: float) -> float:
    """Convert fuel oil #2 from kBtu to gallons."""
    return kbtu * KBTU_TO_GALLONS_FUEL_OIL


def kbtu_to_mlbs_steam(kbtu: float) -> float:
    """Convert district steam from kBtu to Mlbs (thousand pounds)."""
    return kbtu * KBTU_TO_MLBS_STEAM


# ============================================================================
# Reverse Conversion Factors (native units -> kBtu)
# ============================================================================

THERMS_TO_KBTU = 100                   # 1 therm = 100 kBtu
GALLONS_FUEL_OIL_TO_KBTU = 138.5       # 1 gallon fuel oil #2 = 138.5 kBtu
MLBS_STEAM_TO_KBTU = 1194              # 1 Mlb steam = 1,194 kBtu


# ============================================================================
# Reverse Conversion Functions (native units -> kBtu)
# ============================================================================

def therms_to_kbtu(therms: float) -> float:
    """Convert natural gas from therms to kBtu."""
    return therms * THERMS_TO_KBTU


def gallons_to_kbtu(gallons: float) -> float:
    """Convert fuel oil #2 from gallons to kBtu."""
    return gallons * GALLONS_FUEL_OIL_TO_KBTU


def mlbs_to_kbtu(mlbs: float) -> float:
    """Convert district steam from Mlbs to kBtu."""
    return mlbs * MLBS_STEAM_TO_KBTU
