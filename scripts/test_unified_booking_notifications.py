"""Regression tests for calendar-owned unified booking notifications.

Run with: .venv/bin/python scripts/test_unified_booking_notifications.py
The script uses a temporary SQLite database and mocks all outbound HTTP/email.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

fd, database_path = tempfile.mkstemp(prefix="truecosmic-unified-notification-", suffix=".db")
os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
os.environ["SECRET_KEY"] = "unified-notification-regression-secret"

from app import create_app  # noqa: E402
from app.coach import public  # noqa: E402

app = create_app()
app.config.update(TESTING=True)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_booking_context_lookup_contract():
    previous_url = os.environ.get("BOOKING_CONTEXT_PROXY_URL")
    previous_secret = os.environ.get("BOOKING_CONTEXT_PROXY_SECRET")
    os.environ["BOOKING_CONTEXT_PROXY_URL"] = "https://crm.example.test/functions/v1/claudde-bot-proxy"
    os.environ["BOOKING_CONTEXT_PROXY_SECRET"] = "calendar-only-secret"

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(payload={"found": True, "summary": "Visitor is seeking focused coaching."})

    try:
        with patch.object(public.requests, "post", side_effect=fake_post):
            result = public.lookup_booking_context("Visitor@Example.test", "+447700900123")
        assert result == {"found": True, "summary": "Visitor is seeking focused coaching."}
        assert captured["url"] == os.environ["BOOKING_CONTEXT_PROXY_URL"]
        assert captured["json"] == {"op": "get_summary_by_contact", "params": {"email": "visitor@example.test"}}
        assert captured["headers"] == {
            "x-booking-context-secret": "calendar-only-secret",
            "Content-Type": "application/json",
        }

        with patch.object(public.requests, "post", return_value=FakeResponse(status_code=503)):
            assert public.lookup_booking_context("visitor@example.test", None) is None
        with patch.object(public.requests, "post", return_value=FakeResponse(payload=[])):
            assert public.lookup_booking_context("visitor@example.test", None) is None
    finally:
        if previous_url is None:
            os.environ.pop("BOOKING_CONTEXT_PROXY_URL", None)
        else:
            os.environ["BOOKING_CONTEXT_PROXY_URL"] = previous_url
        if previous_secret is None:
            os.environ.pop("BOOKING_CONTEXT_PROXY_SECRET", None)
        else:
            os.environ["BOOKING_CONTEXT_PROXY_SECRET"] = previous_secret


def test_individual_recipients_and_context_boundary():
    sent = []

    def capture_email(subject, body, recipients):
        sent.append((subject, body, tuple(recipients)))

    with app.test_request_context("/"):
        with patch.object(public, "send_email", side_effect=capture_email), patch.object(
            public, "_tz_for_user_email", return_value="Europe/London"
        ):
            public.send_booking_email(
                coach_email="coach@example.test",
                owner_email="admin@truecosmic.com",
                visitor_email="visitor@example.test",
                coach_name="Cheryl",
                visitor_name="Visitor Name",
                start=datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc),
                meet_link="https://meet.example.test/abc",
                booking_id=42,
                booking_token="token",
                visitor_timezone="Europe/London",
                visitor_phone="+447700900123",
                base_url="https://calendar.example.test",
                conversation_summary="Visitor is seeking focused coaching around a specific goal.",
            )

    recipients = [recipient for _, _, (recipient,) in sent]
    assert recipients == [
        "coach@example.test",
        "visitor@example.test",
        "admin@truecosmic.com",
        "info@truecosmic.com",
    ]
    assert len(recipients) == len(set(recipient.lower() for recipient in recipients))
    assert "Claudde conversation summary" in sent[0][1]
    assert "Visitor is seeking focused coaching" in sent[0][1]
    assert "Visitor email: visitor@example.test" in sent[0][1]
    assert "Visitor phone: +447700900123" in sent[0][1]
    assert "Claudde conversation summary" not in sent[1][1]
    assert "Visitor phone: +447700900123" not in sent[1][1]
    assert "Claudde conversation summary" in sent[2][1]
    assert "Claudde conversation summary" in sent[3][1]


def test_no_context_keeps_clean_notification():
    sent = []

    def capture_email(subject, body, recipients):
        sent.append((subject, body, tuple(recipients)))

    with app.test_request_context("/"):
        with patch.object(public, "send_email", side_effect=capture_email), patch.object(
            public, "_tz_for_user_email", return_value="UTC"
        ):
            public.send_booking_email(
                coach_email="coach@example.test",
                owner_email=None,
                visitor_email="visitor@example.test",
                coach_name="Cheryl",
                visitor_name="Visitor Name",
                start=datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc),
                meet_link="https://meet.example.test/abc",
                booking_id=42,
                booking_token="token",
                visitor_timezone="UTC",
                visitor_phone=None,
                base_url="https://calendar.example.test",
                conversation_summary=None,
            )

    assert [recipient for _, _, (recipient,) in sent] == [
        "coach@example.test",
        "visitor@example.test",
        "admin@truecosmic.com",
        "info@truecosmic.com",
    ]
    assert all("Claudde conversation summary" not in body for _, body, _ in sent)


def run():
    test_booking_context_lookup_contract()
    test_individual_recipients_and_context_boundary()
    test_no_context_keeps_clean_notification()
    print("Unified booking notification regression coverage passed.")


if __name__ == "__main__":
    try:
        run()
    finally:
        Path(database_path).unlink(missing_ok=True)
