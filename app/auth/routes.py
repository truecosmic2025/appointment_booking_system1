from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from functools import wraps
from urllib.parse import urlparse


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.url))
            if current_user.role not in roles:
                flash("You do not have access to that page.", "error")
                return redirect(url_for("main.index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password", "error")
        else:
            login_user(user, remember=True)
            next_page = request.args.get("next")
            if not next_page or urlparse(next_page).netloc != "":
                next_page = url_for("main.index")
            return redirect(next_page)

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not name or not email or not password:
            flash("Please fill in all fields", "error")
        elif password != password2:
            flash("Passwords do not match", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email is already registered", "error")
        else:
            user = User(name=name, email=email, role="invitee")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. You can now sign in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))


# Example protected pages for roles
@auth_bp.route("/admin")
@roles_required("admin")
def admin_only():
    return render_template("auth/role_gate.html", title="Admin", role="admin")


@auth_bp.route("/host")
@roles_required("host", "admin")
def host_only():
    return render_template("auth/role_gate.html", title="Host", role="host")


@auth_bp.route("/me")
@login_required
def me():
    return render_template("auth/me.html")
