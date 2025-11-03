BotPenguin Contact Integration

Overview
- **Phone Retrieval**: When a user arrives at the booking page with an email (via URL parameter), the app attempts to retrieve their phone number from BotPenguin and auto-fill it.
- **Booking Sync**: After a successful booking, the app looks up the invitee by email in BotPenguin and updates:
  - booking_time: meeting date-time in invitee’s time zone (ISO 8601)
  - demo_session_coach: coach name

Environment
- Required variables (set in Railway Variables and/or .env locally):
  - BOTPENGUIN_API_KEY
  - BOTPENGUIN_BOT_ID
  - BOTPENGUIN_PLATFORM=website
- Optional overrides if your account uses different endpoints:
  - BOTPENGUIN_BASE_URL=https://api.botpenguin.com
  - BOTPENGUIN_SEARCH_PATH=/api/v2/contacts/search
  - BOTPENGUIN_UPDATE_PATH=/api/v2/contacts/{contact_id}

Files
- app/integrations/botpenguin_service.py: lightweight client with phone retrieval and booking sync
- app/coach/public.py: retrieves phone on page load and booking; triggers sync after booking
- app/templates/coaches/booking.html: sends timezone to server
- test_phone_retrieval.py: test script to verify phone retrieval
- requirements.txt: adds requests

Verification
- **Phone Retrieval**: Visit booking page with email parameter (e.g., `/c/coach-slug?email=user@example.com`). Check logs for "Retrieved phone from BotPenguin".
- **Test Script**: Run `python test_phone_retrieval.py user@example.com` to verify phone retrieval.
- **Booking Sync**: Make a test booking; check server logs for: "BotPenguin: updated contact <id>".
- Confirm the contact in BotPenguin shows booking_time and demo_session_coach.

Notes
- Phone retrieval and sync are best-effort and non-blocking; bookings will still succeed if BotPenguin is unreachable.
- Phone numbers are retrieved from BotPenguin v7 API structure: `profile.userDetails.contact.phone.number` (with optional prefix).
- Fallback checks include: direct phone fields, phoneNumber, phone_number, mobile, and attributes array.
- When BotPenguin sends users to your booking page, ensure the URL includes the email parameter for phone auto-fill to work.
- Example URL: `https://yourdomain.com/c/coach-slug?email=user@example.com&name=John+Doe`
