"""Security and workflow coverage for owner-created coach invitations."""

import os
import re
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_ENABLED"] = "false"

from app import create_app, db
from app.models.coach_invite import CoachInvite
from app.models.user import User


class CoachInvitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, SECRET_KEY="test-invite-secret")

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.owner = self.make_user("Owner", "owner@example.test", "owner")
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    @staticmethod
    def password():
        return "secure-test-password"

    def make_user(self, name, email, role):
        user = User(name=name, email=email, role=role, timezone="UTC")
        user.set_password(self.password())
        db.session.add(user)
        db.session.commit()
        return user

    def login_as_owner(self):
        response = self.client.post(
            "/auth/login",
            data={"email": self.owner.email, "password": self.password()},
        )
        self.assertEqual(response.status_code, 302)

    def invite_form_token(self):
        dashboard = self.client.get("/dashboard/owner")
        self.assertEqual(dashboard.status_code, 200)
        match = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.get_data(as_text=True))
        self.assertIsNotNone(match)
        return match.group(1)

    def issue_via_owner_form(self, name="New Coach", email="coach@truecosmic.com"):
        self.login_as_owner()
        csrf_token = self.invite_form_token()
        with patch("app.coach.public.send_email") as send_email:
            response = self.client.post(
                "/dashboard/owner/invite-coach",
                data={"name": name, "email": email, "csrf_token": csrf_token},
            )
        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once()
        with self.client.session_transaction() as session:
            invite_url = session["latest_coach_invite_url"]
        token = parse_qs(urlparse(invite_url).query)["invite"][0]
        invite = CoachInvite.query.filter_by(token_hash=CoachInvite.token_hash_for(token)).one()
        return invite, token

    def test_open_registration_is_locked_after_owner_exists(self):
        response = self.client.get("/auth/register")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"A coach invitation is required", response.data)
        self.assertNotIn(b'name="password"', response.data)

    def test_owner_can_email_a_one_time_invitation_and_coach_can_accept_it(self):
        invite, token = self.issue_via_owner_form()
        self.client.get("/auth/logout")

        registration_page = self.client.get(f"/auth/register?invite={token}")
        self.assertEqual(registration_page.status_code, 200)
        self.assertIn(b"Create your coach account", registration_page.data)
        self.assertIn(b"coach@truecosmic.com", registration_page.data)

        registration = self.client.post(
            "/auth/register",
            data={
                "invite": token,
                "name": "New Coach",
                "email": "coach@truecosmic.com",
                "password": self.password(),
                "password2": self.password(),
                "timezone": "Europe/London",
            },
        )

        self.assertEqual(registration.status_code, 302)
        self.assertTrue(registration.headers["Location"].endswith("/auth/login"))
        coach = User.query.filter_by(email="coach@truecosmic.com").one()
        self.assertEqual(coach.role, "host")
        self.assertEqual(coach.timezone, "Europe/London")
        self.assertEqual(invite.accepted_by_user_id, coach.id)
        self.assertIsNotNone(invite.accepted_at)

    def test_invitation_cannot_be_reused_or_used_with_another_email(self):
        invite, token = self.issue_via_owner_form(email="single-use@truecosmic.com")
        self.client.get("/auth/logout")
        accepted = self.client.post(
            "/auth/register",
            data={
                "invite": token,
                "name": "Single Use",
                "email": "single-use@truecosmic.com",
                "password": self.password(),
                "password2": self.password(),
                "timezone": "UTC",
            },
        )
        self.assertEqual(accepted.status_code, 302)

        reused = self.client.get(f"/auth/register?invite={token}")
        self.assertEqual(reused.status_code, 200)
        self.assertIn(b"A coach invitation is required", reused.data)
        self.assertEqual(User.query.filter_by(email="single-use@truecosmic.com").count(), 1)

        second_invite, second_token = CoachInvite.issue(
            email="bound-email@truecosmic.com",
            name="Bound Email Coach",
            invited_by_user_id=self.owner.id,
        )
        db.session.add(second_invite)
        db.session.commit()
        wrong_email = self.client.post(
            "/auth/register",
            data={
                "invite": second_token,
                "name": "Bound Email Coach",
                "email": "other@truecosmic.com",
                "password": self.password(),
                "password2": self.password(),
                "timezone": "UTC",
            },
        )
        self.assertEqual(wrong_email.status_code, 200)
        self.assertIn(b"Use the email address that received this coach invitation.", wrong_email.data)
        self.assertEqual(User.query.filter_by(email="other@truecosmic.com").count(), 0)
        self.assertIsNone(second_invite.accepted_at)
        self.assertIsNotNone(invite.accepted_at)

    def test_reissuing_an_invite_invalidates_the_earlier_link(self):
        first_invite, first_token = self.issue_via_owner_form(email="replace@truecosmic.com")
        second_invite, second_token = self.issue_via_owner_form(email="replace@truecosmic.com")

        self.assertLessEqual(first_invite.expires_at, second_invite.created_at)
        self.assertNotEqual(first_token, second_token)
        self.client.get("/auth/logout")
        expired_page = self.client.get(f"/auth/register?invite={first_token}")
        current_page = self.client.get(f"/auth/register?invite={second_token}")
        self.assertIn(b"A coach invitation is required", expired_page.data)
        self.assertIn(b"Create your coach account", current_page.data)

    def test_first_registration_still_creates_the_initial_owner(self):
        db.session.query(CoachInvite).delete()
        db.session.query(User).delete()
        db.session.commit()
        db.session.expunge_all()

        response = self.client.post(
            "/auth/register",
            data={
                "name": "Initial Owner",
                "email": "initial-owner@example.test",
                "password": self.password(),
                "password2": self.password(),
                "timezone": "UTC",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.query.filter_by(email="initial-owner@example.test").one().role, "owner")


if __name__ == "__main__":
    unittest.main()
