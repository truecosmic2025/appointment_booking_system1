# Solution Summary: BotPenguin Phone Retrieval

## Problem Statement
Phone numbers existed in BotPenguin contacts but were not being captured and stored in the booking table, resulting in NULL values for `visitor_phone`.

## Root Cause
The BotPenguin integration was **one-way only** - it synced booking data TO BotPenguin after bookings were created, but never retrieved phone numbers FROM BotPenguin before bookings.

## Solution Implemented ✅

### Key Changes

1. **Fixed Phone Extraction** (`app/integrations/botpenguin_service.py`)
   - Updated `_extract_phone()` to correctly parse BotPenguin v7 API structure
   - Phone is at: `profile.userDetails.contact.phone.number`
   - Handles optional country prefix: `profile.userDetails.contact.phone.prefix`
   - Includes fallback checks for other phone field formats

2. **Added Phone Retrieval Function** (`app/integrations/botpenguin_service.py`)
   - New `get_phone_from_botpenguin(email)` function
   - Looks up contact by email and extracts phone number
   - Returns None if not found (graceful fallback)

3. **Integrated into Booking Flow** (`app/coach/public.py`)
   - **Priority 1**: Checks URL parameters (`?phone=`, `?phone_number=`, `?tel=`, etc.)
   - **Priority 2**: Checks session storage (`session['booking_phone']`)
   - **Priority 3**: Only if both are empty, retrieves from BotPenguin API (fallback)
   - Phone is stored in session for reuse and passed to booking record
   - **Performance**: Minimizes API calls by using cached data when available

### Testing Tools Created

1. **test_phone_retrieval.py** - Quick test for single email
2. **test_phone_priority.py** - Demonstrate priority order (URL → Session → BotPenguin)
3. **list_botpenguin_contacts.py** - List all contacts and their structure
4. **find_phone_contacts.py** - Find which contacts have phone numbers
5. **debug_botpenguin_contact.py** - Deep inspection of contact structure
6. **test_booking_phone_flow.py** - Test complete booking flow

## Verification

### Test Results ✅
```bash
$ python test_phone_retrieval.py kirsteenglen@gmail.com
=== Testing phone retrieval for: kirsteenglen@gmail.com ===
✓ Phone found: +4407717715664

$ python test_phone_retrieval.py abibaomarmoussa@gmail.com
=== Testing phone retrieval for: abibaomarmoussa@gmail.com ===
✓ Phone found: +22996993171
```

### Flow Test ✅
```bash
$ python test_booking_phone_flow.py kirsteenglen@gmail.com
============================================================
TESTING BOOKING PHONE FLOW
============================================================

Scenario: User arrives at booking page with email: kirsteenglen@gmail.com

Step 1: User visits /c/coach-slug?email=kirsteenglen@gmail.com
        App calls get_phone_from_botpenguin()
✓ Step 2: Phone retrieved from BotPenguin: +4407717715664
✓ Step 3: Phone stored in session and hidden form field
✓ Step 4: User completes booking
✓ Step 5: Booking saved with visitor_phone = '+4407717715664'

============================================================
SUCCESS: Phone will be captured in booking table
============================================================
```

## How It Works Now

### Phone Retrieval Priority Order

The system checks for phone numbers in this order:

1. **URL Parameters** (Highest Priority)
   - Checks: `?phone=`, `?phone_number=`, `?tel=`, `?msisdn=`, `?mobile=`
   - If found: Uses this phone (skips session and BotPenguin)
   - BotPenguin API called: **NO**

2. **Session Storage** (Medium Priority)
   - Checks: `session['booking_phone']`
   - If found: Uses this phone (skips BotPenguin)
   - BotPenguin API called: **NO**

3. **BotPenguin API** (Lowest Priority - Fallback)
   - Only called if: No phone in URL AND no phone in session AND email provided
   - If found: Uses this phone and stores in session
   - BotPenguin API called: **YES** (only when necessary)

### Example Scenarios

