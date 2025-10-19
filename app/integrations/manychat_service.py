import os
import logging
from typing import Any, Dict, Optional

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


log = logging.getLogger(__name__)


class ManyChatClient:
    """Minimal ManyChat API client for email-based contact upsert, tagging, and custom fields.

    Env vars:
      - MANYCHAT_API_KEY (required)
      - MANYCHAT_BASE_URL (optional; default: https://api.manychat.com)
      - MANYCHAT_TAG_NAME (optional; default: lead_from_website_bot)
      - MANYCHAT_BOOKING_TIME_FIELD (optional; default: 30min_booking_time)
      - MANYCHAT_COACH_FIELD (optional; default: demo_session_coach)
    """

    def __init__(self) -> None:
        if requests is None:
            raise RuntimeError("The 'requests' package is required for ManyChat integration")
        self.api_key = os.getenv("MANYCHAT_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("MANYCHAT_API_KEY not configured")
        self.base_url = os.getenv("MANYCHAT_BASE_URL", "https://api.manychat.com").rstrip("/")

        # Defaults that can be overridden by env
        self.tag_name = os.getenv("MANYCHAT_TAG_NAME", "lead_from_website_bot").strip() or "lead_from_website_bot"
        self.booking_time_field = os.getenv("MANYCHAT_BOOKING_TIME_FIELD", "30min_booking_time").strip() or "30min_booking_time"
        self.coach_field = os.getenv("MANYCHAT_COACH_FIELD", "demo_session_coach").strip() or "demo_session_coach"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def find_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Return subscriber object if found by email, else None.

        Tries both parameter styles used by ManyChat docs/SDKs.
        """
        attempts = [
            {"email": email},
            {"field": "email", "value": email},
        ]
        for idx, params in enumerate(attempts, start=1):
            try:
                r = requests.get(
                    self._url("/fb/subscriber/findBySystemField"),
                    headers=self._headers(),
                    params=params,
                    timeout=20,
                )
                if r.status_code != 200:
                    log.info(
                        "ManyChat findBySystemField attempt %s failed: %s %s",
                        idx,
                        r.status_code,
                        (r.text or "")[:300],
                    )
                    continue
                data = r.json() if r.content else {}
                if isinstance(data, dict):
                    if data.get("status") == "success" and isinstance(data.get("data"), dict):
                        log.info("ManyChat findBySystemField success on attempt %s for %s", idx, email)
                        return data["data"]
                    if data.get("status") == "error":
                        log.info("ManyChat findBySystemField attempt %s error: %s", idx, data)
                else:
                    log.info("ManyChat findBySystemField attempt %s unexpected payload: %s", idx, type(data).__name__)
            except Exception as e:
                log.info("ManyChat find error on attempt %s: %s", idx, e)
        return None

    def _subscriber_id_to_int(self, subscriber: Dict[str, Any]) -> Optional[int]:
        sid = subscriber.get("id")
        try:
            # ManyChat often returns id as string that is numeric
            return int(str(sid))
        except Exception:
            return None

    def create_contact_with_email(self, email: str, first_name: str = "", last_name: str = "") -> Optional[Dict[str, Any]]:
        """Create a ManyChat unified subscriber with email channel and explicit consent."""
        payload: Dict[str, Any] = {
            "email": email,
            "has_opt_in_email": True,
        }
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        # Optional but helpful for compliance/transparency
        payload["consent_phrase"] = os.getenv("MANYCHAT_CONSENT_PHRASE", "Booked via website")

        try:
            r = requests.post(
                self._url("/fb/subscriber/createSubscriber"),
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            if r.status_code != 200:
                log.info("ManyChat createSubscriber failed: %s %s", r.status_code, r.text[:300])
                return None
            data = r.json() if r.content else {}
            if isinstance(data, dict) and data.get("status") == "success" and isinstance(data.get("data"), dict):
                # Some responses return { status, data: { subscriber: {...} } } — be flexible
                sub = data.get("data", {}).get("subscriber") or data.get("data")
                if isinstance(sub, dict):
                    return sub
            return None
        except Exception as e:
            log.info("ManyChat create error: %s", e)
            return None

    def add_tag_by_name(self, subscriber_id: int, tag_name: str) -> bool:
        try:
            r = requests.post(
                self._url("/fb/subscriber/addTagByName"),
                headers=self._headers(),
                json={"subscriber_id": subscriber_id, "tag_name": tag_name},
                timeout=15,
            )
            if 200 <= r.status_code < 300:
                js = r.json() if r.content else {}
                if isinstance(js, dict) and js.get("status") == "success":
                    log.info("ManyChat addTagByName success: tag=%s subscriber_id=%s", tag_name, subscriber_id)
                    return True
                log.info("ManyChat addTagByName error: %s", js)
            else:
                log.info("ManyChat addTagByName failed: %s %s", r.status_code, (r.text or "")[:300])
            return False
        except Exception as e:
            log.info("ManyChat tag error: %s", e)
            return False

    def set_field_by_name(self, subscriber_id: int, field_name: str, field_value: Any) -> bool:
        try:
            r = requests.post(
                self._url("/fb/subscriber/setCustomFieldByName"),
                headers=self._headers(),
                json={
                    "subscriber_id": subscriber_id,
                    "field_name": field_name,
                    "field_value": field_value,
                },
                timeout=15,
            )
            if 200 <= r.status_code < 300 and r.json().get("status") == "success":
                return True
            # If field not found, try to create the custom field then retry once
            txt = (r.text or "")
            if "field not found" in txt.lower() or "custom field not found" in txt.lower():
                if self._ensure_custom_field(field_name):
                    r2 = requests.post(
                        self._url("/fb/subscriber/setCustomFieldByName"),
                        headers=self._headers(),
                        json={
                            "subscriber_id": subscriber_id,
                            "field_name": field_name,
                            "field_value": field_value,
                        },
                        timeout=15,
                    )
                    return 200 <= r2.status_code < 300 and r2.json().get("status") == "success"
            log.info("ManyChat setCustomFieldByName failed: %s %s", r.status_code, txt[:300])
            return False
        except Exception as e:
            log.info("ManyChat set field error: %s", e)
            return False

    def _get_custom_fields_map(self) -> Dict[str, Dict[str, Any]]:
        """Return a dict mapping lowercased field names to field objects."""
        out: Dict[str, Dict[str, Any]] = {}
        try:
            r = requests.get(self._url("/fb/page/getCustomFields"), headers=self._headers(), timeout=20)
            if r.status_code != 200:
                return out
            js = r.json() or {}
            if isinstance(js, dict) and js.get("status") == "success":
                for it in js.get("data", []) or []:
                    nm = str(it.get("name") or it.get("caption") or "").strip()
                    if nm:
                        out[nm.lower()] = it
        except Exception:
            pass
        return out

    def set_fields_bulk_by_name(self, subscriber_id: int, fields: Dict[str, Any]) -> bool:
        """Set multiple fields using a single API call by resolving names to IDs.

        Falls back to per-field API if bulk fails.
        """
        try:
            existing = self._get_custom_fields_map()
            payload_items = []
            missing: list[str] = []
            for name, value in fields.items():
                key = name.lower()
                if key in existing and existing[key].get("id") is not None:
                    try:
                        fid = int(existing[key]["id"])
                    except Exception:
                        continue
                    payload_items.append({
                        "field_id": fid,
                        "field_name": name,
                        "field_value": value,
                    })
                else:
                    missing.append(name)

            # Create any missing fields (use type datetime for booking_time_field)
            created_any = False
            for name in missing:
                if self._ensure_custom_field(name):
                    created_any = True

            if created_any:
                # Refresh map
                existing = self._get_custom_fields_map()
                for name in missing:
                    key = name.lower()
                    if key in existing and existing[key].get("id") is not None:
                        try:
                            fid = int(existing[key]["id"])
                        except Exception:
                            continue
                        payload_items.append({
                            "field_id": fid,
                            "field_name": name,
                            "field_value": fields[name],
                        })

            if payload_items:
                r = requests.post(
                    self._url("/fb/subscriber/setCustomFields"),
                    headers=self._headers(),
                    json={
                        "subscriber_id": subscriber_id,
                        "fields": payload_items,
                    },
                    timeout=20,
                )
                if 200 <= r.status_code < 300:
                    js = r.json() if r.content else {}
                    if isinstance(js, dict) and js.get("status") == "success":
                        log.info("ManyChat setCustomFields success for subscriber_id=%s fields=%s", subscriber_id, list(fields.keys()))
                        return True
                    log.info("ManyChat setCustomFields error: %s", js)
                else:
                    log.info("ManyChat setCustomFields failed: %s %s", r.status_code, (r.text or "")[:300])

            # Fallback: set individually
            ok_all = True
            for name, value in fields.items():
                if not self.set_field_by_name(subscriber_id, name, value):
                    ok_all = False
            return ok_all
        except Exception as e:
            log.info("ManyChat bulk set error: %s", e)
            return False

    def _ensure_custom_field(self, field_name: str) -> bool:
        """Ensure custom field exists; create as text if missing."""
        try:
            # List existing fields
            r = requests.get(self._url("/fb/page/getCustomFields"), headers=self._headers(), timeout=20)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, dict) and js.get("status") == "success":
                    items = js.get("data") or []
                    for it in items:
                        n = str(it.get("name") or it.get("caption") or it.get("field_name") or "").lower()
                        if n == field_name.lower():
                            return True
            # Create if not present
            # Choose appropriate field type: use 'datetime' for booking time field, else 'text'
            ftype = "datetime" if field_name.lower() == self.booking_time_field.lower() else "text"
            r2 = requests.post(
                self._url("/fb/page/createCustomField"),
                headers=self._headers(),
                json={"caption": field_name, "type": ftype, "description": "Auto-created by booking sync"},
                timeout=20,
            )
            if 200 <= r2.status_code < 300:
                log.info("ManyChat created custom field '%s' of type %s", field_name, ftype)
                return True
        except Exception as e:
            log.info("ManyChat ensure field error: %s", e)
        return False


def sync_booking_to_manychat(visitor_email: str, booking_time_utc_iso: str, coach_name: str, visitor_name: str | None = None) -> None:
    """Upsert visitor into ManyChat, add tag, and set custom fields.

    Best-effort: logs issues and returns without raising.
    """
    try:
        client = ManyChatClient()
    except Exception as e:
        log.info("ManyChat not configured: %s", e)
        return

    sub = client.find_contact_by_email(visitor_email)
    if not sub:
        # Create new contact with consent
        first, last = "", ""
        if visitor_name:
            parts = [p for p in str(visitor_name).split(" ") if p]
            if parts:
                first = parts[0]
                last = " ".join(parts[1:]) if len(parts) > 1 else ""
        sub = client.create_contact_with_email(visitor_email, first, last)
        if not sub:
            log.info("ManyChat: failed to create subscriber for %s", visitor_email)
            return

    sid = client._subscriber_id_to_int(sub)
    if not sid:
        log.info("ManyChat: invalid subscriber id for %s", visitor_email)
        return

    # Tag the contact (best-effort)
    client.add_tag_by_name(sid, client.tag_name)

    # Set/update fields in bulk for better reliability
    client.set_fields_bulk_by_name(
        sid,
        {
            client.booking_time_field: booking_time_utc_iso,
            client.coach_field: coach_name,
        },
    )
