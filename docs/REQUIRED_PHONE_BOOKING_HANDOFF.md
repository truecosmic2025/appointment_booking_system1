# Required Phone Number for Public Bookings

## Delivered change

The public booking page at `/c/<slug>` now presents a visible **Phone number** field for every visitor, including both direct calendar visitors and visitors arriving from a Claudde Bot handoff such as `?name=<visitorName>`. The browser requires a value and performs basic phone-format validation before it submits the booking request. The booking API independently rejects a missing or whitespace-only `phone` value with the inline response message **“Phone number is required to book a session.”**

The API no longer uses a saved `booking_phone` session value as a fallback. Therefore, a hidden, stale, or absent session value cannot create a new booking without an explicitly submitted phone number. Phone numbers supplied in the request continue to use the existing normalization routine and are saved to the existing `booking.visitor_phone` column.

## Explicitly unchanged

This change does not alter the `Booking` schema, Google OAuth routes, `CoachProfile.google_credentials`, availability computation, buffer or notice-window logic, Google Calendar event creation, or the CRM confirmation pipeline. Existing bookings are neither modified nor deleted.

## Existing bookings requiring manual follow-up

Bookings created before this change with an empty `visitor_phone` will not be recovered automatically. The reported examples include **Rajiv Test**, two **Nica** bookings, and **Paris Jones**, dated 19 September 2026 and later. Michael or staff must manually contact these visitors and handle any required confirmation follow-up. The optional missing-phone indicator on the host and owner dashboards was intentionally not included, to keep this emergency validation fix limited to the public booking flow.

## Production verification after deployment

Create a non-production test booking through the raw `/c/<slug>` link and through a `?name=...` handoff link. In each case, an empty phone must be blocked and a valid phone must produce a booking row with a non-empty `visitor_phone`. After the next `sync-railway-bookings` cycle (up to 30 minutes), confirm that the test booking has an `appointment_confirmations` record. Confirm that the existing coach Google Calendar connection and event creation continue to operate normally.
