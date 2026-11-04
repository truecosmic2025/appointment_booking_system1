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


class AvatarSyncTests(unittest.TestCase):
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

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def sync(self, payload=None, error=None):
        kw = {"side_effect": error} if error else {"return_value": _response(payload)}
        with patch.object(avatars.requests, "get", **kw) as get:
            return avatars.sync_now(), get

    def test_matches_by_slug_alias_and_name_from_saved_copy(self):
        ok, _ = self.sync(COACHES_PAYLOAD)
        self.assertTrue(ok)
        idx = avatars.avatar_index()
        self.assertEqual(idx.get("cheryl-andrisani", "Anything"), "https://truecosmic.com/academy/cheryl.jpg.webp")
        self.assertEqual(idx.get("robert", "Robert"), "https://truecosmic.com/academy/robert.jpg.webp")
        self.assertEqual(idx.get("isaac", "Isaac"), "https://truecosmic.com/academy/isaac.jpg.webp")
        self.assertEqual(idx.get("blanca-celis", "Blanca Celis"), "https://res.cloudinary.com/x/blanca")
        self.assertEqual(idx.get("hadassah-headley", "Hadassah Headley"), SITE + "/api/storage/objects/uploads/abc")
        self.assertEqual(idx.get("some-new-slug", "Cheryl  Andrisani"), "https://truecosmic.com/academy/cheryl.jpg.webp")

    def test_no_match_or_no_usable_photo_returns_none(self):
        self.sync(COACHES_PAYLOAD)
        idx = avatars.avatar_index()
        for slug, name in (("truecosmic-team", "the TrueCosmic team"), ("no-photo", "No Photo"), ("bad-photo", "Bad Photo"), (None, None)):
            self.assertIsNone(idx.get(slug, name))

    def test_pages_read_only_the_saved_copy_and_never_fetch(self):
        self.sync(COACHES_PAYLOAD)
        with patch.object(avatars.requests, "get", side_effect=AssertionError("must not fetch")):
            self.assertIsNotNone(avatars.avatar_index().get("robert", "Robert"))

    def test_failed_sync_keeps_the_saved_copy(self):
        self.sync(COACHES_PAYLOAD)
        ok, _ = self.sync(error=RuntimeError("coaches site down"))
        self.assertFalse(ok)
        self.assertEqual(avatars.avatar_index().get("robert", "Robert"), "https://truecosmic.com/academy/robert.jpg.webp")

    def test_unexpected_payload_changes_nothing(self):
        self.sync(COACHES_PAYLOAD)
        ok, _ = self.sync({"error": "nope"})
        self.assertFalse(ok)
        self.assertIsNotNone(avatars.avatar_index().get("robert", "Robert"))

    def test_removed_photo_is_dropped_on_next_sync(self):
        self.sync(COACHES_PAYLOAD)
        self.sync([{"slug": "robert-meade", "name": "Robert Meade", "profileImage": None}])
        self.assertIsNone(avatars.avatar_index().get("robert", "Robert"))

    def test_background_sync_is_throttled_and_survives_failure(self):
        started = []
        with patch.object(avatars.threading, "Thread") as thread:
            thread.side_effect = lambda **kw: started.append(kw) or MagicMock()
            self.assertTrue(avatars.sync_in_background(self.app, force=True))
            self.assertFalse(avatars.sync_in_background(self.app))  # one already running
        avatars._state["running"] = False
        avatars._state["next_sync_at"] = 9e12
        self.assertFalse(avatars.sync_in_background(self.app))  # not due yet
        self.assertEqual(len(started), 1)


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
            avatars.sync_now()
        resp = self.client.get("/coaches")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(html.count("object-cover object-top"), 1)  # only Robert has a photo
        self.assertIn('alt="Robert Meade"', html)
        self.assertIn("https://truecosmic.com/academy/robert.jpg.webp", html)
        self.assertIn(">RM<", html)
        self.assertIn(">TT<", html)

    def test_page_still_renders_when_coaches_site_is_down(self):
        resp = self.client.get("/coaches")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Robert Meade", html)
        self.assertIn(">RM<", html)
        self.assertNotIn('alt="Robert Meade"', html)

    def test_coach_own_page_shows_their_photo_or_initials(self):
        with patch.object(avatars.requests, "get", return_value=_response(COACHES_PAYLOAD)):
            avatars.sync_now()
        html = self.client.get("/c/robert").get_data(as_text=True)
        self.assertIn('class="coach-avatar-photo"', html)
        self.assertIn("https://truecosmic.com/academy/robert.jpg.webp", html)
        self.assertIn("What happens when you book", html)
        self.assertIn('href="/#features"', html)
        self.assertIn('href="/#how"', html)
        html = self.client.get("/c/truecosmic-team").get_data(as_text=True)
        self.assertNotIn('class="coach-avatar-photo"', html)
        self.assertIn(">TT<", html)

    def test_blanca_page_defaults_to_spanish_with_english_toggle(self):
        user = User(email="blanca@example.test", name="Blanca Celis", role="host", timezone="UTC")
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()
        db.session.add(CoachProfile(user_id=user.id, slug="blanca-celis", timezone="UTC"))
        db.session.commit()
        es = self.client.get("/c/blanca-celis?name=Ana").get_data(as_text=True)
        en = self.client.get("/c/blanca-celis?lang=en").get_data(as_text=True)
        robert = self.client.get("/c/robert").get_data(as_text=True)
        robert_es = self.client.get("/c/robert?lang=es").get_data(as_text=True)
        self.assertIn("Reserva con Blanca Celis", es)
        self.assertIn("Qué ocurre al reservar", es)
        self.assertIn("name=Ana", es)  # prefill survives the language link
        self.assertIn("lang=en", es)
        self.assertIn("Meet with Blanca Celis", en)
        self.assertIn("lang=es", en)
        self.assertIn("Meet with Robert Meade", robert)
        self.assertIn("Reserva con Robert Meade", robert_es)


if __name__ == "__main__":
    unittest.main()
