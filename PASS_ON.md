# TrueCosmic Calendar: Complete Upgrade Package

This archive is a clean source snapshot of the `feat/owner-coach-invites` branch at commit `faffdee` (`Add owner-managed coach invitations`). It contains the complete application source, including the preceding required-phone booking fix at commit `9ab422c`.

## Included upgrades

The public booking flow now requires a valid phone number for every new booking. The app validates the phone in the browser and on the server, stores it in the existing `booking.visitor_phone` field, and does not fall back to a stale session phone number.

Coach accounts are invitation-only after the first owner account exists. Owners can issue an email-backed, seven-day, one-time invitation from the owner dashboard. Invitation tokens are stored only as SHA-256 hashes, are bound to the invited email, cannot be reused, and are invalidated when an invitation is reissued for the same address.

## Included handoff materials

The archive includes `docs/REQUIRED_PHONE_BOOKING_HANDOFF.md` and `docs/COACH_INVITATION_HANDOFF.md`, plus `deployment/truecosmic-calendar-security-upgrades.patch`. The deployment patch applies both commits on top of the repository's prior `main` revision.

## Validation completed

The following commands passed before packaging:

```bash
python3 -m unittest -v tests/test_coach_invites.py
python3 -m unittest -v tests/test_required_booking_phone.py
python3 scripts/test_unified_booking_notifications.py
```

## Deployment note

The source snapshot is ready to review, commit, and deploy. GitHub publishing was not completed because the configured account received a 403 permission error for `truecosmic2025/appointment_booking_system1`; no remote branch, pull request, or live deployment was created.
