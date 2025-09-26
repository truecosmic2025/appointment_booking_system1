import os
import json
from datetime import datetime, timedelta, timezone, time
import secrets

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import current_user

from app import db
from app.models.user import User
from app.models.coach_profile import CoachProfile
from app.models.booking import Booking
from app.models.coach_settings import CoachSettings
from app.integrations.google_service import list_freebusy, create_event_with_meet, cancel_event, reschedule_event


public_bp = Blueprint("public", __name__, url_prefix="")


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
    return render_template("coaches/booking.html", coach=coach, profile=profile, hours=hours)


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

    # Send emails (coach, visitor, owner)
    send_booking_email(coach.email, owner.email if owner else None, email, coach.name, name, start, meet_link, booking)

    # Best-effort BotPenguin sync
    try:
        import pytz
        from app.integrations.botpenguin_service import sync_booking_to_botpenguin
        try:
            tz = pytz.timezone(tzname)
            start_local = start.astimezone(tz)
        except Exception:
            start_local = start
        sync_booking_to_botpenguin(visitor_email=email, booking_time_local_iso=start_local.isoformat(), coach_name=coach.name)
    except Exception:
        pass

    return jsonify({"ok": True, "meet_link": meet_link, "manage_url": url_for('public.manage_booking', booking_id=booking.id, token=token, _external=True)})


def send_email(subject: str, body: str, to_emails: list[str]):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER')
    pwd = os.getenv('SMTP_PASS')
    sender = os.getenv('MAIL_FROM', user)

    if not (host and user and pwd and sender):
        # Skip actual sending in dev if not configured
        return

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = ", ".join(to_emails)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, pwd)
        server.sendmail(sender, to_emails, msg.as_string())


def send_booking_email(coach_email, owner_email, visitor_email, coach_name, visitor_name, start, meet_link, booking):
    subject = f"Booking confirmed: {visitor_name} with {coach_name}"
    manage = url_for('public.manage_booking', booking_id=booking.id, token=booking.token, _external=True)
    body = (
        f"Your 30-minute session is booked.\n\n"
        f"Coach: {coach_name}\nVisitor: {visitor_name}\n"
        f"Start (UTC): {start.isoformat()}\nMeet: {meet_link}\n\n"
        f"Manage: {manage} (reschedule or cancel)\n"
    )
    recipients = [coach_email, visitor_email]
    if owner_email:
        recipients.append(owner_email)
    send_email(subject, body, recipients)


@public_bp.route("/booking/<int:booking_id>/<token>")
def manage_booking(booking_id: int, token: str):
    b = db.session.get(Booking, booking_id)
    if not b or b.token != token:
        flash("Invalid booking link", "error")
        return redirect(url_for('main.index'))
    profile = CoachProfile.query.filter_by(user_id=b.coach_id).first()
    return render_template("coaches/manage.html", booking=b, coach=b.coach, profile=profile)


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
    db.session.commit()
    # Notify
    owner = User.query.filter_by(role="owner").first() or User.query.filter_by(role="admin").first()
    subject = f"Booking cancelled: {b.visitor_name} x {b.coach.name}"
    body = f"The session scheduled at {b.start_utc.isoformat()} (UTC) has been cancelled."
    send_email(subject, body, [b.coach.email, b.visitor_email] + ([owner.email] if owner else []))
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
    body = f"The session has been moved to {b.start_utc.isoformat()} (UTC)."
    send_email(subject, body, [b.coach.email, b.visitor_email] + ([owner.email] if owner else []))
    return jsonify({'ok': True})
