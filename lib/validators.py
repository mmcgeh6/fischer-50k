"""
BBL validation and format conversion utilities.

BBL (Borough-Block-Lot) is a 10-digit identifier:
- Digit 1: Borough (1=Manhattan, 2=Bronx, 3=Brooklyn, 4=Queens, 5=Staten Island)
- Digits 2-6: Block number (5 digits, zero-padded)
- Digits 7-10: Lot number (4 digits, zero-padded)

Example: 1011190036 = Manhattan, Block 01119, Lot 0036
"""

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
