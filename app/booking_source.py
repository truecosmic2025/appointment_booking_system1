"""Where a booking came from (website chat, a WhatsApp ad, a Jess call, ...).

Booking links carry ``?src=<source>&ref=<id>``; the booking page passes them to
``/api/book/<slug>``, which stores them on ``booking.source`` / ``booking.source_ref``.
The owner dashboard groups bookings by source so coach performance can be read per channel.
Values come from the URL, so they are cleaned to a short, safe slug before they are stored.
"""

import re

_SOURCE_RE = re.compile(r"[^a-z0-9_-]+")
_REF_RE = re.compile(r"[^A-Za-z0-9_-]+")

DIRECT = "direct"

SOURCE_LABELS = {
    DIRECT: "Direct (no source)",
    "web-chat": "Website chat (Claudde)",
    "whatsapp-chat": "WhatsApp chat (Claudde)",
    "messenger-chat": "Messenger chat (Claudde)",
    "instagram-chat": "Instagram chat (Claudde)",
    "whatsapp-done-deal-starter-kit": "WhatsApp ad: Done Deal",
    "whatsapp-twelve-disciples-guide": "WhatsApp ad: Hidden Scriptures",
    "jess-call": "Jess call",
}


def clean_source(value) -> str | None:
    """Lower-case slug of at most 64 characters, or None when nothing usable is left."""
    if not isinstance(value, str):
        return None
    slug = _SOURCE_RE.sub("-", value.strip().lower()).strip("-")[:64].strip("-")
    return slug or None


def clean_ref(value) -> str | None:
    """Reference id (e.g. a chat conversation id) of at most 128 safe characters, or None."""
    if not isinstance(value, str):
        return None
    ref = _REF_RE.sub("", value.strip())[:128]
    return ref or None


def source_label(source: str | None) -> str:
    if not source:
        return SOURCE_LABELS[DIRECT]
    if source in SOURCE_LABELS:
        return SOURCE_LABELS[source]
    return source.replace("-", " ").replace("_", " ").capitalize()
