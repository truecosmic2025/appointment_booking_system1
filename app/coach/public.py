import os
import json
from datetime import datetime, timedelta, timezone, time
import secrets

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from contextlib import nullcontext
from flask_login import current_user

from app import db
from app.models.user import User
from app.models.coach_profile import CoachProfile
from app.models.booking import Booking
from app.models.coach_settings import CoachSettings
from app.integrations.google_service import list_freebusy, create_event_with_meet, cancel_event, reschedule_event
import logging
import threading
import requests


public_bp = Blueprint("public", __name__, url_prefix="")


def send_make_booking_event(webhook_url: str, coach_name: str, booking_time_iso: str, user_timezone: str, email: str) -> None:
    """Post booking info to Make.com webhook. Best-effort, non-blocking."""
    logger = logging.getLogger(__name__)
    try:
        payload = {
            "demo_session_coach": coach_name,
            "booking_time": booking_time_iso,
            "timezone": user_timezone,
            "email": email,
        }
        requests.post(webhook_url, json=payload, timeout=10)
        logger.info("Make.com webhook posted successfully")
    except Exception as e:
        logger.error(f"Make.com webhook failed: {type(e).__name__}: {e}")


def _tz_for_user_email(email: str) -> str | None:
    try:
        u = User.query.filter_by(email=email).first()
        if not u:
            return None
        # First check User timezone, then fall back to CoachProfile
        if hasattr(u, 'timezone') and u.timezone:
            return u.timezone
        prof = CoachProfile.query.filter_by(user_id=u.id).first()
        if prof and prof.timezone:
            return prof.timezone
    except Exception:
        pass
    return None

def _format_dt_for_tz(dt: datetime, tzname: str | None) -> tuple[str, str]:
    """Return (formatted, tzname_used)."""
    try:
        import pytz
        aware = dt
        if getattr(dt, 'tzinfo', None) is None:
            aware = dt.replace(tzinfo=timezone.utc)
        tzn = tzname or 'UTC'
        local = aware.astimezone(pytz.timezone(tzn))
        return local.strftime('%Y-%m-%d %H:%M'), tzn
    except Exception:
        try:
            return dt.strftime('%Y-%m-%d %H:%M'), tzname or 'UTC'
        except Exception:
            return str(dt), tzname or 'UTC'

@public_bp.route("/coaches")
def coaches_list():
    # List all users with role host (and owner/admin who might also be coaches)
    users = (
        User.query.filter(User.role.in_(["host", "owner", "admin"]))
        .order_by(User.name.asc())
        .all()
    )
    profiles = {p.user_id: p for p in CoachProfile.query.filter(CoachProfile.user_id.in_([u.id for u in users])).all()}
    return render_template("coaches/list.html", users=users, profiles=profiles)


@public_bp.route("/c/<slug>")
def coach_page(slug):
    import json
    profile = CoachProfile.query.filter_by(slug=slug).first_or_404()
    coach = profile.user
    settings = CoachSettings.query.filter_by(user_id=coach.id).first()
    hours = {}
    if settings and settings.working_hours:
        try:
            hours = json.loads(settings.working_hours)
        except Exception:
            hours = {}
    
    # Get query parameters for pre-filling the form
    prefill_name = request.args.get('name', '').strip()
    prefill_email = request.args.get('email', '').strip()
    
    return render_template("coaches/booking.html", coach=coach, profile=profile, hours=hours,
                         prefill_name=prefill_name, prefill_email=prefill_email)


def _parse_iso(s: str) -> datetime:
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s)


def _default_hours():
    # Mon-Fri 09:00-17:00
    return {
        'mon': [["09:00","17:00"]],
        'tue': [["09:00","17:00"]],
        'wed': [["09:00","17:00"]],
        'thu': [["09:00","17:00"]],
        'fri': [["09:00","17:00"]],
    }


