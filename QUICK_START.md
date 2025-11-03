# Quick Start: Phone Retrieval Fix

## ✅ Problem Fixed
Phone numbers from BotPenguin are now automatically retrieved and stored in bookings.

## 🧪 Test It Works

### Quick Test (30 seconds)
```bash
# Find an email with a phone number
python find_phone_contacts.py

# Test phone retrieval with that email
python test_phone_retrieval.py <email>

# See the priority order in action
python test_phone_priority.py
```

### Example
```bash
$ python test_phone_retrieval.py kirsteenglen@gmail.com
✓ Phone found: +4407717715664

$ python test_phone_priority.py
Shows how URL → Session → BotPenguin priority works
```

## 🚀 How to Use

### Phone Retrieval Priority

The system checks for phone in this order:
1. **URL parameters** (e.g., `?phone=1234567890`) - Highest priority
2. **Session storage** - If phone was retrieved earlier
3. **BotPenguin API** - Only as fallback (minimizes API calls)

### For BotPenguin Chatbot Users

**Option 1: Include phone in URL (Recommended - Fastest)**
```
https://yourdomain.com/c/coach-slug?email={{user_email}}&phone={{user_phone}}
```
✓ No API call needed - instant  
✓ Most reliable

**Option 2: Include only email (Uses BotPenguin API)**
```
https://yourdomain.com/c/coach-slug?email={{user_email}}
```
✓ App retrieves phone from BotPenguin automatically  
✓ Requires API call (slightly slower)

### For Direct Bookings
When users enter their email and submit a booking:
1. Checks session for phone (from previous page load)
2. If not in session, checks BotPenguin for their phone
3. Includes it if found
4. Proceeds normally if not found

## 📊 Verify It's Working

### Check Logs
Look for these messages in your server logs:
```
Retrieved phone from BotPenguin for <email>
BotPenguin: retrieved phone for <email>
```

### Check Database
Query your booking table:
```sql
SELECT visitor_email, visitor_phone 
FROM booking 
WHERE visitor_phone IS NOT NULL 
ORDER BY created_at DESC 
LIMIT 10;
```

You should see phone numbers populated for bookings from BotPenguin users.

## 🔧 Troubleshooting

### Phone still NULL?

**1. Check if contact has phone in BotPenguin**
```bash
python debug_botpenguin_contact.py <email>
```

**2. Check if email parameter is passed**
- Verify BotPenguin chatbot includes `?email=` in booking URL
- Check browser URL when user arrives at booking page

**3. Check server logs**
- Look for "Retrieved phone from BotPenguin" messages
- Look for any BotPenguin-related errors

**4. Verify BotPenguin API key**
- Check `.env` file has `BOTPENGUIN_API_KEY`
- Test API connection: `python list_botpenguin_contacts.py`

## 📝 What Changed

### Files Modified
- `app/integrations/botpenguin_service.py` - Phone extraction logic
- `app/coach/public.py` - Phone retrieval integration
- `docs/BotPenguinSetup.md` - Updated documentation

### New Test Scripts
- `test_phone_retrieval.py` - Test single email
- `find_phone_contacts.py` - Find contacts with phones
- `list_botpenguin_contacts.py` - List all contacts
- `test_booking_phone_flow.py` - Test complete flow

## ✨ No Configuration Needed

The fix uses your existing BotPenguin configuration:
- `BOTPENGUIN_API_KEY` ✅
- `BOTPENGUIN_BASE_URL` (optional) ✅

## 🎯 Expected Results

### Before Fix
```
visitor_phone: NULL (even though phone exists in BotPenguin)
```

### After Fix
```
visitor_phone: +4407717715664 (retrieved from BotPenguin)
```

## 📞 Support

If you need help:
1. Run the test scripts to diagnose the issue
2. Check the detailed documentation in `SOLUTION_SUMMARY.md`
3. Review `PHONE_RETRIEVAL_FIX.md` for technical details

---

**Status**: ✅ Fixed and Tested  
**Version**: 1.0  
**Date**: November 3, 2025
