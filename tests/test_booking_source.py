"""Booking source tracking: ?src=&ref= on the booking link is stored on the booking."""

import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["SYNC_POST_BOOKING"] = "0"

from app import create_app, db
from app.booking_source import clean_ref, clean_source, source_label
from app.models.booking import Booking
from app.models.coach_profile import CoachProfile
from app.models.user import User


class CleanSourceTests(unittest.TestCase):
    def test_clean_source(self):
        self.assertEqual(clean_source("whatsapp-done-deal-starter-kit"), "whatsapp-done-deal-starter-kit")
        self.assertEqual(clean_source("  Web Chat  "), "web-chat")
        self.assertEqual(clean_source("<script>alert(1)</script>"), "script-alert-1-script")
        self.assertIsNone(clean_source(""))
        self.assertIsNone(clean_source("!!!"))
        self.assertIsNone(clean_source(None))
        self.assertEqual(len(clean_source("a" * 200)), 64)

    def test_clean_ref(self):
        self.assertEqual(clean_ref("3f2c8912-c518-4956-a955-1ce606d98239"), "3f2c8912-c518-4956-a955-1ce606d98239")
        self.assertEqual(clean_ref("abc<>\"' 123"), "abc123")
        self.assertIsNone(clean_ref(""))
        self.assertEqual(len(clean_ref("b" * 300)), 128)

    def test_labels(self):
        self.assertEqual(source_label(None), "Direct (no source)")
        self.assertEqual(source_label("whatsapp-done-deal-starter-kit"), "WhatsApp ad: Done Deal")
        self.assertEqual(source_label("some-new-route"), "Some new route")


class BookingSourceFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        coach = User(email="coach@example.test", name="Test Coach", role="host", timezone="UTC")
        coach.set_password("test-password")
        db.session.add(coach)
        db.session.commit()
        db.session.add(CoachProfile(user_id=coach.id, slug="test-coach", timezone="UTC"))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def _book(self, extra):
        payload = {
            "name": "Visitor Example",
            "email": "visitor@example.test",
            "phone": "+44 7734 322560",
            "start": "2027-01-10T12:00:00+00:00",
            "timezone": "UTC",
            **extra,
        }
        with patch("app.coach.public.create_event_with_meet", return_value=("evt", "https://meet.example.test/x")) as ev, \
                patch("app.coach.public.threading.Thread"):
            response = self.client.post("/api/book/test-coach", json=payload)
        return response, ev

    def test_page_embeds_cleaned_source_for_the_booking_request(self):
        page = self.client.get("/c/test-coach?src=whatsapp-done-deal-starter-kit&ref=conv-123").get_data(as_text=True)
        self.assertIn('"whatsapp-done-deal-starter-kit"', page)
        self.assertIn('"conv-123"', page)
        hostile = self.client.get('/c/test-coach?src=%3C%2Fscript%3E&ref=%22%3E%3Cx').get_data(as_text=True)
        self.assertNotIn("</script>\"", hostile)
        self.assertNotIn('"><x', hostile)

    def test_page_without_source_still_works(self):
        response = self.client.get("/c/test-coach")
        self.assertEqual(response.status_code, 200)
        self.assertIn("source: \"\" || null", response.get_data(as_text=True))

    def test_source_is_saved_on_the_booking_and_in_the_calendar_event(self):
        response, ev = self._book({"source": "whatsapp-done-deal-starter-kit", "source_ref": "conv-123"})
        self.assertEqual(response.status_code, 200)
        booking = Booking.query.one()
        self.assertEqual(booking.source, "whatsapp-done-deal-starter-kit")
        self.assertEqual(booking.source_ref, "conv-123")
        self.assertIn("Source: WhatsApp ad: Done Deal", ev.call_args.kwargs["description"])

    def test_booking_without_source_is_stored_as_direct(self):
        response, _ = self._book({})
        self.assertEqual(response.status_code, 200)
        booking = Booking.query.one()
        self.assertIsNone(booking.source)
        self.assertIsNone(booking.source_ref)

    def test_owner_dashboard_shows_bookings_by_source(self):
        self._book({"source": "whatsapp-done-deal-starter-kit", "source_ref": "conv-1"})
        self._book({})
        owner = User(email="owner@example.test", name="Owner", role="owner", timezone="UTC")
        owner.set_password("owner-test-password")
        db.session.add(owner)
        db.session.commit()
        login = self.client.post("/auth/login", data={"email": "owner@example.test", "password": "owner-test-password"})
        self.assertEqual(login.status_code, 302)
        page = self.client.get("/dashboard/owner")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Where bookings come from", html)
        self.assertIn("WhatsApp ad: Done Deal", html)
        self.assertIn("Direct (no source)", html)


if __name__ == "__main__":
    unittest.main()