@public_bp.route("/api/availability/<slug>")
def api_availability(slug):
    profile = CoachProfile.query.filter_by(slug=slug).first_or_404()
    if not profile.google_credentials:
        return jsonify({"slots": []})

    day_str = request.args.get("date")  # YYYY-MM-DD
    try:
        day = datetime.strptime(day_str, "%Y-%m-%d").date() if day_str else datetime.utcnow().date()
    except ValueError:
        day = datetime.utcnow().date()
    # Load settings
    settings = CoachSettings.query.filter_by(user_id=profile.user_id).first()
    try:
        import pytz
        tzname = profile.timezone or 'UTC'
        tz = pytz.timezone(tzname)
    except Exception:
        tz = timezone.utc
        tzname = 'UTC'

    hours = _default_hours()
    if settings and settings.working_hours:
        try:
            import json
            parsed = json.loads(settings.working_hours)
            if isinstance(parsed, dict):
                hours = parsed
        except Exception:
            pass

    min_notice = timedelta(minutes=(settings.min_notice_min if settings else 120))
    buffer = timedelta(minutes=(settings.buffer_min if settings else 0))
    max_days = settings.max_days_ahead if settings else 30

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    if (day - now_utc.date()).days > max_days:
        return jsonify({"slots": []})

    # Determine weekday key
    weekday_keys = ['mon','tue','wed','thu','fri','sat','sun']
    wk = weekday_keys[day.weekday()]
    ranges = hours.get(wk, [])
    if not ranges:
        return jsonify({"slots": []})

    # Build start/end window to query freebusy (in UTC)
    def _local_dt(d, hhmm):
        h, m = map(int, hhmm.split(':'))
        return datetime(d.year, d.month, d.day, h, m)

    try:
        import pytz
        local_slots = []
        for start_hhmm, end_hhmm in ranges:
            local_start = pytz.timezone(tzname).localize(_local_dt(day, start_hhmm))
            local_end = pytz.timezone(tzname).localize(_local_dt(day, end_hhmm))
            local_slots.append((local_start, local_end))
        window_start_utc = min(ls[0] for ls in local_slots).astimezone(timezone.utc)
        window_end_utc = max(ls[1] for ls in local_slots).astimezone(timezone.utc)
    except Exception:
        # Fallback to full day UTC and a single local slot in UTC
        start_utc = datetime.combine(day, time(9,0)).replace(tzinfo=timezone.utc)
        end_utc = datetime.combine(day, time(17,0)).replace(tzinfo=timezone.utc)
        window_start_utc = start_utc
        window_end_utc = end_utc
        local_slots = [(start_utc, end_utc)]

    busy = list_freebusy(profile.google_credentials, window_start_utc, window_end_utc)
    busy_intervals = []
    for b in busy:
        b_start = _parse_iso(b['start'])
        b_end = _parse_iso(b['end'])
        busy_intervals.append((b_start - buffer, b_end + buffer))

    # Generate 30-min slots across all working ranges
    slots = []
    for local_start, local_end in local_slots:
        slot = local_start
        while slot + timedelta(minutes=30) <= local_end:
            slot_utc = slot.astimezone(timezone.utc)
            # Apply min notice
            if slot_utc < now_utc + min_notice:
                slot += timedelta(minutes=30)
                continue
            end_utc = slot_utc + timedelta(minutes=30)
            # check overlap
            overlap = False
            for b_start, b_end in busy_intervals:
                if not (end_utc <= b_start or slot_utc >= b_end):
                    overlap = True
                    break
            if not overlap:
                slots.append(slot_utc.isoformat())
            slot += timedelta(minutes=30)

    return jsonify({"slots": slots, "timezone": tzname})


