# Phone Number Retrieval Fix

## Problem
Phone numbers existed in BotPenguin contacts but were not being captured and stored in the booking table, resulting in NULL values for `visitor_phone`.

## Root Cause
The BotPenguin integration was **one-way** - it only synced booking data TO BotPenguin after a booking was created, but never retrieved phone numbers FROM BotPenguin before the booking.

## Solution Implemented

### 1. Added Phone Extraction Method
**File**: `app/integrations/botpenguin_service.py`
- Added `_extract_phone()` method to BotPenguinClient
- Searches multiple phone field locations in priority order:
  - **Primary**: `profile.userDetails.contact.phone.number` (BotPenguin v7 API format)
  - **With prefix**: Combines `phone.prefix` + `phone.number` if prefix exists
  - **Fallback**: Direct fields like `phone`, `phoneNumber`, `phone_number`, `mobile`
  - **Attributes**: Checks attributes array for phone-related keys

### 2. Created Phone Retrieval Function
**File**: `app/integrations/botpenguin_service.py`
- Added `get_phone_from_botpenguin(email)` function
- Looks up contact by email and extracts phone number
- Returns None if not found (graceful fallback)

### 3. Integrated Phone Retrieval in Booking Flow
**File**: `app/coach/public.py`

#### On Booking Page Load (`/c/<slug>`)
- When email is provided via URL parameter (e.g., `?email=user@example.com`)
- Attempts to retrieve phone from BotPenguin
- Auto-fills phone in hidden field if found
- Stores in session for persistence

#### On Booking Submission (`/api/book/<slug>`)
- If phone not provided in request or session
- Attempts to retrieve from BotPenguin using visitor email
- Stores retrieved phone in booking record

### 4. Added Test Script
**File**: `test_phone_retrieval.py`
- Command-line tool to test phone retrieval
- Usage: `python test_phone_retrieval.py user@example.com`

### 5. Updated Documentation
**File**: `docs/BotPenguinSetup.md`
- Updated title to "BotPenguin Contact Integration"
- Added phone retrieval overview
- Added verification steps for phone retrieval
- Added notes about URL parameter requirements

## How It Works

### Scenario 1: User Arrives from BotPenguin
1. BotPenguin chatbot sends user to: `/c/coach-slug?email=user@example.com`
2. App retrieves phone from BotPenguin contact
3. Phone is auto-filled (hidden field) and stored in session
4. User completes booking with phone automatically included

### Scenario 2: Direct Booking
1. User visits booking page directly
2. Enters name and email
3. On submission, app checks BotPenguin for phone
4. Phone is included in booking if found

## Testing

### Manual Test
1. Visit: `/c/your-coach-slug?email=test@example.com`
2. Check server logs for: "Retrieved phone from BotPenguin"
3. Complete booking
4. Verify `visitor_phone` is not NULL in database

### Script Test
```bash
# Test with an email that exists in BotPenguin
python test_phone_retrieval.py test@example.com

# List all contacts to find emails with phone numbers
python list_botpenguin_contacts.py

# Find which contacts have phone numbers
python find_phone_contacts.py
```

Expected output:
```
=== Testing phone retrieval for: test@example.com ===
✓ Phone found: +1234567890
```

## Benefits
- ✅ Captures phone numbers from BotPenguin contacts automatically
- ✅ No changes required to BotPenguin chatbot flow
- ✅ Graceful fallback - bookings still work if phone not found
- ✅ Non-blocking - doesn't slow down booking process
- ✅ Works with existing URL parameter approach

## Configuration
No additional configuration needed. Uses existing:
- `BOTPENGUIN_API_KEY`
- `BOTPENGUIN_BASE_URL` (optional)
- `BOTPENGUIN_LIST_PATH` (optional)
