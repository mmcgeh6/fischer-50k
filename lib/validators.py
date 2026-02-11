"""
BBL validation, format conversion, and input detection utilities.

BBL (Borough-Block-Lot) is a 10-digit identifier:
- Digit 1: Borough (1=Manhattan, 2=Bronx, 3=Brooklyn, 4=Queens, 5=Staten Island)
- Digits 2-6: Block number (5 digits, zero-padded)
- Digits 7-10: Lot number (4 digits, zero-padded)

Example: 1011190036 = Manhattan, Block 01119, Lot 0036
"""

import re
from typing import Tuple

def validate_bbl(bbl: str) -> bool:
    """
    Validate NYC BBL format.

    Args:
        bbl: BBL string to validate (should be 10 digits)

    Returns:
        True if valid BBL format, False otherwise
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
    """
    Convert 10-digit BBL to dashed format for DOF lookups.

    Args:
        bbl: 10-digit BBL (e.g., "1011190036")

    Returns:
        Dashed format (e.g., "1-01119-0036")

    Raises:
        ValueError: If BBL is not 10 digits
    """
    if len(bbl) != 10:
        raise ValueError(f"BBL must be 10 digits, got {len(bbl)}")
    return f"{bbl[0]}-{bbl[1:6]}-{bbl[6:]}"


def bbl_from_dashed(dashed: str) -> str:
    """
    Convert dashed BBL to 10-digit format.

    Args:
        dashed: Dashed BBL (e.g., "1-01119-0036")

    Returns:
        10-digit format (e.g., "1011190036")
    """
    return dashed.replace("-", "")


def get_borough_name(bbl: str) -> str:
    """
    Get borough name from BBL.

    Args:
        bbl: 10-digit BBL

    Returns:
        Borough name string
    """
    boroughs = {
        "1": "Manhattan",
        "2": "Bronx",
        "3": "Brooklyn",
        "4": "Queens",
        "5": "Staten Island"
    }
    if not bbl:
        return "Unknown"
    return boroughs.get(bbl[0], "Unknown")


def detect_input_type(user_input: str) -> str:
    """
    Detect whether user input is a BBL, dashed BBL, or address.

    Args:
        user_input: Raw user input string

    Returns:
        "bbl", "dashed_bbl", or "address"
    """
    stripped = user_input.strip()

    # Check dashed BBL pattern: D-DDDDD-DDDD
    if re.match(r"^\d-\d{5}-\d{4}$", stripped):
        return "dashed_bbl"

    # Check 10-digit numeric BBL with valid borough
    if len(stripped) == 10 and stripped.isdigit() and stripped[0] in "12345":
        return "bbl"

    return "address"


def normalize_input(user_input: str) -> Tuple[str, str]:
    """
    Detect input type and normalize to a usable value.

    Args:
        user_input: Raw user input (BBL, dashed BBL, or address)

    Returns:
        Tuple of (input_type, normalized_value) where:
        - input_type is "bbl", "dashed_bbl", or "address"
        - normalized_value is the 10-digit BBL or stripped address string
    """
    stripped = user_input.strip()
    input_type = detect_input_type(stripped)

    if input_type == "dashed_bbl":
        normalized = bbl_from_dashed(stripped)
        # Verify the converted value is actually a valid BBL
        if not validate_bbl(normalized):
            return ("address", stripped)
        return ("dashed_bbl", normalized)

    if input_type == "bbl":
        return ("bbl", stripped)

    return ("address", stripped)
