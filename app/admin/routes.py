from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.models.user import User
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

