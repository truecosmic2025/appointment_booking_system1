"""Regression coverage for the public booking phone requirement."""

import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["SYNC_POST_BOOKING"] = "0"

from app import create_app, db
from app.models.booking import Booking
from app.models.coach_profile import CoachProfile
from app.models.user import User


class RequiredBookingPhoneTests(unittest.TestCase):
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

        coach = User(
            email="coach@example.test",
            name="Test Coach",
            role="host",
            timezone="UTC",
        )
        coach.set_password("test-password")
        db.session.add(coach)
        db.session.commit()
        db.session.add(CoachProfile(user_id=coach.id, slug="test-coach", timezone="UTC"))
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    @staticmethod
    def booking_payload(phone):
        return {
            "name": "Visitor Example",
            "email": "visitor@example.test",
            "phone": phone,
            "start": "2027-01-10T12:00:00+00:00",
            "timezone": "UTC",
        }

    def test_direct_and_bot_handoff_pages_show_a_visible_required_phone_field(self):
        for path in ("/c/test-coach", "/c/test-coach?name=Visitor%20Example"):
            response = self.client.get(path)
            page = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertRegex(
                page,
                r'<input type="tel" name="phone"[^>]*required>',
            )
            self.assertNotIn('type="hidden" name="phone"', page)

    def test_empty_phone_is_rejected_even_when_a_stale_session_value_exists(self):
        with self.client.session_transaction() as session:
            session["booking_phone"] = "+447734322560"

        with patch("app.coach.public.create_event_with_meet") as create_event:
            response = self.client.post(
                "/api/book/test-coach",
                json=self.booking_payload("   "),
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Phone number is required to book a session."},
        )
        create_event.assert_not_called()
        self.assertEqual(Booking.query.count(), 0)

    def test_non_phone_value_is_rejected_before_calendar_event_creation(self):
        with patch("app.coach.public.create_event_with_meet") as create_event:
            response = self.client.post(
                "/api/book/test-coach",
                json=self.booking_payload("not-a-phone-number"),
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Enter a valid phone number to book a session."},
        )
        create_event.assert_not_called()
        self.assertEqual(Booking.query.count(), 0)

    def test_valid_phone_is_normalized_and_saved_on_a_new_booking(self):
        with patch(
            "app.coach.public.create_event_with_meet",
            return_value=("test-event-id", "https://meet.example.test/test"),
        ), patch("app.coach.public.threading.Thread") as background_thread:
            response = self.client.post(
                "/api/book/test-coach",
                json=self.booking_payload("+44 7734 322560"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        booking = Booking.query.one()
        self.assertEqual(booking.visitor_phone, "+447734322560")
        background_thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
