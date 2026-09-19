"""Regression coverage for retiring the public /coaches directory page.

The /coaches page used to render every coach's real name, personal email
address, and a direct /c/<slug> booking link with no gate at all -- letting
anyone book a session with any coach without ever going through Claudde
Bot's qualifying questions, which the bot-driven flow strictly requires.
It must now redirect out to the gated, bot-fronted coach site instead of
rendering coach details.
"""

import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["SYNC_POST_BOOKING"] = "0"

from app import create_app, db
from app.coach.public import PUBLIC_COACH_DIRECTORY_URL
from app.models.coach_profile import CoachProfile
from app.models.user import User


class PublicCoachesDirectoryRedirectTests(unittest.TestCase):
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

    def test_public_coaches_directory_redirects_out_instead_of_listing_coaches(self):
        response = self.client.get("/coaches")

        self.assertIn(response.status_code, (301, 302, 303, 307, 308))
        self.assertEqual(response.headers["Location"], PUBLIC_COACH_DIRECTORY_URL)

        page = response.get_data(as_text=True)
        self.assertNotIn("coach@example.test", page)
        self.assertNotIn("/c/test-coach", page)

    def test_individual_coach_booking_page_is_unaffected(self):
        response = self.client.get("/c/test-coach")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
