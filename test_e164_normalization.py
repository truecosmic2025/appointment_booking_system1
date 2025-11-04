#!/usr/bin/env python3
"""Test E.164 phone number normalization."""

import sys
from dotenv import load_dotenv
load_dotenv()

from app.integrations.botpenguin_service import get_phone_from_botpenguin

print("""
╔════════════════════════════════════════════════════════════════╗
║              E.164 PHONE NUMBER NORMALIZATION                  ║
╚════════════════════════════════════════════════════════════════╝

E.164 Format Standard:
  • Starts with + (plus sign)
  • Followed by country code (1-3 digits)
  • Followed by subscriber number
  • No spaces, dashes, or other formatting
  • Maximum 15 digits total (including country code)
  • No leading zeros after country code

Examples:
  ✓ +14155552671 (US)
  ✓ +447911123456 (UK)
  ✓ +33123456789 (France)
  ✗ +4407911123456 (UK with extra 0 - INVALID)
  ✗ +1 (415) 555-2671 (formatted - INVALID)

""")

# Test with real BotPenguin data
test_emails = [
    "kirsteenglen@gmail.com",  # UK number (had extra 0)
    "abibaomarmoussa@gmail.com",  # Benin number
    "thealangroupllc1@gmail.com",  # US number
]

print("=" * 70)
print("TESTING BOTPENGUIN PHONE RETRIEVAL WITH E.164 NORMALIZATION")
print("=" * 70)

for email in test_emails:
    print(f"\nEmail: {email}")
    phone = get_phone_from_botpenguin(email)
    
    if phone:
        # Validate E.164 format
        is_valid = (
            phone.startswith('+') and
            len(phone) >= 11 and
            len(phone) <= 16 and
            phone[1:].isdigit()
        )
        
        status = "✓ VALID E.164" if is_valid else "✗ INVALID"
        print(f"  Phone: {phone}")
        print(f"  Status: {status}")
        
        # Check specific issues
        if phone.startswith('+440') and len(phone) > 13:
            print(f"  ⚠ Warning: UK number may have extra 0")
        elif not phone.startswith('+'):
            print(f"  ✗ Error: Missing + prefix")
        elif not phone[1:].isdigit():
            print(f"  ✗ Error: Contains non-digit characters")
    else:
        print(f"  Phone: (not found)")

print("\n" + "=" * 70)
print("NORMALIZATION RULES APPLIED")
print("=" * 70)
print("""
1. Remove all formatting (spaces, dashes, parentheses)
2. Ensure + prefix
3. Remove leading zeros after country code:
   • UK: +4407... → +447...
   • France: +3301... → +331...
   • Spain: +3409... → +349...
4. Validate total length (10-15 digits)
""")

print("=" * 70)
print("STORAGE IN DATABASE")
print("=" * 70)
print("""
When a booking is created, the visitor_phone field will contain:
  • E.164 formatted phone number (e.g., +447911123456)
  • NULL if no phone available

This ensures:
  ✓ Consistent format across all bookings
  ✓ Compatible with SMS/WhatsApp APIs
  ✓ Easy to validate and process
  ✓ International phone number support
""")