@public_bp.route("/api/book/<slug>", methods=["POST"]) 
def api_book(slug):
    profile = CoachProfile.query.filter_by(slug=slug).first_or_404()
    coach = profile.user
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    start_iso = data.get("start")
    tzname = (data.get("timezone") or "UTC").strip() or "UTC"
    if not (name and email and start_iso):
        return jsonify({"error": "Missing fields"}), 400

    start = datetime.fromisoformat(start_iso)
    end = start + timedelta(minutes=30)

    # Create Google Calendar event with Meet link
    attendees = [
        {"email": coach.email},
        {"email": email},
    ]
    # Add owner/admin as attendee (owner preferred)
    owner = User.query.filter_by(role="owner").first() or User.query.filter_by(role="admin").first()
    if owner and owner.email not in [a['email'] for a in attendees]:
        attendees.append({"email": owner.email})

    event_id, meet_link = create_event_with_meet(
        profile.google_credentials,
        summary=f"Coaching: {coach.name} x {name}",
        start=start,
        end=end,
        attendees=attendees,
        description=f"Booking via TrueCosmic Calendar. Coach: {coach.name}. Visitor: {name} ({email}).",
    )

    token = secrets.token_hex(16)
    booking = Booking(
        coach_id=coach.id,
        visitor_name=name,
        visitor_email=email,
        start_utc=start,
        end_utc=end,
        timezone=tzname,
        status="booked",
        google_event_id=event_id,
        meet_link=meet_link,
        token=token,
    )
    db.session.add(booking)
    db.session.commit()

    # Capture primitives to avoid DetachedInstanceError in background thread
    coach_email_val = coach.email
    owner_email_val = owner.email if owner else None
    visitor_email_val = email
    coach_name_val = coach.name
    visitor_name_val = name
    booking_id_val = booking.id
    booking_token_val = token
    visitor_timezone_val = tzname
    start_val = start
    meet_link_val = meet_link
    try:
        from flask import request as _rq
        base_url_val = (_rq.url_root or '').rstrip('/')
    except Exception:
        base_url_val = None

    # Kick off post-booking tasks (email + integrations) in a background thread
    app_obj = None
    try:
        # Capture a real app object to use app context in the background thread
        app_obj = current_app._get_current_object()
    except Exception:
        app_obj = None

    def _post_booking_tasks():
        try:
            # Ensure Flask application context inside background thread
            ctx_mgr = app_obj.app_context() if app_obj is not None else nullcontext()
            with ctx_mgr:
                # Send emails (coach, visitor, owner)
                try:
                    send_booking_email(
                        coach_email_val,
                        owner_email_val,
                        visitor_email_val,
                        coach_name_val,
                        visitor_name_val,
                        start_val,
                        meet_link_val,
                        booking_id_val,
                        booking_token_val,
                        visitor_timezone_val,
                        base_url_val,
                    )
                except Exception as e:
                    logging.getLogger(__name__).error("send_booking_email failed: %s: %s", type(e).__name__, e)

                # Best-effort BotPenguin + ManyChat + Make.com webhook
                try:
                    import pytz
                    from app.integrations.botpenguin_service import sync_booking_to_botpenguin
                    from app.integrations.manychat_service import sync_booking_to_manychat
                    try:
                        tz = pytz.timezone(visitor_timezone_val)
                        start_local = start_val.astimezone(tz)
                    except Exception:
                        start_local = start_val
                    # Compute UTC ISO for ManyChat field
                    try:
                        start_utc_iso = start_val.astimezone(pytz.UTC).isoformat()
                    except Exception:
                        start_utc_iso = start_val.isoformat()
                    try:
                        sync_booking_to_botpenguin(visitor_email=visitor_email_val, booking_time_local_iso=start_local.isoformat(), coach_name=coach_name_val)
                    except Exception as e:
                        logging.getLogger(__name__).warning("BotPenguin sync failed: %s: %s", type(e).__name__, e)
                    try:
                        logging.getLogger(__name__).info(
                            "ManyChat: syncing visitor=%s coach=%s time_utc=%s",
                            visitor_email_val,
                            coach_name_val,
                            start_utc_iso,
                        )
                        sync_booking_to_manychat(
                            visitor_email=visitor_email_val,
                            booking_time_utc_iso=start_utc_iso,
                            coach_name=coach_name_val,
                            visitor_name=visitor_name_val,
                        )
                    except Exception as e:
                        logging.getLogger(__name__).warning("ManyChat sync failed: %s: %s", type(e).__name__, e)
                    # After ManyChat: sync contact to FluentCRM
                    try:
                        from app.integrations.fluentcrm_service import sync_contact_to_fluentcrm
                        logging.getLogger(__name__).info("FluentCRM: syncing contact email=%s name=%s", email, name)
                        sync_contact_to_fluentcrm(email, name)
                    except Exception as e:
                        logging.getLogger(__name__).warning("FluentCRM sync failed: %s: %s", type(e).__name__, e)

                    # Send Make.com webhook if configured
                    try:
                        webhook_url = os.getenv("MAKE_WEBHOOK_URL", "").strip()
                        if webhook_url:
                            send_make_booking_event(webhook_url, coach_name_val, start_local.isoformat(), visitor_timezone_val, visitor_email_val)
                    except Exception as e:
                        logging.getLogger(__name__).warning("Make.com webhook failed: %s: %s", type(e).__name__, e)
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger(__name__).exception("Post-booking tasks error: %s", e)

    try:
        sync_mode = os.getenv('SYNC_POST_BOOKING', '0').lower() in ('1','true','yes')
        if sync_mode:
            # Even in synchronous mode, cap how long we block the request thread
            # to avoid Gunicorn timeouts under slow external APIs.
            try:
                budget_sec = int(os.getenv('POST_BOOKING_SYNC_BUDGET_SEC', '8'))
            except Exception:
                budget_sec = 8
            logging.getLogger(__name__).info(
                "Running post-booking tasks with budget=%ss (SYNC_POST_BOOKING=1)",
                budget_sec,
            )
            t = threading.Thread(target=_post_booking_tasks, daemon=True)
            t.start()
            t.join(timeout=budget_sec)
            if t.is_alive():
                logging.getLogger(__name__).warning(
                    "Post-booking tasks exceeded budget; continuing in background"
                )
        else:
            threading.Thread(target=_post_booking_tasks, daemon=True).start()
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to dispatch post-booking tasks: %s: %s", type(e).__name__, e)

    # Build a relative manage URL for the API response to avoid proxy/scheme issues
    try:
        manage_url = url_for('public.manage_booking', booking_id=booking.id, token=token)
    except Exception:
        manage_url = f"/booking/{booking.id}/{token}"

    return jsonify({"ok": True, "meet_link": meet_link, "manage_url": manage_url})


