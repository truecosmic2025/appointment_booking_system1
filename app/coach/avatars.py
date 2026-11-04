"""Coach avatars for the public /coaches page.

Photos are read from the coaches site (coaches.truecosmic.com) so a coach's
photo only ever needs changing in one place. Nothing is stored in this app's
database: the list is fetched from the coaches site's public API, cached in
memory, and any failure simply falls back to the coach's initials. A slow or
unavailable coaches site must never break or noticeably slow the page.
"""

import logging
import os
import re
import threading
import time

import requests

log = logging.getLogger(__name__)

COACHES_SITE_URL = os.getenv("COACHES_SITE_URL", "https://coaches.truecosmic.com").rstrip("/")

CACHE_TTL_SECONDS = 3600
# After a failed fetch, don't try again for this long so every page view
# isn't held up waiting on a coaches site that is down. Kept short: a deploy
# starts with an empty cache, so a slow first answer must not hide photos for long.
FAILURE_RETRY_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 6

# Calendar slug -> coaches-site slug, for coaches whose slug differs between
# the two apps. Anything not listed here is matched by identical slug, then by
# full name.
SLUG_ALIASES = {
    "robert": "robert-meade",
    "isaac": "isaac-adegbe",
    "blanca-celis": "blanca-castillo",
}

_lock = threading.Lock()
_cache = {"by_slug": {}, "by_name": {}, "fetched_at": 0.0, "next_attempt_at": 0.0}


def reset_cache() -> None:
    """Forget everything cached (used by tests)."""
    with _lock:
        _cache.update(by_slug={}, by_name={}, fetched_at=0.0, next_attempt_at=0.0)


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


def _refresh_if_needed() -> None:
    now = time.time()
    with _lock:
        fresh = _cache["fetched_at"] and now - _cache["fetched_at"] < CACHE_TTL_SECONDS
        if fresh or now < _cache["next_attempt_at"]:
            return
        # Claim this attempt so concurrent requests don't all fetch at once.
        _cache["next_attempt_at"] = now + FAILURE_RETRY_SECONDS

    coaches = _fetch_coaches()
    if coaches is None:
        return  # keep whatever we had; next_attempt_at already delays a retry

    by_slug, by_name = {}, {}
    for c in coaches:
        if not isinstance(c, dict):
            continue
        url = resolve_image_url(c.get("profileImage"))
        if not url:
            continue
        slug = (c.get("slug") or "").strip().lower()
        if slug:
            by_slug[slug] = url
        name = _normalise_name(c.get("name") or "")
        if name:
            by_name[name] = url

    with _lock:
        _cache.update(by_slug=by_slug, by_name=by_name, fetched_at=time.time(), next_attempt_at=0.0)


def avatar_for(slug: str | None, name: str | None = None) -> str | None:
    """Best avatar URL for a calendar coach, or None if there isn't one."""
    _refresh_if_needed()
    with _lock:
        by_slug, by_name = _cache["by_slug"], _cache["by_name"]
        slug = (slug or "").strip().lower()
        if slug:
            site_slug = SLUG_ALIASES.get(slug, slug)
            if site_slug in by_slug:
                return by_slug[site_slug]
        normalised = _normalise_name(name or "")
        return by_name.get(normalised) if normalised else None


def initials_for(name: str | None) -> str:
    """Up to two capital letters for the fallback avatar."""
    words = re.findall(r"[^\W_]+", name or "", flags=re.UNICODE)
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


def warm_up_in_background() -> None:
    """Fetch the coaches list at start-up so the first visitors already get photos."""
    threading.Thread(target=_refresh_if_needed, name="coach-avatar-warmup", daemon=True).start()
