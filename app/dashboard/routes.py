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

    return render_template(
        "dashboard/host.html",
        kpis={
            "bookings_30": total_30,
            "cancellations_30": cancels_30,
            "upcoming_7": upcoming_cnt,
        },
        profile=prof,
        upcoming=upcoming,
        now=now,
    )

