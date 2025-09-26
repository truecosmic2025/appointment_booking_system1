BotPenguin Contact Update

Overview
- After a successful booking, the app looks up the invitee by email in BotPenguin and updates:
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
- app/integrations/botpenguin_service.py: lightweight client + sync helper
- app/coach/public.py: triggers sync after booking; stores timezone from request
- app/templates/coaches/booking.html: sends timezone to server
- requirements.txt: adds requests

Verification
- Make a test booking; check server logs for: "BotPenguin: updated contact <id>".
- Confirm the contact in BotPenguin shows booking_time and demo_session_coach.

Notes
- Sync is best-effort and non-blocking; bookings will still succeed if BotPenguin is unreachable.
