from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required, current_user
from email_validator import EmailNotValidError, validate_email

from app import db
from app.models import User, Booking, CoachInvite, CoachProfile
from app.auth.routes import roles_required


dash_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def _weekly_windows(now, weeks=8):
    """Return ISO-week starts for a compact, consistently ordered trend."""
    current_week = now.date() - timedelta(days=now.weekday())
    return [current_week - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]


def _make_weekly_trend(rows, now, weeks=8, coach_id=None):
    """Build booking-request volume from existing Booking.created_at data only."""
    week_starts = _weekly_windows(now, weeks)
    counts = {week_start: 0 for week_start in week_starts}

    for created_at, row_coach_id in rows:
        if coach_id is not None and row_coach_id != coach_id:
            continue
        if not created_at:
            continue
        week_start = created_at.date() - timedelta(days=created_at.weekday())
        if week_start in counts:
            counts[week_start] += 1

    values = [counts[week_start] for week_start in week_starts]
    trend_max = max(values) if any(values) else 1
    step = 100 / max(len(values) - 1, 1)
    # SVG y=34 is chart floor and y=4 is chart ceiling, leaving a readable line at zero.
    points = " ".join(
        f"{index * step:.1f},{34 - (value / trend_max * 26):.1f}"
        for index, value in enumerate(values)
    )
    return {
        "labels": [week_start.strftime("%-d %b") for week_start in week_starts],
        "series": values,
        "max": trend_max,
        "points": points,
        "total": sum(values),
    }


def _connection_state(coaches, profiles_by_user_id):
    disconnected = []
    for coach in coaches:
        profile = profiles_by_user_id.get(coach.id)
        if not profile or not profile.google_credentials:
            disconnected.append(coach)
    return disconnected


def _coach_invite_form_token() -> str:
    """Return the per-session CSRF token for the sensitive invite action."""
    token = session.get("coach_invite_form_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["coach_invite_form_token"] = token
    return token


def _public_url(endpoint: str, **values) -> str:
    """Build a stable external URL, preferring a configured public base URL."""
    path = url_for(endpoint, **values)
    configured_base = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("APP_URL")
        or os.getenv("EXTERNAL_BASE_URL")
    )
    if configured_base:
        return configured_base.rstrip("/") + path
    scheme = "https" if os.getenv("FORCE_HTTPS_URLS", "0") == "1" else None
    if scheme:
        return url_for(endpoint, _external=True, _scheme=scheme, **values)
    return url_for(endpoint, _external=True, **values)


