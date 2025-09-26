import json
import os
from flask import Blueprint, redirect, request, session, url_for, flash
from flask_login import login_required, current_user
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from app import db
from app.models.coach_profile import CoachProfile


google_bp = Blueprint("google", __name__, url_prefix="/google")


def _ensure_profile():
    profile = CoachProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        slug_base = CoachProfile.generate_slug(current_user.name)
        # Ensure uniqueness
        slug = slug_base
        i = 1
        while CoachProfile.query.filter_by(slug=slug).first() is not None:
            i += 1
            slug = f"{slug_base}-{i}"
        profile = CoachProfile(user_id=current_user.id, slug=slug)
        db.session.add(profile)
        db.session.commit()
    return profile


@google_bp.route("/connect")
@login_required
def connect():
    if current_user.role not in ("host", "owner", "admin"):
        flash("Only coaches can connect Google Calendar.", "error")
        return redirect(url_for("main.index"))

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        flash("Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for("auth.me"))

    # Build an external redirect URI; force https in production if requested
    scheme = "https" if os.getenv("FORCE_HTTPS_URLS", "0") == "1" else None
    redirect_uri = url_for("google.callback", _external=True, _scheme=scheme) if scheme else url_for("google.callback", _external=True)
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=redirect_uri,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    session["google_oauth_state"] = state
    return redirect(auth_url)


@google_bp.route("/callback")
@login_required
def callback():
    state = session.get("google_oauth_state")
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = url_for("google.callback", _external=True)
    if not state or not client_id or not client_secret:
        flash("Invalid OAuth state.", "error")
        return redirect(url_for("auth.me"))

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        state=state,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    profile = _ensure_profile()
    profile.google_credentials = json.dumps(data)
    db.session.commit()
    flash("Google Calendar connected.", "success")
    return redirect(url_for("auth.me"))


@google_bp.route("/disconnect", methods=["POST"])
@login_required
def disconnect():
    if current_user.role not in ("host", "owner", "admin"):
        flash("Only coaches can manage Google Calendar.", "error")
        return redirect(url_for("auth.me"))

    profile = CoachProfile.query.filter_by(user_id=current_user.id).first()
    if not profile or not profile.google_credentials:
        flash("Google Calendar is not connected.", "error")
        return redirect(url_for("auth.me"))

    # Attempt token revocation (best-effort)
    try:
        import json, requests
        data = json.loads(profile.google_credentials)
        token = data.get("token") or data.get("access_token") or data.get("refresh_token")
        if token:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
    except Exception:
        pass

    profile.google_credentials = None
    db.session.commit()
    flash("Google Calendar disconnected.", "success")
    return redirect(url_for("auth.me"))
