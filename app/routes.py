from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # If user is already authenticated, send them to their dashboard
    if current_user.is_authenticated:
        role = getattr(current_user, "role", None)
        if role in ("owner", "admin"):
            return redirect(url_for("dashboard.owner"))
        if role == "host":
            return redirect(url_for("dashboard.host"))
        # Fallback for other roles
        return redirect(url_for("public.coaches_list"))
    return render_template("index.html")

