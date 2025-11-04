#!/usr/bin/env python3
"""Utility to normalize phone numbers to E.164 format."""

def normalize_to_e164(phone: str, default_country: str = None) -> str:
    """
    Normalize phone number to E.164 format.
    
    E.164 format: +[country code][subscriber number]
    - Starts with +
    - No spaces, dashes, or other formatting
    - Country code (1-3 digits)
    - Subscriber number (up to 15 digits total)
    
    Examples:
        +14155552671 (US)
        +442071838750 (UK)
        +33123456789 (France)
    """
    if not phone:
        return ""
    
    # Remove all non-digit characters except leading +
    cleaned = phone.strip()
    if cleaned.startswith('+'):
        prefix = '+'
        cleaned = cleaned[1:]
    else:
        prefix = ''
    
    # Remove all non-digits
    digits = ''.join(c for c in cleaned if c.isdigit())
    
    if not digits:
        return ""
    
    # If already has +, reconstruct
    if prefix:
        # Check for common issues like +4407... (should be +447...)
        # UK numbers: +44 followed by 10 digits (no leading 0)
        if digits.startswith('440') and len(digits) == 12:
            # Remove the 0 after country code
            digits = '44' + digits[3:]
        # US/Canada: +1 followed by 10 digits
        elif digits.startswith('1') and len(digits) == 11:
            pass  # Already correct
        # Other patterns can be added here
        
        return f"+{digits}"
    
    # If no +, try to add it based on length/pattern
    # This is tricky without knowing the country
    if len(digits) == 10:
        # Could be US/Canada without country code
        if default_country == 'US' or default_country == 'CA':
            return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # US/Canada with country code but no +
        return f"+{digits}"
    
    # Return with + if it looks like it has country code
    if len(digits) >= 10:
        return f"+{digits}"
    
    # Too short, return as-is
    return phone


# Test cases
test_cases = [
    ("+22996993171", "+22996993171"),  # Already correct
    ("+4407717715664", "+447717715664"),  # UK with extra 0
    ("+19193028696", "+19193028696"),  # US correct
    ("+14695818388", "+14695818388"),  # US correct
    ("+447939822889", "+447939822889"),  # UK correct
    ("1234567890", "+1234567890"),  # No country code
    ("+1 (415) 555-2671", "+14155552671"),  # Formatted US
    ("+44 20 7183 8750", "+442071838750"),  # Formatted UK
]

print("E.164 Normalization Tests:\n")
print(f"{'Input':<25} {'Expected':<20} {'Result':<20} {'Status'}")
print("=" * 80)

for input_phone, expected in test_cases:
    result = normalize_to_e164(input_phone)
    status = "✓ PASS" if result == expected else "✗ FAIL"
    print(f"{input_phone:<25} {expected:<20} {result:<20} {status}")

print("\n" + "=" * 80)
print("\nReal BotPenguin Examples:\n")

real_examples = [
    ("+22996993171", "Benin"),
    ("+4407717715664", "UK (has extra 0)"),
    ("+19193028696", "US"),
    ("+14695818388", "US"),
    ("+447939822889", "UK (correct)"),
]

for phone, country in real_examples:
    normalized = normalize_to_e164(phone)
    print(f"{phone:<20} → {normalized:<20} ({country})")
