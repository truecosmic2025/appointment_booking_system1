"""Seed an isolated local preview database for manual UI review only.

Run with: DATABASE_URL=sqlite:////tmp/truecosmic-preview.db .venv-linux/bin/python scripts/seed_preview.py
Preview login credentials: owner@example.test / preview-password
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app, db  # noqa: E402
from app.models import Booking, CoachProfile, User  # noqa: E402

app = create_app()


def user(email, name, role):
    record = User(email=email, name=name, role=role, timezone="Europe/London")
    record.set_password("preview-password")
    db.session.add(record)
    db.session.flush()
    return record


with app.app_context():
    db.drop_all()
    db.create_all()
    owner = user("owner@example.test", "Michael Founder", "owner")
    coach = user("coach@example.test", "Ava Morgan", "host")
    unconnected = user("unconnected@example.test", "Jon Rivers", "host")
    db.session.add_all([
        CoachProfile(user_id=coach.id, slug="ava-morgan", timezone="Europe/London", google_credentials='{"token":"preview-token","refresh_token":"preview-refresh"}'),
        CoachProfile(user_id=unconnected.id, slug="jon-rivers", timezone="Europe/London"),
    ])
    now = datetime.utcnow()
    for index in range(8):
        created = now - timedelta(days=index * 7 + 2)
        db.session.add(Booking(
            coach_id=coach.id,
            visitor_name=f"Client {index + 1}",
            visitor_email=f"client{index + 1}@example.test",
            start_utc=now + timedelta(days=index % 5 + 1, hours=index),
            end_utc=now + timedelta(days=index % 5 + 1, hours=index, minutes=30),
            timezone="Europe/London",
            status="cancelled" if index == 3 else "booked",
            token=f"preview-token-{index}",
            created_at=created,
        ))
    db.session.commit()
    print("Preview database seeded.")
