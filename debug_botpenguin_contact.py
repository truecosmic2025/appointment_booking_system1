#!/usr/bin/env python3
"""Debug script to inspect BotPenguin contact structure."""

import sys
import json
from dotenv import load_dotenv
load_dotenv()

from app.integrations.botpenguin_service import BotPenguinClient

def debug_contact(email: str):
    """Fetch and display full contact structure."""
    print(f"\n=== Debugging BotPenguin contact for: {email} ===\n")
    
    try:
        client = BotPenguinClient()
        print("✓ BotPenguin client initialized")
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        return
    
    print(f"Searching for contact with email: {email}")
    contact = client.find_contact_by_email(email)
    
    if not contact:
        print(f"✗ No contact found for {email}")
        return
    
    print(f"✓ Contact found!\n")
    
    # Save full contact to file
    filename = f"contact_{email.replace('@', '_at_').replace('.', '_')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(contact, f, indent=2, ensure_ascii=False)
    print(f"Full contact data saved to: {filename}\n")
    
    # Display contact structure
    print("=" * 60)
    print("CONTACT STRUCTURE:")
    print("=" * 60)
    print(json.dumps(contact, indent=2, ensure_ascii=False))
    print("=" * 60)
    
    # Try to extract email
    extracted_email = client._extract_email(contact)
    print(f"\nExtracted email: {extracted_email}")
    
    # Try to extract phone
    extracted_phone = client._extract_phone(contact)
    print(f"Extracted phone: {extracted_phone if extracted_phone else '(not found)'}")
    
    # Show where to look for phone
    print("\n" + "=" * 60)
    print("PHONE FIELD ANALYSIS:")
    print("=" * 60)
    
    def check_path(obj, path):
        """Check if a path exists in the object."""
        current = obj
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    phone_paths = [
        ["phone"],
        ["phoneNumber"],
        ["phone_number"],
        ["mobile"],
        ["profile", "phone"],
        ["profile", "phoneNumber"],
        ["profile", "userDetails", "contact", "phone"],
        ["profile", "userDetails", "contact", "phoneNumber"],
    ]
    
    for path in phone_paths:
        value = check_path(contact, path)
        path_str = " -> ".join(path)
        if value:
            print(f"✓ Found at {path_str}: {value}")
        else:
            print(f"✗ Not at {path_str}")
    
    # Check attributes
    print("\nChecking attributes array:")
    attrs = (
        contact.get("profile", {})
        .get("userDetails", {})
        .get("attributes", [])
    )
    
    if isinstance(attrs, list) and attrs:
        print(f"Found {len(attrs)} attributes:")
        for attr in attrs:
            if isinstance(attr, dict):
                key = attr.get("key", "")
                value = attr.get("value", "")
                print(f"  - {key}: {value}")
    else:
        print("No attributes array found or empty")
    
    # Check all top-level keys
    print("\n" + "=" * 60)
    print("ALL TOP-LEVEL KEYS:")
    print("=" * 60)
    if isinstance(contact, dict):
        for key in contact.keys():
            print(f"  - {key}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_botpenguin_contact.py <email>")
        print("Example: python debug_botpenguin_contact.py user@example.com")
        sys.exit(1)
    
    email = sys.argv[1]
    debug_contact(email)
