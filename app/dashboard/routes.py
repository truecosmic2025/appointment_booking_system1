from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app import db
from app.models import User, Booking, CoachProfile
from app.auth.routes import roles_required


dash_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


@dash_bp.route("/owner")
@login_required
@roles_required("owner", "admin")
def owner():
    now = _now()
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)
    next_7 = now + timedelta(days=7)

    total_7 = Booking.query.filter(Booking.created_at >= last_7).count()
    total_30 = Booking.query.filter(Booking.created_at >= last_30).count()
    cancels_30 = (
        Booking.query.filter(Booking.created_at >= last_30, Booking.status == "cancelled").count()
    )

    coaches_q = User.query.filter(User.role.in_(["host", "owner", "admin"]))
    total_coaches = coaches_q.count()
    connected = (
        CoachProfile.query.filter(CoachProfile.google_credentials.isnot(None)).count()
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

    # Per‑coach quick stats
    coach_rows = (
        db.session.query(User, CoachProfile)
        .outerjoin(CoachProfile, CoachProfile.user_id == User.id)
        .filter(User.role.in_(["host", "owner", "admin"]))
        .order_by(User.name.asc())
        .all()
    )

    # Get current user's timezone for display
    try:
        import pytz
        tz_name = current_user.timezone if hasattr(current_user, 'timezone') and current_user.timezone else 'UTC'
        tz = pytz.timezone(tz_name)
        now_local_str = now.astimezone(tz).strftime('%Y-%m-%d %H:%M')
    except Exception:
        tz_name = 'UTC'
        now_local_str = now.strftime('%Y-%m-%d %H:%M')

    return render_template(
        "dashboard/owner.html",
        kpis={
            "bookings_7": total_7,
            "bookings_30": total_30,
            "cancellations_30": cancels_30,
            "coaches": total_coaches,
            "connected": connected,
        },
        upcoming=upcoming,
        coach_rows=coach_rows,
        now=now,
        now_local_str=now_local_str,
    )


@dash_bp.route("/host")
@login_required
@roles_required("host", "admin", "owner")
def host():
    now = _now()
    last_30 = now - timedelta(days=30)
    next_7 = now + timedelta(days=7)

    me_id = current_user.id
    prof = CoachProfile.query.filter_by(user_id=me_id).first()

    total_30 = Booking.query.filter(Booking.coach_id == me_id, Booking.created_at >= last_30).count()
    cancels_30 = Booking.query.filter(
        Booking.coach_id == me_id, Booking.created_at >= last_30, Booking.status == "cancelled"
    ).count()
    upcoming_cnt = Booking.query.filter(
        Booking.coach_id == me_id, Booking.status == "booked", Booking.start_utc >= now, Booking.start_utc <= next_7
    ).count()

    upcoming = (
        Booking.query.filter(
            Booking.coach_id == me_id, Booking.status == "booked", Booking.start_utc >= now
        )
        .order_by(Booking.start_utc.asc())
        .limit(25)
        .all()
    )
    # Build localized view of upcoming sessions in host's timezone
    try:
        import pytz
        tz_name = (prof.timezone if prof and prof.timezone else 'UTC')
        tz = pytz.timezone(tz_name)
    except Exception:
        tz_name = 'UTC'
        tz = None

    # Current time formatted in host timezone
    try:
        now_local_str = now.astimezone(tz).strftime('%Y-%m-%d %H:%M') if tz else now.strftime('%Y-%m-%d %H:%M')
    except Exception:
        now_local_str = now.strftime('%Y-%m-%d %H:%M')

    upcoming_local = []
    for b in upcoming:
        try:
            start_local_str = b.start_utc.astimezone(tz).strftime('%Y-%m-%d %H:%M') if tz else b.start_utc.strftime('%Y-%m-%d %H:%M')
        except Exception:
            start_local_str = b.start_utc.strftime('%Y-%m-%d %H:%M')
        upcoming_local.append({
            'start_local_str': start_local_str,
            'visitor_name': b.visitor_name,
            'visitor_email': b.visitor_email,
            'status': b.status,
            'meet_link': getattr(b, 'meet_link', None),
        })

    return render_template(
        "dashboard/host.html",
        kpis={
            "bookings_30": total_30,
            "cancellations_30": cancels_30,
            "upcoming_7": upcoming_cnt,
        },
        profile=prof,
        upcoming=upcoming,
        upcoming_local=upcoming_local,
        tz_name=tz_name,
        now_local_str=now_local_str,
        now=now,
    )

