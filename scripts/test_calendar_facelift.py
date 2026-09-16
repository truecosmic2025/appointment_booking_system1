"""Focused regression coverage for the TrueCosmic Calendar facelift.

Run with: .venv-linux/bin/python scripts/test_calendar_facelift.py
This script uses an isolated temporary SQLite database and never connects to Railway.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

fd, database_path = tempfile.mkstemp(prefix="truecosmic-facelift-", suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
os.environ["SECRET_KEY"] = "facelift-regression-secret"

from app import create_app, db  # noqa: E402
from app.models import Booking, CoachProfile, User  # noqa: E402

app = create_app()
app.config.update(TESTING=True)


def login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def make_user(email, name, role="host"):
    user = User(email=email, name=name, role=role, timezone="Europe/London")
    user.set_password("not-used-in-test")
    db.session.add(user)
    db.session.flush()
    return user


def run():
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.drop_all()
        db.create_all()

        owner = make_user("owner@example.test", "Team Owner", "owner")
        connected = make_user("connected@example.test", "Connected Coach")
        unconnected = make_user("unconnected@example.test", "Unconnected Coach")
        connected_profile = CoachProfile(
            user_id=connected.id,
            slug="connected-coach",
            timezone="Europe/London",
            google_credentials='{"token":"existing-access-token","refresh_token":"existing-refresh-token"}',
        )
        unconnected_profile = CoachProfile(
            user_id=unconnected.id,
            slug="unconnected-coach",
            timezone="Europe/London",
        )
        db.session.add_all([connected_profile, unconnected_profile])

        for week_offset in range(8):
            created = (now - timedelta(days=(week_offset * 7) + 2)).replace(tzinfo=None)
            booked = Booking(
                coach_id=connected.id,
                visitor_name=f"Connected Visitor {week_offset}",
                visitor_email=f"connected-{week_offset}@example.test",
                start_utc=(now - timedelta(days=week_offset + 1)).replace(tzinfo=None),
                end_utc=(now - timedelta(days=week_offset + 1, minutes=-30)).replace(tzinfo=None),
                timezone="Europe/London",
                status="cancelled" if week_offset == 1 else "booked",
                token=f"connected-token-{week_offset}",
                created_at=created,
            )
            other = Booking(
                coach_id=unconnected.id,
                visitor_name=f"Other Visitor {week_offset}",
                visitor_email=f"other-{week_offset}@example.test",
                start_utc=(now - timedelta(days=week_offset + 1)).replace(tzinfo=None),
                end_utc=(now - timedelta(days=week_offset + 1, minutes=-30)).replace(tzinfo=None),
                timezone="Europe/London",
                status="booked",
                token=f"unconnected-token-{week_offset}",
                created_at=created,
            )
            db.session.add_all([booked, other])

        db.session.add(Booking(
            coach_id=connected.id,
            visitor_name="Upcoming Visitor",
            visitor_email="upcoming@example.test",
            start_utc=(now + timedelta(days=1)).replace(tzinfo=None),
            end_utc=(now + timedelta(days=1, minutes=30)).replace(tzinfo=None),
            timezone="Europe/London",
            status="booked",
            token="upcoming-token",
            created_at=now.replace(tzinfo=None),
        ))
        db.session.commit()

        owner_id = owner.id
        connected_id = connected.id
        credential_before = db.session.get(CoachProfile, connected_profile.id).google_credentials
        profile_id = connected_profile.id

    # Each request receives its own app/request context, as in production.
    coach_client = app.test_client()
    login(coach_client, connected_id)
    response = coach_client.get("/dashboard/host")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Your coaching rhythm" in page
    assert "Booking requests over 8 weeks" in page
    assert "Cancellation rate" in page
    assert "Upcoming Visitor" in page

    owner_client = app.test_client()
    login(owner_client, owner_id)
    response = owner_client.get("/dashboard/owner")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "The coaching pulse" in page
    assert "Google Calendar gaps" in page
    assert "Unconnected Coach" in page
    assert "Coach momentum" in page
    assert "Upcoming Visitor" in page

    response = owner_client.get(
        f"/admin/reports/meetings?period=30&status=past&coach_id={connected_id}"
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Connected Visitor 0" in page
    assert "Other Visitor 0" not in page
    assert f'value="{connected_id}" selected' in page

    response = app.test_client().get("/c/connected-coach")
    assert response.status_code == 200
    assert "Find your moment" in response.get_data(as_text=True)

    with app.app_context():
        # Dashboard and public-page rendering must never mutate the stored OAuth JSON.
        assert db.session.get(CoachProfile, profile_id).google_credentials == credential_before

    css = Path(app.root_path, "static", "css", "tailwind.css").read_text(encoding="utf-8")
    assert ".tc-card" in css
    assert ".tc-btn-primary" in css
    print("Facelift regression coverage passed.")


if __name__ == "__main__":
    try:
        run()
    finally:
        Path(database_path).unlink(missing_ok=True)
