#!/usr/bin/env python3
"""Find contacts with phone numbers."""

import json

with open('botpenguin_list_response.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

contacts = data.get('data', [])
print(f"Total contacts: {len(contacts)}\n")

contacts_with_phone = []
for c in contacts:
    phone_num = c.get('profile', {}).get('userDetails', {}).get('contact', {}).get('phone', {}).get('number', '').strip()
    email = c.get('profile', {}).get('userDetails', {}).get('contact', {}).get('email', '').strip()
    
    if phone_num:
        contacts_with_phone.append((email, phone_num))

print(f"Contacts with phone: {len(contacts_with_phone)}\n")

if contacts_with_phone:
    print("Contacts with phone numbers:")
    for email, phone in contacts_with_phone[:10]:
        print(f"  {email or '(no email)'} | {phone}")
else:
    print("No contacts found with phone numbers in this page")
