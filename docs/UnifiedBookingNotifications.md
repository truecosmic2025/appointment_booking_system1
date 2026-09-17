# Unified Booking Notifications

The multi-coach calendar application is the **single sender** of booking notices. It sends separate messages to the booked coach, the visitor, `admin@truecosmic.com`, and `info@truecosmic.com`. A configured owner also retains the existing individual internal notice when that address differs from the fixed recipients.

The visitor’s booking confirmation remains unchanged. Internal messages add a **Claudde conversation summary** only when the CRM can identify exactly one recent completed Claudde conversation for the booking email or E.164 telephone number. The application never adds the summary to the visitor’s message. If CRM is unreachable, the context migration is unavailable, the secret is absent, or no unambiguous match is found, calendar confirmation proceeds normally without a summary.

## Required calendar environment

The calendar service owner must verify these variables directly in Railway before deploying or testing this release.

| Variable | Required value or purpose |
| --- | --- |
| `EMAIL_ENABLED` | `true` |
| Mail transport | Configure one supported route: SMTP, Resend, SendGrid, or MailerSend. Existing production values are retained. |
| `BOOKING_CONTEXT_PROXY_URL` | The deployed CRM `claudde-bot-proxy` Edge Function URL. |
| `BOOKING_CONTEXT_PROXY_SECRET` | A new high-entropy secret shared **only** with the CRM `BOOKING_CONTEXT_PROXY_SECRET` function secret. It must not equal `CLAUDDE_BOT_PROXY_SECRET`. |
| `BOOKING_CONTEXT_TIMEOUT_SEC` | Optional; defaults to `3`, with a maximum of `8`. |

The existing Google OAuth and coach credential configuration are untouched. No booking or user database column has been renamed, retyped, or removed.

## CRM prerequisite

Apply the CRM migration:

```text
supabase/migrations/20260916221500_claudde_booking_context_lookup.sql
```

Then deploy the matching `claudde-bot-proxy` function and add the same `BOOKING_CONTEXT_PROXY_SECRET` to that function’s secrets. The function only accepts this secret for the `get_summary_by_contact` operation. It does not grant the calendar access to chat transcripts, message payloads, bot settings, or write operations.

## Removal of retired integrations

The booking route no longer performs the retired chatbot contact lookup or post-booking synchronization. The historic configurable administrator-recipient setting and its legacy `app.py` notification helper are also removed. The calendar’s notification recipients are now explicit and reviewable in `app/coach/public.py`.

Existing non-email contact and automation updates remain separate best-effort integration work. They are not used as the email notification sender.

## Validation

Run the isolated regression test before review:

```bash
python3 scripts/test_unified_booking_notifications.py
```

The final deployment test must use a real booking after a real Claudde conversation with the same email or phone. Confirm that the coach, `admin@truecosmic.com`, and `info@truecosmic.com` each receive **one** email with the confirmed appointment time and the summary. Repeat with a new visitor who has no Claudde history and confirm that booking still succeeds and the notices contain no summary block.
