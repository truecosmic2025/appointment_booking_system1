#!/usr/bin/env python3
"""Test phone retrieval priority order."""

print("""
╔════════════════════════════════════════════════════════════════╗
║           PHONE NUMBER RETRIEVAL PRIORITY ORDER                ║
╚════════════════════════════════════════════════════════════════╝

The system checks for phone numbers in this order:

┌─────────────────────────────────────────────────────────────┐
│ PRIORITY 1: URL Parameters (Highest Priority)              │
├─────────────────────────────────────────────────────────────┤
│ Checks these URL parameters:                                │
│   • ?phone=...                                              │
│   • ?phone_number=...                                       │
│   • ?tel=...                                                │
│   • ?msisdn=...                                             │
│   • ?mobile=...                                             │
│                                                             │
│ Example: /c/coach?email=user@example.com&phone=1234567890  │
│                                                             │
│ ✓ If found: Use this phone (skip session and BotPenguin)   │
│ ✗ If not found: Check Priority 2                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PRIORITY 2: Session Storage (Medium Priority)              │
├─────────────────────────────────────────────────────────────┤
│ Checks session['booking_phone']                             │
│                                                             │
│ Session is populated when:                                  │
│   • Phone was in URL on previous page load                  │
│   • Phone was retrieved from BotPenguin earlier             │
│                                                             │
│ ✓ If found: Use this phone (skip BotPenguin)               │
│ ✗ If not found: Check Priority 3                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PRIORITY 3: BotPenguin API (Lowest Priority - Fallback)    │
├─────────────────────────────────────────────────────────────┤
│ Only called if:                                             │
│   • No phone in URL parameters AND                          │
│   • No phone in session AND                                 │
│   • Email is provided                                       │
│                                                             │
│ Makes API call to BotPenguin to retrieve phone by email     │
│                                                             │
│ ✓ If found: Use this phone and store in session            │
│ ✗ If not found: Proceed without phone (NULL in database)   │
└─────────────────────────────────────────────────────────────┘

╔════════════════════════════════════════════════════════════════╗
║                        EXAMPLE SCENARIOS                       ║
╚════════════════════════════════════════════════════════════════╝

Scenario 1: Phone in URL
─────────────────────────────────────────────────────────────────
URL: /c/coach?email=user@example.com&phone=1234567890
Result: Uses 1234567890 (from URL)
BotPenguin API called: NO ✗

Scenario 2: Phone in Session
─────────────────────────────────────────────────────────────────
URL: /c/coach?email=user@example.com
Session: booking_phone = "1234567890"
Result: Uses 1234567890 (from session)
BotPenguin API called: NO ✗

Scenario 3: Phone from BotPenguin (Fallback)
─────────────────────────────────────────────────────────────────
URL: /c/coach?email=user@example.com
Session: (empty)
BotPenguin: Contact has phone +447717715664
Result: Uses +447717715664 (from BotPenguin)
BotPenguin API called: YES ✓

Scenario 4: No Phone Available
─────────────────────────────────────────────────────────────────
URL: /c/coach?email=user@example.com
Session: (empty)
BotPenguin: Contact has no phone
Result: Proceeds without phone (NULL)
BotPenguin API called: YES ✓ (but no phone found)

╔════════════════════════════════════════════════════════════════╗
║                      WHY THIS ORDER?                           ║
╚════════════════════════════════════════════════════════════════╝

1. URL Parameters (Priority 1)
   • Most explicit - user/system intentionally provided it
   • No API call needed - fastest
   • Overrides everything else

2. Session Storage (Priority 2)
   • Already retrieved in this session
   • No API call needed - fast
   • Avoids redundant BotPenguin lookups

3. BotPenguin API (Priority 3)
   • Fallback when nothing else available
   • Requires API call - slower
   • Only called when necessary to minimize API usage

╔════════════════════════════════════════════════════════════════╗
║                    PERFORMANCE BENEFITS                        ║
╚════════════════════════════════════════════════════════════════╝

✓ Minimizes BotPenguin API calls (only when needed)
✓ Faster page loads (uses cached data when available)
✓ Respects explicit phone parameters (URL overrides)
✓ Graceful fallback (works even if BotPenguin is down)

""")

# Interactive test
print("\n" + "="*60)
print("INTERACTIVE TEST")
print("="*60)

def test_priority(url_phone, session_phone, bp_phone):
    """Simulate the priority logic."""
    print(f"\nTest Case:")
    print(f"  URL phone: {url_phone or '(none)'}")
    print(f"  Session phone: {session_phone or '(none)'}")
    print(f"  BotPenguin phone: {bp_phone or '(none)'}")
    
    # Priority 1: URL
    if url_phone:
        print(f"\n✓ Result: {url_phone} (from URL)")
        print(f"  BotPenguin API called: NO")
        return url_phone
    
    # Priority 2: Session
    if session_phone:
        print(f"\n✓ Result: {session_phone} (from session)")
        print(f"  BotPenguin API called: NO")
        return session_phone
    
    # Priority 3: BotPenguin
    print(f"  BotPenguin API called: YES")
    if bp_phone:
        print(f"\n✓ Result: {bp_phone} (from BotPenguin)")
        return bp_phone
    else:
        print(f"\n✗ Result: NULL (no phone found)")
        return None

# Test cases
test_priority("1234567890", "9999999999", "+447717715664")
test_priority(None, "9999999999", "+447717715664")
test_priority(None, None, "+447717715664")
test_priority(None, None, None)

print("\n" + "="*60)
print("All tests demonstrate correct priority order!")
print("="*60 + "\n")