@dash_bp.route("/owner/invite-coach", methods=["POST"])
@login_required
@roles_required("owner")
def invite_coach():
    submitted_token = request.form.get("csrf_token", "")
    session_token = session.get("coach_invite_form_token", "")
    if not submitted_token or not secrets.compare_digest(submitted_token, session_token):
        flash("The invitation form expired. Please try again.", "error")
        return redirect(url_for("dashboard.owner"))

    name = (request.form.get("name") or "").strip()
    raw_email = (request.form.get("email") or "").strip()
    if not name or not raw_email:
        flash("Enter the coach's name and email address.", "error")
        return redirect(url_for("dashboard.owner"))

    try:
        email = validate_email(raw_email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        flash("Enter a valid coach email address.", "error")
        return redirect(url_for("dashboard.owner"))

    if User.query.filter_by(email=email).first():
        flash("That email already has an account. Manage it from People instead.", "error")
        return redirect(url_for("dashboard.owner"))

    now = datetime.utcnow()
    # Reissuing an invitation revokes an earlier unused link for the same email.
    CoachInvite.query.filter(
        CoachInvite.email == email,
        CoachInvite.accepted_at.is_(None),
        CoachInvite.expires_at > now,
    ).update({CoachInvite.expires_at: now}, synchronize_session=False)

    invite, raw_token = CoachInvite.issue(
        email=email,
        name=name,
        invited_by_user_id=current_user.id,
        expires_in_days=7,
    )
    db.session.add(invite)
    db.session.commit()

    invite_url = _public_url("auth.register", invite=raw_token)
    session["latest_coach_invite_url"] = invite_url
    session["coach_invite_form_token"] = secrets.token_urlsafe(32)

    try:
        from app.coach.public import send_email

        send_email(
            "You're invited to join TrueCosmic Calendar",
            "\n".join(
                [
                    f"Hi {name},",
                    "",
                    "You have been invited to join TrueCosmic Calendar as a coach.",
                    "Create your account using this one-time link:",
                    invite_url,
                    "",
                    "This link expires in 7 days and is tied to this email address.",
                    "After creating your account, sign in, connect your Google Calendar, and set your availability.",
                ]
            ),
            [email],
        )
    except Exception:
        # The owner can still copy the generated link if outbound email is unavailable.
        pass

    flash(f"Coach invitation created for {email}. An email delivery was attempted.", "success")
    return redirect(url_for("dashboard.owner"))


@dash_bp.route("/owner")
@login_required
@roles_required("owner", "admin")
def owner():
    now = _now()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)
    next_7 = now + timedelta(days=7)
    trend_since = datetime.combine(_weekly_windows(now)[0], datetime.min.time()).replace(tzinfo=timezone.utc)

    total_7 = Booking.query.filter(Booking.created_at >= last_7).count()
    total_30 = Booking.query.filter(Booking.created_at >= last_30).count()
    cancels_30 = Booking.query.filter(
        Booking.created_at >= last_30, Booking.status == "cancelled"
    ).count()

    coaches = User.query.filter(User.role == "host", User.is_active.is_(True)).order_by(User.name.asc()).all()
    profiles = CoachProfile.query.filter(CoachProfile.user_id.in_([coach.id for coach in coaches] or [-1])).all()
    profiles_by_user_id = {profile.user_id: profile for profile in profiles}
    disconnected_coaches = _connection_state(coaches, profiles_by_user_id)
    invite_now = datetime.utcnow()
    pending_invites = (
        CoachInvite.query.filter(
            CoachInvite.accepted_at.is_(None),
            CoachInvite.expires_at > invite_now,
        )
        .order_by(CoachInvite.created_at.desc())
        .limit(10)
        .all()
    )

    upcoming = (
        Booking.query.filter(
            Booking.status == "booked",
            Booking.start_utc >= now,
            Booking.start_utc <= next_7,
        )
        .order_by(Booking.start_utc.asc())
        .limit(25)
        .all()
    )

    # Build a staff-facing, week-at-a-glance agenda from the existing upcoming data.
    try:
        import pytz
        display_tz_name = current_user.timezone or "UTC"
        display_tz = pytz.timezone(display_tz_name)
    except Exception:
        display_tz_name = "UTC"
        display_tz = timezone.utc

    upcoming_by_day = []
    day_groups = {}
    for booking in upcoming:
        starts_at = booking.start_utc
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        local_start = starts_at.astimezone(display_tz)
        day_key = local_start.strftime("%Y-%m-%d")
        if day_key not in day_groups:
            day_groups[day_key] = {
                "label": local_start.strftime("%A, %-d %B"),
                "sessions": [],
            }
            upcoming_by_day.append(day_groups[day_key])
        day_groups[day_key]["sessions"].append({
            "time": local_start.strftime("%-I:%M %p"),
            "coach": booking.coach.name if booking.coach else "Unassigned coach",
            "visitor": booking.visitor_name,
        })

    trend_rows = db.session.query(Booking.created_at, Booking.coach_id).filter(Booking.created_at >= trend_since).all()
    organisation_trend = _make_weekly_trend(trend_rows, now)
    coach_insights = []
    for coach in coaches:
        coach_trend = _make_weekly_trend(trend_rows, now, coach_id=coach.id)
        bookings_30 = Booking.query.filter(Booking.coach_id == coach.id, Booking.created_at >= last_30).count()
        upcoming_7 = Booking.query.filter(
            Booking.coach_id == coach.id,
            Booking.status == "booked",
            Booking.start_utc >= now,
            Booking.start_utc <= next_7,
        ).count()
        coach_insights.append({
            "coach": coach,
            "profile": profiles_by_user_id.get(coach.id),
            "bookings_30": bookings_30,
            "upcoming_7": upcoming_7,
            "trend": coach_trend,
        })

    now_local_str = now.astimezone(display_tz).strftime("%-d %b %Y, %-I:%M %p")
    total_coaches = len(coaches)
    connected = total_coaches - len(disconnected_coaches)

    return render_template(
        "dashboard/owner.html",
        kpis={
            "bookings_7": total_7,
            "bookings_30": total_30,
            "cancellations_30": cancels_30,
            "coaches": total_coaches,
            "connected": connected,
            "connection_rate": round((connected / total_coaches * 100) if total_coaches else 0),
        },
        upcoming=upcoming,
        upcoming_by_day=upcoming_by_day,
        coach_insights=coach_insights,
        disconnected_coaches=disconnected_coaches,
        organisation_trend=organisation_trend,
        now=now,
        tz_name=display_tz_name,
        now_local_str=now_local_str,
        pending_invites=pending_invites,
        latest_invite_url=session.pop("latest_coach_invite_url", None),
        coach_invite_form_token=_coach_invite_form_token(),
    )