def send_email(subject: str, body: str, to_emails: list[str]):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    logger = logging.getLogger(__name__)

    # Respect standard env names with fallbacks for older keys
    email_enabled = (os.getenv('EMAIL_ENABLED', 'false').lower() == 'true')
    if not email_enabled:
        return

    # Configure sender meta
    sender = os.getenv('EMAIL_FROM') or os.getenv('MAIL_FROM') or (os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER'))
    sender_name = os.getenv('EMAIL_FROM_NAME', '').strip()
    if not sender:
        # Nothing configured; skip silently in dev
        return

    # Detect available HTTP providers (prefer HTTP API in PaaS environments where SMTP may be blocked)
    sendgrid_key = os.getenv('SENDGRID_API_KEY', '').strip()
    resend_key = os.getenv('RESEND_API_KEY', '').strip()
    mailersend_key = os.getenv('MAILERSEND_API_TOKEN', '').strip()
    transport = (os.getenv('EMAIL_TRANSPORT', 'auto').strip().lower() or 'auto')  # auto|smtp|api

    def _send_via_http_provider() -> bool:
        try:
            headers = {"Accept": "application/json"}
            timeout = float(os.getenv('EMAIL_HTTP_TIMEOUT_SEC', '10'))
            # RESEND
            if resend_key:
                headers["Authorization"] = f"Bearer {resend_key}"
                payload = {
                    "from": f"{sender_name} <{sender}>" if sender_name else sender,
                    "to": to_emails,
                    "subject": subject,
                    "text": body,
                }
                r = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=timeout)
                if 200 <= r.status_code < 300:
                    logger.info("Email: sent via Resend to %s", ",".join(to_emails))
                    return True
                logger.info("Resend send failed: %s %s", r.status_code, (r.text or '')[:300])
            # SENDGRID
            if sendgrid_key:
                headers = {
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json",
                }
                content = [{"type": "text/plain", "value": body}]
                tos = [{"email": e} for e in to_emails]
                payload = {
                    "personalizations": [{"to": tos}],
                    "from": {"email": sender, **({"name": sender_name} if sender_name else {})},
                    "subject": subject,
                    "content": content,
                }
                r = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=timeout)
                if r.status_code in (200, 202):
                    logger.info("Email: sent via SendGrid to %s", ",".join(to_emails))
                    return True
                logger.info("SendGrid send failed: %s %s", r.status_code, (r.text or '')[:300])
            # MAILERSEND
            if mailersend_key:
                headers = {
                    "Authorization": f"Bearer {mailersend_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "from": {"email": sender, **({"name": sender_name} if sender_name else {})},
                    "to": [{"email": e} for e in to_emails],
                    "subject": subject,
                    "text": body,
                }
                r = requests.post("https://api.mailersend.com/v1/email", json=payload, headers=headers, timeout=timeout)
                if 200 <= r.status_code < 300:
                    logger.info("Email: sent via MailerSend to %s", ",".join(to_emails))
                    return True
                logger.info("MailerSend send failed: %s %s", r.status_code, (r.text or '')[:300])
        except Exception as e:
            logger.info("Email HTTP provider error: %s: %s", type(e).__name__, e)
        return False

    # If transport prefers API and a provider is configured, try it first
    if transport in ('api', 'http') and (sendgrid_key or resend_key or mailersend_key):
        if _send_via_http_provider():
            return

    # Otherwise, attempt SMTP (may be blocked on some PaaS)
    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER')
    pwd = os.getenv('SMTP_PASSWORD') or os.getenv('SMTP_PASS')
    use_tls = (os.getenv('SMTP_USE_TLS', 'true').lower() == 'true')
    debug_level = int(os.getenv('SMTP_DEBUG', '0') or '0')

    if host and user and pwd:
        msg = MIMEMultipart()
        msg['From'] = f"{sender_name} <{sender}>" if sender_name else sender
        msg['To'] = ", ".join(to_emails)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Use SMTP_SSL for port 465, SMTP with starttls for other ports
        # Use short network timeouts to avoid blocking request threads
        smtp_timeout = float(os.getenv('SMTP_TIMEOUT_SEC', '8'))
        try:
            logger.info("SMTP: sending to %s via %s:%s as %s", ",".join(to_emails), host, port, sender)
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=smtp_timeout) as server:
                    if debug_level:
                        server.set_debuglevel(debug_level)
                    server.login(user, pwd)
                    server.sendmail(sender, to_emails, msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=smtp_timeout) as server:
                    if debug_level:
                        server.set_debuglevel(debug_level)
                    if use_tls:
                        server.starttls()
                    server.login(user, pwd)
                    server.sendmail(sender, to_emails, msg.as_string())
            logger.info("SMTP: sent successfully to %s", ",".join(to_emails))
            return
        except Exception as e:
            logger.error("SMTP send failed: %s: %s", type(e).__name__, e)
            # If API providers are available and transport is auto, try fallback via HTTP
            if transport == 'auto' and (sendgrid_key or resend_key or mailersend_key):
                if _send_via_http_provider():
                    return
            # else, give up silently (best-effort)
            return

    # No SMTP configured; if API available, try it
    if _send_via_http_provider():
        return
    # Nothing could send; log and exit
    logger.info("Email: no available transport configured; skipped sending to %s", ",".join(to_emails))


