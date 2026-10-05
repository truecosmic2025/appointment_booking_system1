from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_, select, and_, desc
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta

from app import db
from app.models.user import User
from app.models.booking import Booking
from app.auth.routes import roles_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def require_login():
    pass


@admin_bp.route("/users")
@roles_required("admin", "owner")
def users_index():
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(User.email.ilike(like), User.name.ilike(like)))
    users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, q=q)


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required("admin", "owner")
def users_set_role(user_id: int):
    role = request.form.get("role", "").strip()
    target = db.session.get(User, user_id)
    if not target:
        return abort(404)

    # Only owners can assign/remove owner role
    if role == "owner" and current_user.role != "owner":
        flash("Only the owner can grant owner role.", "error")
        return redirect(url_for("admin.users_index"))

    # Prevent demoting the last owner
    if target.role == "owner" and role != "owner":
        owners = User.query.filter_by(role="owner").count()
        if owners <= 1:
            flash("You cannot demote the last owner.", "error")
            return redirect(url_for("admin.users_index"))

    if role not in {"owner", "admin", "host", "invitee"}:
        flash("Invalid role.", "error")
        return redirect(url_for("admin.users_index"))

    target.role = role
    db.session.commit()
    flash(f"Updated role for {target.email} to {role}.", "success")
    return redirect(url_for("admin.users_index"))


@admin_bp.route("/users/<int:user_id>/active", methods=["POST"])
@roles_required("owner")
def users_set_active(user_id: int):
    target = db.session.get(User, user_id)
    if not target:
        return abort(404)

    # Only hosts can be deactivated via this control
    if target.role != "host":
        flash("Only host accounts can be activated/deactivated here.", "error")
        return redirect(url_for("admin.users_index"))

    desired = request.form.get("active", "").strip()
    if desired not in {"0", "1"}:
        flash("Invalid active value.", "error")
        return redirect(url_for("admin.users_index"))

    target.is_active = True if desired == "1" else False
    db.session.commit()
    state = "activated" if target.is_active else "deactivated"
    flash(f"{target.email} has been {state}.", "success")
    return redirect(url_for("admin.users_index"))


@admin_bp.route("/reports/meetings")
@roles_required("admin", "owner")
def meetings_report():
    period_raw = request.args.get("period", "30").strip()
    try:
        period = int(period_raw)
    except ValueError:
        period = 30
    if period not in (30, 60, 90):
        period = 30

    status = (request.args.get("status", "past") or "").strip().lower()
    if status not in ("past", "cancelled"):
        status = "past"

    selected_coach_id = request.args.get("coach_id", type=int)
    coach_choices = User.query.filter(User.role == "host").order_by(User.name.asc()).all()
    allowed_coach_ids = {coach.id for coach in coach_choices}
    if selected_coach_id not in allowed_coach_ids:
        selected_coach_id = None

    page = request.args.get("page", 1, type=int)
    per_page = 20

    now = datetime.utcnow()
    since = now - timedelta(days=period)

    conditions = [Booking.start_utc >= since, Booking.start_utc <= now]
    if status == "past":
        conditions.append(Booking.status == "booked")
    else:
        conditions.append(Booking.status == "cancelled")
    if selected_coach_id:
        conditions.append(Booking.coach_id == selected_coach_id)

    stmt = (
        select(Booking)
        .options(joinedload(Booking.coach))
        .where(and_(*conditions))
        .order_by(desc(Booking.start_utc))
    )

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    return render_template(
        "admin/meetings_report.html",
        pagination=pagination,
        period=period,
        status=status,
        coach_choices=coach_choices,
        selected_coach_id=selected_coach_id,
        now=now,
    )


@admin_bp.route("/fix-hadassah-slug", methods=["POST"])
@login_required
def fix_hadassah_slug():
    """TEMPORARY: Fix hadassah-headley slug mismatch. REMOVE AFTER USE."""
    from app.models.coach_profile import CoachProfile
    from flask import jsonify

    if not current_user.is_authenticated or current_user.role != "owner":
        return jsonify({"error": "admin only"}), 403

    old_slug = "hadasssah-headley"
    new_slug = "hadassah-headley"

    # Check for conflicts
    existing = CoachProfile.query.filter_by(slug=new_slug).first()
    if existing:
        return jsonify({"error": f"slug '{new_slug}' already exists"}), 409

    # Find misspelled row
    prof = CoachProfile.query.filter_by(slug=old_slug).first()
    if not prof:
        return jsonify({"error": f"no profile with slug '{old_slug}'"}), 404

    # Update
    try:
        prof.slug = new_slug
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    # Verify
    verified = CoachProfile.query.filter_by(slug=new_slug).first()
    if not verified:
        return jsonify({"error": "verification failed"}), 500

    return jsonify({
        "success": True,
        "coach_name": verified.user.name,
        "coach_email": verified.user.email,
        "slug": verified.slug,
        "message": "Slug updated. DELETE THIS ENDPOINT NEXT."
    }), 200