@dash_bp.route("/host")
@login_required
@roles_required("host", "admin", "owner")
def host():
    now = _now()
    last_30 = now - timedelta(days=30)
    next_7 = now + timedelta(days=7)
    trend_since = datetime.combine(_weekly_windows(now)[0], datetime.min.time()).replace(tzinfo=timezone.utc)

    me_id = current_user.id
    profile = CoachProfile.query.filter_by(user_id=me_id).first()
    total_30 = Booking.query.filter(Booking.coach_id == me_id, Booking.created_at >= last_30).count()
    cancels_30 = Booking.query.filter(
        Booking.coach_id == me_id, Booking.created_at >= last_30, Booking.status == "cancelled"
    ).count()
    upcoming_count = Booking.query.filter(
        Booking.coach_id == me_id,
        Booking.status == "booked",
        Booking.start_utc >= now,
        Booking.start_utc <= next_7,
    ).count()

    upcoming = (
        Booking.query.filter(
            Booking.coach_id == me_id,
            Booking.status == "booked",
            Booking.start_utc >= now,
        )
        .order_by(Booking.start_utc.asc())
        .limit(25)
        .all()
    )

    try:
        import pytz
        tz_name = profile.timezone if profile and profile.timezone else "UTC"
        display_tz = pytz.timezone(tz_name)
    except Exception:
        tz_name = "UTC"
        display_tz = timezone.utc

    upcoming_by_day = []
    day_groups = {}
    for booking in upcoming:
        starts_at = booking.start_utc
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        local_start = starts_at.astimezone(display_tz)
        day_key = local_start.strftime("%Y-%m-%d")
        if day_key not in day_groups:
            day_groups[day_key] = {
                "label": local_start.strftime("%A, %-d %B"),
                "sessions": [],
            }
            upcoming_by_day.append(day_groups[day_key])
        day_groups[day_key]["sessions"].append({
            "time": local_start.strftime("%-I:%M %p"),
            "visitor_name": booking.visitor_name,
            "visitor_email": booking.visitor_email,
            "meet_link": booking.meet_link,
            "manage_url": url_for("public.manage_booking", booking_id=booking.id, token=booking.token),
        })

    trend_rows = db.session.query(Booking.created_at, Booking.coach_id).filter(
        Booking.coach_id == me_id,
        Booking.created_at >= trend_since,
    ).all()
    booking_trend = _make_weekly_trend(trend_rows, now, coach_id=me_id)
    cancellation_rate = round((cancels_30 / total_30 * 100) if total_30 else 0)
    now_local_str = now.astimezone(display_tz).strftime("%-d %b %Y, %-I:%M %p")

    return render_template(
        "dashboard/host.html",
        kpis={
            "bookings_30": total_30,
            "cancellations_30": cancels_30,
            "cancellation_rate": cancellation_rate,
            "upcoming_7": upcoming_count,
        },
        profile=profile,
        upcoming_by_day=upcoming_by_day,
        booking_trend=booking_trend,
        tz_name=tz_name,
        now_local_str=now_local_str,
        now=now,
    )