def send_booking_email(coach_email, owner_email, visitor_email, coach_name, visitor_name, start, meet_link, booking_id: int, booking_token: str, visitor_timezone: str | None, base_url: str | None = None):
    subject = f"Booking confirmed: {visitor_name} with {coach_name}"

    # Build an absolute manage URL when possible; gracefully fall back
    def _manage_url():
        # Prefer explicit base_url captured from the request, if provided
        if base_url:
            return base_url.rstrip('/') + f"/booking/{booking_id}/{booking_token}"
        try:
            return url_for('public.manage_booking', booking_id=booking_id, token=booking_token, _external=True)
        except RuntimeError:
            # No request context or SERVER_NAME; compose path manually and prefix with base URL if provided
            base = os.getenv('PUBLIC_BASE_URL') or os.getenv('APP_URL') or os.getenv('EXTERNAL_BASE_URL')
            path = f"/booking/{booking_id}/{booking_token}"
            if base:
                return base.rstrip('/') + path
            return path

    manage = _manage_url()

    # Helper to make details block per timezone
    def details_for(tzname: str | None):
        start_str, used_tz = _format_dt_for_tz(start, tzname)
        return (
            f"Coach: {coach_name}\n"
            f"Visitor: {visitor_name}\n"
            f"Start: {start_str} ({used_tz})\n"
            f"Meet: {meet_link}\n\n"
            f"Manage: {manage} (reschedule or cancel)\n"
        )

    # Build recipients
    raw_admins = os.getenv('ADMIN_EMAILS', '')
    admin_emails = [e.strip() for e in raw_admins.split(',') if e.strip()]

    # Participants: send individually with their timezone
    participant_order = [coach_email, visitor_email] + ([owner_email] if owner_email else [])
    sent_set = set()
    for e in participant_order:
        if not e:
            continue
        el = e.lower()
        if el in sent_set:
            continue
        sent_set.add(el)
        # Determine tz
        if e == visitor_email:
            tzname = visitor_timezone
        elif e == coach_email:
            tzname = _tz_for_user_email(coach_email)
        elif owner_email and e == owner_email:
            tzname = _tz_for_user_email(owner_email)
        else:
            tzname = None
        body = "A 30-minute session is booked.\n\n" + details_for(tzname)
        send_email(subject, body, [e])

    # Admin recipients: send individually using their timezone, with admin phrasing
    for e in admin_emails:
        el = e.lower()
        if not el or el in sent_set:
            continue
        tzname = _tz_for_user_email(e)
        body = "A demo session has been booked.\n\n" + details_for(tzname)
        send_email(subject, body, [e])


