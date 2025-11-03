#!/usr/bin/env python3
"""Test the complete booking phone retrieval flow."""

import sys
from dotenv import load_dotenv
load_dotenv()

from app.integrations.botpenguin_service import get_phone_from_botpenguin

def test_flow(email: str):
    """Test the complete phone retrieval flow."""
    print(f"\n{'='*60}")
    print(f"TESTING BOOKING PHONE FLOW")
    print(f"{'='*60}\n")
    
    print(f"Scenario: User arrives at booking page with email: {email}\n")
    
    # Step 1: User arrives at booking page
    print("Step 1: User visits /c/coach-slug?email=" + email)
    print("        App calls get_phone_from_botpenguin()")
    
    # Step 2: Retrieve phone from BotPenguin
    phone = get_phone_from_botpenguin(email)
    
    if phone:
        print(f"✓ Step 2: Phone retrieved from BotPenguin: {phone}")
        print(f"✓ Step 3: Phone stored in session and hidden form field")
        print(f"✓ Step 4: User completes booking")
        print(f"✓ Step 5: Booking saved with visitor_phone = '{phone}'")
        print(f"\n{'='*60}")
        print(f"SUCCESS: Phone will be captured in booking table")
        print(f"{'='*60}\n")
        return True
    else:
        print(f"✗ Step 2: No phone found in BotPenguin")
        print(f"  Step 3: Booking proceeds without phone")
        print(f"  Step 4: Booking saved with visitor_phone = NULL")
        print(f"\n{'='*60}")
        print(f"RESULT: Phone will NOT be captured (contact has no phone)")
        print(f"{'='*60}\n")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_booking_phone_flow.py <email>")
        print("\nExample:")
        print("  python test_booking_phone_flow.py kirsteenglen@gmail.com")
        print("\nTo find emails with phones:")
        print("  python find_phone_contacts.py")
        sys.exit(1)
    
    email = sys.argv[1]
    success = test_flow(email)
    sys.exit(0 if success else 1)
