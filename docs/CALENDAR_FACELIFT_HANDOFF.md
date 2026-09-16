# TrueCosmic Calendar facelift — deployment handoff

> **New Railway migration: none.** This release contains **no schema migration and no data migration**. Do not run an `ALTER TABLE` statement for this release. In particular, `CoachProfile.google_credentials` and every existing `booking` and `user` column remain untouched.

## What changed

This release modernizes the existing Flask/Jinja2 calendar application in place. It replaces the runtime Tailwind CDN with a compiled, minified Tailwind 3 stylesheet and a reusable, responsive component layer. The visual direction uses the existing repository’s cosmic logo as the source of the plum/lilac palette, with a high-contrast serif display face and a deliberately restrained card system. The implementation is CSS-only from a branding perspective; no scheduling, authentication, or Google Calendar behavior has been redesigned.

The coach dashboard now includes an eight-week booking-request trend, a 30-day cancellation rate, a clear Google Calendar status card, and the next 25 booked appointments grouped by local day. It continues to expose the existing reschedule, cancel, and Google Meet actions.

The owner dashboard now includes an organisation-wide eight-week booking-request trend, per-coach eight-week mini trends, request and upcoming-session counts, a named list of active coaches without a Google Calendar connection, and a day-grouped week-at-a-glance schedule. The meetings report now includes an `All coaches` / individual coach filter and retains that filter while paging and switching time-zone display.

## Files changed or added

| Area | Files |
| --- | --- |
| Application routes | `app/dashboard/routes.py`, `app/admin/routes.py` |
| Shared layout and pages | `app/templates/base.html`, `app/templates/dashboard/host.html`, `app/templates/dashboard/owner.html`, `app/templates/admin/meetings_report.html`, `app/templates/admin/users.html`, `app/templates/coach/settings.html`, `app/templates/coaches/booking.html` |
| Styling and frontend build | `app/static/css/tailwind-input.css` (new), `app/static/css/tailwind.css` (compiled output, new), `app/static/css/custom.css`, `tailwind.config.js` (new), `package.json` (new), `package-lock.json` (new) |
| Container/build support | `Dockerfile`, `.dockerignore` (new), `.gitignore` |
| Verification and handoff | `scripts/test_calendar_facelift.py` (new), `scripts/seed_preview.py` (new), `docs/UI_VALIDATION_NOTES.md` (new), `docs/CALENDAR_FACELIFT_HANDOFF.md` (new) |

## Protected integration and data contract

No Google OAuth connect/callback code changed: `app/google/routes.py` is not modified. No Google service implementation changed: `app/integrations/google_service.py` is not modified. The `CoachProfile` model/schema is not modified, and this release performs **no write** to `CoachProfile.google_credentials`; dashboards only read the existing value to display connection state.

The `Booking` and `User` models/schema are not modified. None of the CRM synchronization fields were renamed, retyped, or removed: `visitor_name`, `visitor_email`, `visitor_phone`, `start_utc`, `end_utc`, `status`, `call_status`, `timezone`, `coach_id`, `user.name`, and `user.email`. No CRM, Twilio, WhatsApp, ElevenLabs, Supabase, or reminder code is added or changed.

## Build and deployment steps

The repository Dockerfile now has a Node build stage that runs `npm ci` and `npm run build:css` before the production Python image is built. Railway deployments that use this Dockerfile need no extra build command.

If the Railway service is instead configured to use a non-Docker build command, run the following before starting the Flask/Gunicorn service:

```bash
npm ci
npm run build:css
pip install -r requirements.txt
```

There are **no new environment variables** for this release. The optional Supabase confirmation/no-show analytics is deliberately deferred to phase 2 because it needs a separately scoped, read-only Supabase integration. If that phase is approved later, add a dedicated scoped Supabase project URL and read-only key in Railway; do not hardcode them.

## Validation completed before handoff

The focused regression script was run against an isolated temporary SQLite database, not Railway. It validates coach and owner dashboard rendering, Google-connection-gap rendering, coach report filtering, public booking-page rendering, the generated Tailwind asset, and the invariant that rendering never changes a stored `google_credentials` JSON value.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/test_calendar_facelift.py
python -m compileall -q app
npm run build:css
```

A seeded local preview was rendered in a browser at desktop size and the public booking page was captured at **375 × 812**. The mobile capture confirmed a single-column layout, readable fields/actions, and no clipping. Full observations are recorded in `docs/UI_VALIDATION_NOTES.md`.

## Required live Railway smoke test

Do this **after** the branch is deployed, using an existing connected coach and a non-production test visitor record. This must be performed on `calendar.truecosmic.com`; it has not been run from this isolated development environment because it would use a real coach token and create a live Google event.

1. Log in as an already Google-connected coach. Confirm the coach dashboard opens and the Google Calendar card says **Connected**, without any consent or reconnect prompt.
2. Open that coach’s existing `/c/<slug>` page. Confirm time slots still load normally.
3. Make one real test booking using the approved test visitor. Confirm the booking persists, a Google Calendar event is created, and a Google Meet link is returned.
4. Confirm the booked session appears on the coach dashboard and in the owner week-at-a-glance view.
5. Log in as owner/admin. Confirm the named Google-connection-gap list and per-coach filter in **Reports** return expected data.
6. Check the CRM’s next `sync-railway-bookings` run and the WhatsApp/voice reminder monitor. The code path is unchanged, so the sanity check should only confirm the existing cross-system sync continues to see the unchanged booking/user columns.

## Phase 2 explicitly not included

Confirmation, no-show, WhatsApp, and voice-call outcomes remain outside this deployment. Surfacing them requires an independent, read-only Supabase API integration with scoped credentials, an agreed matching key between the two systems, failure-mode handling, and a separate review. No such environment variable or credential has been introduced here.

## Brand note

The current repository contains the circular cosmic/logo asset and the public TrueCosmic site confirms the transformation/coaching tone, but no CRM theme-token source was available in the connected environment. The plum palette is derived from that checked-in logo (`#693B9B` primary, with lilac neutrals) rather than invented arbitrarily. Confirm the exact CRM palette with Michael before treating these tokens as permanent; adjusting `tailwind.config.js` is a one-file, behavior-free change.
