#!/usr/bin/env python3
"""Check phone number formats from BotPenguin."""

import json

with open('botpenguin_list_response.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

contacts = data.get('data', [])
print("Sample phone formats from BotPenguin:\n")

count = 0
for c in contacts:
    phone_obj = c.get('profile', {}).get('userDetails', {}).get('contact', {}).get('phone', {})
    number = phone_obj.get('number', '').strip()
    prefix = phone_obj.get('prefix', '').strip()
    
    if number:
        count += 1
        email = c.get('profile', {}).get('userDetails', {}).get('contact', {}).get('email', '').strip()
        print(f"{count}. Email: {email or '(no email)'}")
        print(f"   Number: {number}")
        print(f"   Prefix: {prefix or '(none)'}")
        
        # What our code returns
        if prefix and not number.startswith("+"):
            combined = f"{prefix}{number}"
        else:
            combined = number
        print(f"   Stored as: {combined}")
        print()
        
        if count >= 5:
            break

print(f"\nTotal contacts with phone: {sum(1 for c in contacts if c.get('profile', {}).get('userDetails', {}).get('contact', {}).get('phone', {}).get('number', '').strip())}")
