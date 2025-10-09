Admin Email Notifications

This app can notify owners/admins by email when a booking is created, rescheduled, or cancelled.

Setup

- Configure SMTP in your `.env`:
  - `EMAIL_ENABLED=true`
  - `SMTP_HOST=...`
  - `SMTP_PORT=587`
  - `SMTP_USERNAME=...`
  - `SMTP_PASSWORD=...`
  - `SMTP_USE_TLS=true`
  - `EMAIL_FROM=notifications@yourdomain.com`
- Set the admin recipients (comma-separated):
  - `ADMIN_EMAILS=owner1@example.com,owner2@example.com`
- (Optional) Secure admin routes with an admin token (used for reschedule/cancel):
  - `ADMIN_TOKEN=some-secret`

Endpoints

- Booking creation notifications are sent automatically when a user submits the booking form.
- Reschedule a booking (admin-only):
  - `POST /admin/bookings/<booking_id>/reschedule`
  - form fields: `token` (if `ADMIN_TOKEN` set), `date` (YYYY-MM-DD), `time` (HH:MM 24-hr), `tz` (IANA name, optional)
- Cancel a booking (admin-only):
  - `POST /admin/bookings/<booking_id>/cancel`
  - form fields: `token` (if `ADMIN_TOKEN` set)

Attendee Reschedule (Public)

- Users can reschedule with a signed tokenized link and the public endpoint:
  - `POST /meet/bookings/<booking_id>/reschedule`
  - form fields: `token` (required), `date` (YYYY-MM-DD), `time` (HH:MM 24-hr), `tz` (optional IANA tz)
- The token is an HMAC derived from the booking id and creation time using your `SECRET_KEY`. You can generate it server-side as needed to build links in emails.
- When attendee reschedules, the linked Google Calendar event is updated and admins receive a notification.

Notes

- Notifications are non-blocking; failures do not affect user flow.
- Times in emails are formatted in the booking’s timezone.
- Booking cancellations now use a soft status (`status=cancelled`) when supported by the DB; slots ignore cancelled bookings.
- Google Calendar updates for reschedule/cancel are not performed by these endpoints.
  - However, Google-side edits are detected via polling if enabled (see below) and will soft-cancel or reschedule locally.

Polling Google Calendar Changes (Delta Sync)

- The app can poll Google Calendar for changes every few minutes and keep bookings in sync.
- Configure interval (optional): `GOOGLE_SYNC_INTERVAL_MINUTES=2` (default 2 minutes).
- Logging: set `LOG_LEVEL=DEBUG` in `.env` for verbose sync logs.
- Behavior:
  - Reschedules on Google update the corresponding booking and notify admins.
  - Cancellations on Google remove the booking and notify admins.
  - Only events created by this app are tracked (mapped by event id).
