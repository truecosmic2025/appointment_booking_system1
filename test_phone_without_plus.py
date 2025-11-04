#!/usr/bin/env python3
"""Test phone normalization for numbers without + prefix."""

import sys
sys.path.insert(0, '.')

from app.coach.public import _normalize_phone_e164

test_cases = [
    ("919051527991", "India - 12 digits without +"),
    ("19193028696", "US - 11 digits without +"),
    ("+919051527991", "India - with +"),
    ("+19193028696", "US - with +"),
    ("9193028696", "US - 10 digits (no country code)"),
    ("4407717715664", "UK - 13 digits without +"),
    ("+4407717715664", "UK - with + and extra 0"),
]

print("=" * 80)
print("TESTING PHONE NORMALIZATION WITHOUT + PREFIX")
print("=" * 80)
print()

for phone, description in test_cases:
    result = _normalize_phone_e164(phone)
    print(f"Input:  {phone:<20} ({description})")
    print(f"Output: {result:<20}")
    print(f"Length: {len(result)} characters")
    
    # Validate E.164
    is_valid = (
        result.startswith('+') and
        len(result) >= 11 and
        len(result) <= 16 and
        result[1:].isdigit()
    )
    print(f"Status: {'✓ VALID E.164' if is_valid else '✗ INVALID'}")
    print()

print("=" * 80)
print("ANALYSIS")
print("=" * 80)
print("""
Current behavior for numbers without +:
  • If ≥10 digits: Adds + prefix
  • Assumes the number already includes country code
  
Examples:
  919051527991  → +919051527991  (assumes India country code 91)
  19193028696   → +19193028696   (assumes US country code 1)
  9193028696    → +9193028696    (ambiguous - could be US without country code)

POTENTIAL ISSUES:
  ⚠ 919051527991 could be:
     • India: +91 9051527991 (country code 91)
     • OR: +919 051527991 (country code 919 - doesn't exist)
     
  ⚠ 9193028696 could be:
     • US: +1 9193028696 (missing country code 1)
     • OR: +91 93028696 (India with wrong format)
     • OR: +919 3028696 (country code 919 - doesn't exist)

RECOMMENDATION:
  For numbers without +, we should either:
  1. Require + prefix in input
  2. Use a default country code (e.g., US +1)
  3. Use a phone number parsing library (phonenumbers)
""")