@public_bp.route("/booking/<int:booking_id>/<token>")
def manage_booking(booking_id: int, token: str):
    b = db.session.get(Booking, booking_id)
    if not b or b.token != token:
        flash("Invalid booking link", "error")
        return redirect(url_for('main.index'))
    profile = CoachProfile.query.filter_by(user_id=b.coach_id).first()
    
    # Format booking time in visitor's timezone
    visitor_tz = b.timezone or 'UTC'
    start_local_str, tz_used = _format_dt_for_tz(b.start_utc, visitor_tz)
    
    return render_template("coaches/manage.html", booking=b, coach=b.coach, profile=profile,
                         start_local_str=start_local_str, visitor_tz=tz_used)


@public_bp.route("/booking/<int:booking_id>/<token>/cancel", methods=["POST"])
def cancel_booking(booking_id: int, token: str):
    b = db.session.get(Booking, booking_id)
    if not b or b.token != token:
        return jsonify({"error": "Invalid"}), 400
    if b.status == 'cancelled':
        return jsonify({"ok": True})
    profile = CoachProfile.query.filter_by(user_id=b.coach_id).first()
    if b.google_event_id:
        cancel_event(profile.google_credentials, b.google_event_id)
    b.status = 'cancelled'
    # Clear joinable artifacts from the record so UIs don't show them
    b.meet_link = None
    b.google_event_id = None
    db.session.commit()
    # Notify
    owner = User.query.filter_by(role="owner").first() or User.query.filter_by(role="admin").first()
    subject = f"Booking cancelled: {b.visitor_name} x {b.coach.name}"
    raw_admins = os.getenv('ADMIN_EMAILS', '')
    admin_emails = [e.strip() for e in raw_admins.split(',') if e.strip()]

    def cancel_body_for(tzname: str | None):
        s, used = _format_dt_for_tz(b.start_utc, tzname)
        return f"The session scheduled at {s} ({used}) has been cancelled."

    sent = set()
    # Coach
    coach_tz = _tz_for_user_email(b.coach.email)
    send_email(subject, cancel_body_for(coach_tz), [b.coach.email])
    sent.add(b.coach.email.lower())
    # Visitor
    send_email(subject, cancel_body_for(b.timezone), [b.visitor_email])
    sent.add(b.visitor_email.lower())
    # Owner
    if owner and owner.email and owner.email.lower() not in sent:
        owner_tz = _tz_for_user_email(owner.email)
        send_email(subject, cancel_body_for(owner_tz), [owner.email])
        sent.add(owner.email.lower())
    # Admins
    for e in admin_emails:
        el = e.lower()
        if not el or el in sent:
            continue
        tzname = _tz_for_user_email(e)
        send_email(subject, cancel_body_for(tzname), [e])
        sent.add(el)
    return jsonify({"ok": True})