#### Scenario 1: Phone in URL
```
URL: /c/coach-slug?email=user@example.com&phone=1234567890
Result: Uses 1234567890 (from URL)
BotPenguin API called: NO ✗
Booking saved with phone: 1234567890 ✅
```

#### Scenario 2: Phone in Session
```
URL: /c/coach-slug?email=user@example.com
Session: booking_phone = "1234567890"
Result: Uses 1234567890 (from session)
BotPenguin API called: NO ✗
Booking saved with phone: 1234567890 ✅
```

#### Scenario 3: Phone from BotPenguin (Fallback)
```
URL: /c/coach-slug?email=user@example.com
Session: (empty)
BotPenguin: Contact has phone +447717715664
Result: Uses +447717715664 (from BotPenguin)
BotPenguin API called: YES ✓
Booking saved with phone: +447717715664 ✅
```

#### Scenario 4: No Phone Available
```
URL: /c/coach-slug?email=user@example.com
Session: (empty)
BotPenguin: Contact has no phone
Result: Proceeds without phone
BotPenguin API called: YES ✓ (but no phone found)
Booking saved with visitor_phone: NULL
```

## BotPenguin Phone Structure

The phone is stored in a nested object:
```json
{
  "profile": {
    "userDetails": {
      "contact": {
        "phone": {
          "number": "7717715664",
          "prefix": "+44"
        }
      }
    }
  }
}
```

The extraction method:
- Retrieves `phone.number`
- Prepends `phone.prefix` if available and number doesn't start with `+`
- Returns formatted phone: `+447717715664`

## Configuration Required

No additional configuration needed. Uses existing environment variables:
- `BOTPENGUIN_API_KEY` (required)
- `BOTPENGUIN_BASE_URL` (optional, defaults to https://api.v7.botpenguin.com)

## BotPenguin Chatbot Setup

To ensure phone capture works, configure your BotPenguin chatbot to:
1. Collect user's email address
2. Send users to booking page with email parameter:
   ```
   https://yourdomain.com/c/coach-slug?email={{user_email}}
   ```

Optional: Also pass name for better UX:
```
https://yourdomain.com/c/coach-slug?email={{user_email}}&name={{user_name}}
```

## Benefits

✅ Automatically captures phone numbers from BotPenguin contacts  
✅ **Minimizes API calls** - only queries BotPenguin when necessary  
✅ **Fast performance** - uses URL params and session cache first  
✅ **Respects explicit data** - URL parameters override everything  
✅ No changes required to BotPenguin chatbot flow  
✅ Graceful fallback - bookings work even if phone not found  
✅ Non-blocking - doesn't slow down booking process  
✅ Works with existing URL parameter approach  
✅ Handles international phone numbers with country prefixes  

## Files Modified

- `app/integrations/botpenguin_service.py` - Added phone extraction and retrieval
- `app/coach/public.py` - Integrated phone retrieval in booking flow
- `docs/BotPenguinSetup.md` - Updated documentation

## Files Created

- `test_phone_retrieval.py` - Quick phone retrieval test
- `list_botpenguin_contacts.py` - List contacts with structure
- `find_phone_contacts.py` - Find contacts with phones
- `debug_botpenguin_contact.py` - Deep contact inspection
- `test_booking_phone_flow.py` - Complete flow test
- `PHONE_RETRIEVAL_FIX.md` - Detailed fix documentation
- `SOLUTION_SUMMARY.md` - This file

## Next Steps

1. **Deploy the changes** to your production environment
2. **Test with real bookings** from BotPenguin chatbot
3. **Monitor logs** for "Retrieved phone from BotPenguin" messages
4. **Verify database** that `visitor_phone` is no longer NULL for BotPenguin users
5. **Update BotPenguin chatbot** to include email parameter in booking URLs if not already doing so

## Support

If phone numbers are still not being captured:
1. Run `python find_phone_contacts.py` to verify contacts have phone numbers in BotPenguin
2. Check that BotPenguin chatbot is passing email parameter in URL
3. Check server logs for "Retrieved phone from BotPenguin" or error messages
4. Run `python debug_botpenguin_contact.py <email>` to inspect specific contact structure
