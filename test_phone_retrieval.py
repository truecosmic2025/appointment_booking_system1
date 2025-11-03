#!/usr/bin/env python3
"""Test script to verify phone retrieval from BotPenguin."""

import sys
from dotenv import load_dotenv
load_dotenv()

from app.integrations.botpenguin_service import get_phone_from_botpenguin

def test_phone_retrieval(email: str):
    """Test retrieving phone number for a given email."""
    print(f"\n=== Testing phone retrieval for: {email} ===")
    
    phone = get_phone_from_botpenguin(email)
    
    if phone:
        print(f"✓ Phone found: {phone}")
        return True
    else:
        print(f"✗ No phone found")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_phone_retrieval.py <email>")
        print("Example: python test_phone_retrieval.py user@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    success = test_phone_retrieval(email)
    sys.exit(0 if success else 1)
