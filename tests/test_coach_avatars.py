"""Coach avatars on /coaches: read from the coaches site, never break the page."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["SYNC_POST_BOOKING"] = "0"

from app import create_app, db
from app.coach import avatars
from app.models.coach_profile import CoachProfile
from app.models.user import User

SITE = avatars.COACHES_SITE_URL

COACHES_PAYLOAD = [
    {"slug": "robert-meade", "name": "Robert Meade", "profileImage": "https://truecosmic.com/academy/robert.jpg.webp"},
    {"slug": "isaac-adegbe", "name": "Isaac Adegbe", "profileImage": "https://truecosmic.com/academy/isaac.jpg.webp"},
    {"slug": "blanca-castillo", "name": "Blanca Celis Castillo", "profileImage": "https://res.cloudinary.com/x/blanca"},
    {"slug": "hadassah-headley", "name": "Hadassah Headley", "profileImage": "/api/storage/objects/uploads/abc"},
    {"slug": "cheryl-andrisani", "name": "Cheryl Andrisani", "profileImage": "https://truecosmic.com/academy/cheryl.jpg.webp"},
    {"slug": "no-photo", "name": "No Photo", "profileImage": None},
    {"slug": "bad-photo", "name": "Bad Photo", "profileImage": "javascript:alert(1)"},
]


def _response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


class ResolveImageUrlTests(unittest.TestCase):
    def test_absolute_urls_pass_through(self):
        self.assertEqual(avatars.resolve_image_url("https://a.test/x.jpg"), "https://a.test/x.jpg")

    def test_relative_upload_path_points_at_coaches_site(self):
        self.assertEqual(avatars.resolve_image_url("/api/storage/objects/uploads/abc"), SITE + "/api/storage/objects/uploads/abc")

    def test_protocol_relative(self):
        self.assertEqual(avatars.resolve_image_url("//cdn.test/x.jpg"), "https://cdn.test/x.jpg")

    def test_rejects_empty_and_unsafe_values(self):
        for bad in (None, "", "   ", "javascript:alert(1)", "data:image/png;base64,AAAA", 42):
            self.assertIsNone(avatars.resolve_image_url(bad), bad)


class InitialsTests(unittest.TestCase):
    def test_initials(self):
        self.assertEqual(avatars.initials_for("Robert Meade"), "RM")
        self.assertEqual(avatars.initials_for("Blanca Celis Castillo"), "BC")
        self.assertEqual(avatars.initials_for("isaac"), "I")
        self.assertEqual(avatars.initials_for(""), "?")
        self.assertEqual(avatars.initials_for(None), "?")


class AvatarLookupTests(unittest.TestCase):
    def setUp(self):
        avatars.reset_cache()

    def test_matches_by_slug_alias_and_name(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            # Same slug on both sites.
            self.assertEqual(avatars.avatar_for("cheryl-andrisani", "Anything"), "https://truecosmic.com/academy/cheryl.jpg.webp")
            # Slugs that differ between the two apps.
            self.assertEqual(avatars.avatar_for("robert", "Robert"), "https://truecosmic.com/academy/robert.jpg.webp")
            self.assertEqual(avatars.avatar_for("isaac", "Isaac"), "https://truecosmic.com/academy/isaac.jpg.webp")
            self.assertEqual(avatars.avatar_for("blanca-celis", "Blanca Celis"), "https://res.cloudinary.com/x/blanca")
            # Uploaded photo served by the coaches site.
            self.assertEqual(avatars.avatar_for("hadassah-headley", "Hadassah Headley"), SITE + "/api/storage/objects/uploads/abc")
            # Unknown slug, but the full name matches.
            self.assertEqual(avatars.avatar_for("some-new-slug", "Cheryl  Andrisani"), "https://truecosmic.com/academy/cheryl.jpg.webp")

    def test_no_match_or_no_usable_photo_returns_none(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            self.assertIsNone(avatars.avatar_for("truecosmic-team", "the TrueCosmic team"))
            self.assertIsNone(avatars.avatar_for("no-photo", "No Photo"))
            self.assertIsNone(avatars.avatar_for("bad-photo", "Bad Photo"))
            self.assertIsNone(avatars.avatar_for(None, None))

    def test_list_is_fetched_once_and_cached(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)) as get:
            avatars.avatar_for("robert", "Robert")
            avatars.avatar_for("isaac", "Isaac")
            avatars.avatar_for("cheryl-andrisani", "Cheryl Andrisani")
            self.assertEqual(get.call_count, 1)

    def test_failure_returns_none_and_is_not_retried_straight_away(self):
        with patch.object(avatars.requests, "get", side_effect=RuntimeError("coaches site down")) as get:
            self.assertIsNone(avatars.avatar_for("robert", "Robert"))
            self.assertIsNone(avatars.avatar_for("isaac", "Isaac"))
            self.assertEqual(get.call_count, 1)

    def test_failed_refresh_keeps_the_last_good_list(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            self.assertIsNotNone(avatars.avatar_for("robert", "Robert"))
        # Make the cache stale, then have the refresh fail.
        avatars._cache["fetched_at"] = 1.0
        avatars._cache["next_attempt_at"] = 0.0
        with patch.object(avatars.requests, "get", side_effect=RuntimeError("down")):
            self.assertEqual(avatars.avatar_for("robert", "Robert"), "https://truecosmic.com/academy/robert.jpg.webp")

    def test_unexpected_payload_is_ignored(self):
        with patch.object(avatars.requests, "get", return_value=_response({"error": "nope"})):
            self.assertIsNone(avatars.avatar_for("robert", "Robert"))


class CoachesPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()

    def setUp(self):
        avatars.reset_cache()
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        for email, name, slug in (
            ("robert@example.test", "Robert Meade", "robert"),
            ("team@example.test", "TrueCosmic Team", "truecosmic-team"),
        ):
            user = User(email=email, name=name, role="host", timezone="UTC")
            user.set_password("test-password")
            db.session.add(user)
            db.session.commit()
            db.session.add(CoachProfile(user_id=user.id, slug=slug, timezone="UTC"))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_page_shows_photo_where_there_is_one_and_initials_otherwise(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            resp = self.client.get("/coaches")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(html.count("object-cover object-top"), 1)  # only Robert has a photo
        self.assertIn('alt="Robert Meade"', html)
        self.assertIn("https://truecosmic.com/academy/robert.jpg.webp", html)
        self.assertIn(">RM<", html)
        self.assertIn(">TT<", html)

    def test_page_still_renders_when_coaches_site_is_down(self):
        with patch.object(avatars.requests, "get", side_effect=RuntimeError("down")):
            resp = self.client.get("/coaches")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Robert Meade", html)
        self.assertIn(">RM<", html)
        self.assertNotIn('alt="Robert Meade"', html)

    def test_coach_own_page_shows_their_photo_or_initials(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            html = self.client.get("/c/robert").get_data(as_text=True)
            self.assertIn('class="coach-avatar-photo"', html)
            self.assertIn("https://truecosmic.com/academy/robert.jpg.webp", html)
            self.assertIn("What happens when you book", html)
            self.assertIn('href="/#features"', html)
            self.assertIn('href="/#how"', html)
            html = self.client.get("/c/truecosmic-team").get_data(as_text=True)
        self.assertNotIn('class="coach-avatar-photo"', html)
        self.assertIn(">TT<", html)


if __name__ == "__main__":
    unittest.main()
