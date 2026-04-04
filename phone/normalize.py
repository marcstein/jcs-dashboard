"""
phone/normalize.py — E.164 Phone Number Normalization

Converts common US phone number formats to E.164 (+1XXXXXXXXXX).
All phone numbers are normalized before database lookup or storage.

Handles:
- (314) 555-1234  → +13145551234
- 314-555-1234    → +13145551234
- 314.555.1234    → +13145551234
- +1 314 555 1234 → +13145551234
- 3145551234      → +13145551234
- 13145551234     → +13145551234
- +13145551234    → +13145551234 (already normalized)
"""
import re
from typing import Optional


def normalize_phone(number: str) -> Optional[str]:
    """
    Normalize a phone number to E.164 format (+1XXXXXXXXXX).

    Returns None if the input is empty, None, or not a valid US number.
    Only handles US numbers (+1 country code) for now.
    """
    if not number or not isinstance(number, str):
        return None

    # Strip everything except digits and leading +
    stripped = number.strip()
    if not stripped:
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', stripped)

    if not digits:
        return None

    # Handle different lengths
    if len(digits) == 10:
        # Standard 10-digit US number
        return f"+1{digits}"
    elif len(digits) == 11 and digits[0] == '1':
        # 11-digit with country code
        return f"+{digits}"
    elif len(digits) == 7:
        # 7-digit local number — can't normalize without area code
        return None
    elif len(digits) > 11:
        # Might have extension or extra digits — try taking first 11
        if digits[0] == '1' and len(digits) >= 11:
            return f"+{digits[:11]}"
        elif len(digits) >= 10:
            return f"+1{digits[:10]}"
        return None
    else:
        # Less than 7 or 8-9 digits — not a valid US number
        return None


def format_display(normalized: str) -> str:
    """
    Format a normalized E.164 number for human display.

    +13145551234 → (314) 555-1234
    """
    if not normalized or len(normalized) != 12 or not normalized.startswith('+1'):
        return normalized or ""

    digits = normalized[2:]  # Strip +1
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def is_valid_e164(number: str) -> bool:
    """Check if a string is a valid E.164 US number."""
    if not number:
        return False
    return bool(re.match(r'^\+1\d{10}$', number))
