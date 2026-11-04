"""Coach avatars for the public /coaches page.

Photos come from the coaches site (coaches.truecosmic.com) so a coach's photo
only ever needs changing in one place. The URLs are copied into this app's own
database (coach_avatar table) by a background sync, and pages read only that
copy, so a slow or unavailable coaches site never slows a page down, and the
photos survive deploys. No photo simply falls back to the coach's initials.
"""

import logging
import os
import re
import threading
import time

import requests

log = logging.getLogger(__name__)

COACHES_SITE_URL = os.getenv("COACHES_SITE_URL", "https://coaches.truecosmic.com").rstrip("/")

CACHE_TTL_SECONDS = 3600  # how often the saved copy is refreshed
# After a failed fetch, don't try again for this long so every page view
# isn't held up waiting on a coaches site that is down. Kept short: a deploy
# starts with an empty cache, so a slow first answer must not hide photos for long.
FAILURE_RETRY_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 15  # background only, so a slow site costs nothing

# Calendar slug -> coaches-site slug, for coaches whose slug differs between
# the two apps. Anything not listed here is matched by identical slug, then by
# full name.
SLUG_ALIASES = {
    "robert": "robert-meade",
    "isaac": "isaac-adegbe",
    "blanca-celis": "blanca-castillo",
}

_lock = threading.Lock()
_state = {"next_sync_at": 0.0, "running": False}


def reset_cache() -> None:
    """Forget sync timing (used by tests)."""
    with _lock:
        _state.update(next_sync_at=0.0, running=False)


def _normalise_name(name: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (name or "").lower()))


def resolve_image_url(image) -> str | None:
    """Turn a coaches-site image value into an absolute http(s) URL, or None."""
    if not isinstance(image, str):
        return None
    image = image.strip()
    if not image:
        return None
    if image.startswith("//"):
        return "https:" + image
    if image.startswith("/"):
        # Uploaded photos are served by the coaches site itself.
        return COACHES_SITE_URL + image
    if image.lower().startswith(("https://", "http://")):
        return image
    return None


def _fetch_coaches() -> list | None:
    try:
        resp = requests.get(f"{COACHES_SITE_URL}/api/coaches", timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Coach avatars: could not fetch coaches list: %s", exc)
        return None
    if isinstance(data, dict):
        data = data.get("coaches")
    return data if isinstance(data, list) else None


def sync_now() -> bool:
    """Copy the coaches site's photo URLs into the database. Needs an app context.

    Returns True if the list was fetched and saved. On any failure the existing
    copy is left untouched.
    """
    from app import db
    from app.models.coach_avatar import CoachAvatar

    coaches = _fetch_coaches()
    if coaches is None:
        return False
    rows = {}
    for c in coaches:
        if not isinstance(c, dict):
            continue
        url = resolve_image_url(c.get("profileImage"))
        slug = (c.get("slug") or "").strip().lower()
        if url and slug:
            rows[slug] = (_normalise_name(c.get("name") or ""), url)
    try:
        existing = {r.site_slug: r for r in CoachAvatar.query.all()}
        for slug, (name_key, url) in rows.items():
            row = existing.pop(slug, None)
            if row is None:
                db.session.add(CoachAvatar(site_slug=slug, name_key=name_key, image_url=url))
            else:
                row.name_key, row.image_url = name_key, url
        for stale in existing.values():  # coach removed their photo or left
            db.session.delete(stale)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Coach avatars: could not save the coaches list")
        return False
    return True


def _sync_in_thread(app) -> None:
    ok = False
    try:
        with app.app_context():
            ok = sync_now()
    except Exception:
        log.exception("Coach avatars: background sync failed")
    with _lock:
        _state["running"] = False
        _state["next_sync_at"] = time.time() + (CACHE_TTL_SECONDS if ok else FAILURE_RETRY_SECONDS)


def sync_in_background(app, force: bool = False) -> bool:
    """Start a background sync if one is due. Never blocks the caller."""
    with _lock:
        if _state["running"] or (not force and time.time() < _state["next_sync_at"]):
            return False
        _state["running"] = True
    threading.Thread(target=_sync_in_thread, args=(app,), name="coach-avatar-sync", daemon=True).start()
    return True


class AvatarIndex:
    def __init__(self, by_slug: dict, by_name: dict):
        self.by_slug, self.by_name = by_slug, by_name

    def get(self, slug: str | None, name: str | None = None) -> str | None:
        slug = (slug or "").strip().lower()
        if slug:
            url = self.by_slug.get(SLUG_ALIASES.get(slug, slug))
            if url:
                return url
        normalised = _normalise_name(name or "")
        return self.by_name.get(normalised) if normalised else None


def avatar_index() -> AvatarIndex:
    """Photo lookup read from the database; kicks off a refresh in the background when due."""
    from flask import current_app
    from app.models.coach_avatar import CoachAvatar

    if not current_app.config.get("TESTING"):
        sync_in_background(current_app._get_current_object())
    try:
        rows = CoachAvatar.query.all()
    except Exception:
        log.exception("Coach avatars: could not read saved photos")
        return AvatarIndex({}, {})
    return AvatarIndex({r.site_slug: r.image_url for r in rows}, {r.name_key: r.image_url for r in rows if r.name_key})


def initials_for(name: str | None) -> str:
    """Up to two capital letters for the fallback avatar."""
    words = re.findall(r"[^\W_]+", name or "", flags=re.UNICODE)
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()