@public_bp.route("/booking/<int:booking_id>/<token>/reschedule", methods=["POST"])
def reschedule_booking(booking_id: int, token: str):
    b = db.session.get(Booking, booking_id)
    if not b or b.token != token:
        return jsonify({"error": "Invalid"}), 400
    data = request.get_json(force=True)
    start_iso = data.get('start')
    if not start_iso:
        return jsonify({'error': 'Missing start'}), 400
    new_start = datetime.fromisoformat(start_iso)
    new_end = new_start + timedelta(minutes=30)
    profile = CoachProfile.query.filter_by(user_id=b.coach_id).first()
    if b.google_event_id:
        reschedule_event(profile.google_credentials, b.google_event_id, new_start, new_end)
    b.start_utc = new_start
    b.end_utc = new_end
    db.session.commit()
    owner = User.query.filter_by(role="owner").first() or User.query.filter_by(role="admin").first()
    subject = f"Booking rescheduled: {b.visitor_name} x {b.coach.name}"
    raw_admins = os.getenv('ADMIN_EMAILS', '')
    admin_emails = [e.strip() for e in raw_admins.split(',') if e.strip()]

    def resched_body_for(tzname: str | None):
        s, used = _format_dt_for_tz(b.start_utc, tzname)
        return f"The session has been moved to {s} ({used})."

    sent = set()
    # Coach
    coach_tz = _tz_for_user_email(b.coach.email)
    send_email(subject, resched_body_for(coach_tz), [b.coach.email])
    sent.add(b.coach.email.lower())
    # Visitor
    send_email(subject, resched_body_for(b.timezone), [b.visitor_email])
    sent.add(b.visitor_email.lower())
    # Owner
    if owner and owner.email and owner.email.lower() not in sent:
        owner_tz = _tz_for_user_email(owner.email)
        send_email(subject, resched_body_for(owner_tz), [owner.email])
        sent.add(owner.email.lower())
    # Admins
    for e in admin_emails:
        el = e.lower()
        if not el or el in sent:
            continue
        tzname = _tz_for_user_email(e)
        send_email(subject, resched_body_for(tzname), [e])
        sent.add(el)
    return jsonify({'ok': True})
