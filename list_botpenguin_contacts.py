#!/usr/bin/env python3
"""List first few BotPenguin contacts to understand structure."""

import json
from dotenv import load_dotenv
load_dotenv()

from app.integrations.botpenguin_service import BotPenguinClient

def list_contacts():
    """List first page of contacts."""
    print("\n=== Listing BotPenguin Contacts ===\n")
    
    try:
        client = BotPenguinClient()
        print("✓ BotPenguin client initialized\n")
    except Exception as e:
        print(f"✗ Failed to initialize client: {e}")
        return
    
    # Make a direct API call to list contacts
    import requests
    url = client._url(client.list_path)
    body = dict(client._base_body)
    body["page"] = 1
    
    print(f"Requesting: {url}")
    print(f"Headers: {client._headers()}\n")
    
    try:
        r = requests.post(url, headers=client._headers(), json=body, timeout=30)
        print(f"Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"Error response: {r.text[:500]}")
            return
        
        data = r.json() if r.content else {}
        
        # Save response
        with open("botpenguin_list_response.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✓ Response saved to: botpenguin_list_response.json\n")
        
        # Extract contacts
        contacts = None
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                contacts = data["data"]
            elif isinstance(data.get("users"), list):
                contacts = data["users"]
            elif isinstance(data.get("contacts"), list):
                contacts = data["contacts"]
        
        if not contacts:
            print("Could not find contacts in response")
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            return
        
        print(f"Found {len(contacts)} contacts\n")
        
        # Show first contact structure
        if contacts:
            print("=" * 60)
            print("FIRST CONTACT STRUCTURE:")
            print("=" * 60)
            print(json.dumps(contacts[0], indent=2, ensure_ascii=False)[:2000])
            print("=" * 60)
            
            # Try to extract email and phone from first contact
            first = contacts[0]
            email = client._extract_email(first)
            phone = client._extract_phone(first)
            
            print(f"\nFirst contact:")
            print(f"  Email: {email if email else '(not found)'}")
            print(f"  Phone: {phone if phone else '(not found)'}")
            
            # Show all emails
            print(f"\nAll contact emails:")
            for i, contact in enumerate(contacts[:10], 1):
                email = client._extract_email(contact)
                phone = client._extract_phone(contact)
                print(f"  {i}. {email if email else '(no email)'} | Phone: {phone if phone else '(no phone)'}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    list_contacts()
