import os
import json
from typing import Optional, Dict, Any
import logging

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


log = logging.getLogger(__name__)


class BotPenguinClient:
    """Minimal BotPenguin API client used for contact lookup and update.

    Env vars:
      - BOTPENGUIN_API_KEY (required)
      - BOTPENGUIN_BOT_ID (required)
      - BOTPENGUIN_PLATFORM (optional; default: website)
      - BOTPENGUIN_BASE_URL (optional; default: https://api.botpenguin.com)
      - BOTPENGUIN_SEARCH_PATH (optional; default: /api/v2/contacts/search)
      - BOTPENGUIN_UPDATE_PATH (optional; default: /api/v2/contacts/{contact_id})
    """

    def __init__(self):
        self.api_key = os.getenv("BOTPENGUIN_API_KEY", "").strip()
        self.bot_id = os.getenv("BOTPENGUIN_BOT_ID", "").strip()
        self.platform = os.getenv("BOTPENGUIN_PLATFORM", "website").strip() or "website"
        self.base_url = os.getenv("BOTPENGUIN_BASE_URL", "https://api.botpenguin.com").rstrip("/")
        self.search_path = os.getenv("BOTPENGUIN_SEARCH_PATH", "/api/v2/contacts/search")
        self.update_path = os.getenv("BOTPENGUIN_UPDATE_PATH", "/api/v2/contacts/{contact_id}")

        if not self.api_key or not self.bot_id:
            raise RuntimeError("BotPenguin credentials not configured")
        if requests is None:
            raise RuntimeError("The 'requests' package is required for BotPenguin integration")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def find_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        params = {"botId": self.bot_id, "platform": self.platform, "email": email}
        url = self._url(self.search_path)
        try:
            r = requests.get(url, headers=self._headers(), params=params, timeout=10)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json() if r.content else {}
            if isinstance(data, dict):
                if isinstance(data.get("contacts"), list) and data["contacts"]:
                    return data["contacts"][0]
                if data.get("id"):
                    return data
            if isinstance(data, list) and data:
                return data[0]
        except Exception as e:
            log.warning("BotPenguin search failed: %s", e)
        return None

    def update_contact_attributes(self, contact_id: str, attrs: Dict[str, Any]) -> bool:
        path = self.update_path.replace("{contact_id}", contact_id)
        url = self._url(path)
        body = {"botId": self.bot_id, "platform": self.platform, "attributes": attrs}
        try:
            r = requests.patch(url, headers=self._headers(), data=json.dumps(body), timeout=10)
            return 200 <= r.status_code < 300
        except Exception as e:
            log.warning("BotPenguin update failed: %s", e)
            return False


def sync_booking_to_botpenguin(visitor_email: str, booking_time_local_iso: str, coach_name: str) -> None:
    try:
        client = BotPenguinClient()
    except Exception as e:
        log.info("BotPenguin not configured: %s", e)
        return

    contact = client.find_contact_by_email(visitor_email)
    if not contact:
        log.info("BotPenguin: no contact found for %s", visitor_email)
        return

    contact_id = str(contact.get("id") or contact.get("_id") or contact.get("uuid") or "").strip()
    if not contact_id:
        log.info("BotPenguin: contact found without id, skipping")
        return

    ok = client.update_contact_attributes(contact_id, {
        "booking_time": booking_time_local_iso,
        "demo_session_coach": coach_name,
    })
    if ok:
        log.info("BotPenguin: updated contact %s", contact_id)
    else:
        log.warning("BotPenguin: failed to update contact %s", contact_id)

