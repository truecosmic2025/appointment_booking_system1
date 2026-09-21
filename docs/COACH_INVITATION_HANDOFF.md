# Owner-Managed Coach Invitations

## What changed

New coach accounts are now **invitation-only**. Once the app has an owner account, opening `/auth/register` without a current invitation shows an access-required message and does not present an account form. The original first-account bootstrap remains available only while the user table is empty; it creates the initial owner account exactly as before.

An owner can create coach invitations from **Dashboard → Invite a coach**. The form collects the coach’s name and email address, creates a high-entropy one-time registration link, and attempts delivery through the app’s configured email provider. The link is tied to the invited email address and expires after **seven days**. The dashboard shows a newly created link once for manual copying if email delivery is unavailable, as well as a list of pending invitations.

## Coach onboarding steps

A coach opens the emailed invitation link, creates a password, and selects a time zone. The account is created with the `host` role. The coach then signs in, opens **Account**, selects **Connect Google Calendar**, and configures availability. After Google Calendar is connected, their public booking address is available as `https://calendar.truecosmic.com/c/<coach-slug>`; it can be copied from the coach directory.

## Security behavior

The app stores only a SHA-256 digest of each invitation token, not the raw token. An invitation cannot be reused after account creation. An invitation also cannot be accepted for a different email address. When an owner re-invites the same address, the earlier unused invitation is revoked immediately. The owner-only invite action has a per-session CSRF token, and only the `owner` role can create invitations. Administrators can see the main dashboard but cannot issue invitations.

## Deployment requirements

Deploy the application normally. The existing `db.create_all()` startup path creates the new `coach_invite` table automatically. No existing table or Google OAuth setting is changed. Confirm that the production email configuration is still enabled; if email delivery cannot be configured, the owner may copy the one-time link shown immediately after creating an invite and send it through an approved internal channel.

## Production verification

After deployment, sign in as an owner and create an invitation for a controlled test email. Confirm that `/auth/register` is locked without the invitation, the invitation link prefills and locks the invited email, the completed account has the `host` role, and using the same link again is rejected. Confirm that the new coach can sign in, connect Google Calendar, save availability, and receive a working `/c/<slug>` booking link.
