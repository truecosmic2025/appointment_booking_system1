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
    """BotPenguin API v7 client using inbox endpoints, matching working botpenguin.py logic.

    Env vars:
      - BOTPENGUIN_API_KEY (required)
      - BOTPENGUIN_BASE_URL (optional; default: https://api.v7.botpenguin.com)
      - BOTPENGUIN_LIST_PATH (optional; default: /inbox/users)
      - BOTPENGUIN_UPDATE_PATH (optional; default: /inbox/users/{contact_id}/attributes)
    """

    def __init__(self):
        self.api_key = os.getenv("BOTPENGUIN_API_KEY", "").strip()
        self.base_url = os.getenv("BOTPENGUIN_BASE_URL", "https://api.v7.botpenguin.com").rstrip("/")
        self.list_path = os.getenv("BOTPENGUIN_LIST_PATH", "/inbox/users")
        # Default to updating the user resource directly; some workspaces 404 on the /attributes subpath
        self.update_path = os.getenv("BOTPENGUIN_UPDATE_PATH", "/inbox/users/{contact_id}")

        if not self.api_key:
            raise RuntimeError("BOTPENGUIN_API_KEY not configured")
        if requests is None:
            raise RuntimeError("The 'requests' package is required for BotPenguin integration")

        # Base body copied from the working script
        self._base_body: Dict[str, Any] = {
            "_agentAssigned": [],
            "_botAutomation": [],
            "_botFacebook": [],
            "_botTelegram": [],
            "_botWebsite": [],
            "_botWhatsapp": [],
            "applicableFilters": [],
            "createdAt": {"startAt": "", "endsAt": ""},
            "ctwaNewUsers": False,
            "ctwaOldUsers": False,
            "hasOrdered": {"status": False, "lastAt": ""},
            "isLiveChatActive": False,
            "isOnline": False,
            "isSubscriber": True,
            "lastMessageBy": [],
            "lastSeenAt": {"startAt": "", "endsAt": ""},
            "searchText": "",
            "segments": [],
            "status": [],
            "tags": [],
            "tagsV2": [],
            "userInteracted": False,
            "page": 1,
            "isExport": "none",
            "isContact": False,
        }

    def _headers(self) -> Dict[str, str]:
        # Match header capitalization from the working script
        return {
            "AuthType": "Key",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _extract_email(self, contact: Dict[str, Any]) -> str:
        # Check common locations and attributes list
        paths = [
            ["email"],
            ["profile", "email"],
            ["profile", "userDetails", "contact", "email"],
        ]
        for p in paths:
            cur: Any = contact
            ok = True
            for k in p:
                if not isinstance(cur, dict) or k not in cur:
                    ok = False
                    break
                cur = cur[k]
            if ok and isinstance(cur, str) and cur.strip():
                return cur.strip()
        attrs = (
            contact.get("profile", {})
            .get("userDetails", {})
            .get("attributes", [])
        )
        if isinstance(attrs, list):
            for a in attrs:
                if isinstance(a, dict) and a.get("key") in ("email", "Email"):
                    v = a.get("value")
                    if isinstance(v, str) and v.strip():
                        return v.strip()
        return ""

    def _normalize_phone_e164(self, phone: str, default_country_code: str = None) -> str:
        """
        Normalize phone number to E.164 format.
        E.164: +[country code][subscriber number] (no spaces/formatting)
        
        Args:
            phone: Phone number to normalize
            default_country_code: Default country code to use if number has no + (e.g., "1" for US)
        """
        if not phone:
            return ""
        
        # Remove all non-digit characters except leading +
        cleaned = phone.strip()
        has_plus = cleaned.startswith('+')
        if has_plus:
            cleaned = cleaned[1:]
        
        # Remove all non-digits
        digits = ''.join(c for c in cleaned if c.isdigit())
        
        if not digits:
            return ""
        
        # If had +, check for common formatting issues
        if has_plus:
            # UK: +44 should be followed by 10 digits (no leading 0)
            # Common error: +4407... should be +447...
            if digits.startswith('440') and len(digits) >= 12:
                # Check if removing the 0 gives us valid length
                without_zero = '44' + digits[3:]
                if len(without_zero) <= 15:  # E.164 max length
                    digits = without_zero
            
            # France: +33 followed by 9 digits (no leading 0)
            elif digits.startswith('330') and len(digits) >= 11:
                without_zero = '33' + digits[3:]
                if len(without_zero) <= 15:
                    digits = without_zero
            
            # Spain: +34 followed by 9 digits (no leading 0)
            elif digits.startswith('340') and len(digits) >= 11:
                without_zero = '34' + digits[3:]
                if len(without_zero) <= 15:
                    digits = without_zero
            
            return f"+{digits}"
        
        # No + prefix - need to determine if country code is included
        # This is ambiguous without knowing the source country
        
        # If exactly 10 digits, likely missing country code (US/Canada format)
        if len(digits) == 10:
            # Use default country code or assume US
            country_code = default_country_code or "1"
            return f"+{country_code}{digits}"
        
        # If 11 digits and starts with 1, likely US/Canada with country code
        if len(digits) == 11 and digits.startswith('1'):
            return f"+{digits}"
        
        # If 12+ digits, assume it includes country code
        if len(digits) >= 12:
            # Check for common patterns without +
            # India: 91 followed by 10 digits
            if digits.startswith('91') and len(digits) == 12:
                return f"+{digits}"
            # UK: 44 followed by 10 digits (but check for extra 0)
            elif digits.startswith('44') and len(digits) >= 12:
                # Check if there's an extra 0 after country code
                if digits[2] == '0' and len(digits) == 13:
                    # Remove the extra 0: 4407... → 447...
                    return f"+44{digits[3:]}"
                return f"+{digits}"
            # Otherwise assume it has country code
            return f"+{digits}"
        
        # 11 digits not starting with 1 - ambiguous
        # Could be missing country code or have short country code
        # Default: assume it has country code
        if len(digits) >= 11:
            return f"+{digits}"
        
        # Too short (< 10 digits), return original
        return phone

    def _extract_phone(self, contact: Dict[str, Any]) -> str:
        """Extract phone number from contact data and normalize to E.164."""
        # Check the nested phone.number structure first (BotPenguin v7 format)
        phone_obj = (
            contact.get("profile", {})
            .get("userDetails", {})
            .get("contact", {})
            .get("phone", {})
        )
        if isinstance(phone_obj, dict):
            number = phone_obj.get("number", "").strip()
            if number:
                # Optionally prepend prefix if available
                prefix = phone_obj.get("prefix", "").strip()
                if prefix and not number.startswith("+"):
                    combined = f"{prefix}{number}"
                else:
                    combined = number
                # Normalize to E.164 format
                return self._normalize_phone_e164(combined)
        
        # Check common direct paths as fallback
        paths = [
            ["phone"],
            ["phoneNumber"],
            ["phone_number"],
            ["mobile"],
            ["profile", "phone"],
            ["profile", "phoneNumber"],
            ["profile", "userDetails", "contact", "phone"],
            ["profile", "userDetails", "contact", "phoneNumber"],
        ]
        for p in paths:
            cur: Any = contact
            ok = True
            for k in p:
                if not isinstance(cur, dict) or k not in cur:
                    ok = False
                    break
                cur = cur[k]
            if ok and isinstance(cur, str) and cur.strip():
                return cur.strip()
        
        # Check attributes list for phone-related keys
        attrs = (
            contact.get("profile", {})
            .get("userDetails", {})
            .get("attributes", [])
        )
        if isinstance(attrs, list):
            phone_keys = ("phone", "Phone", "phoneNumber", "phone_number", "mobile", "Mobile", "tel", "Tel")
            for a in attrs:
                if isinstance(a, dict) and a.get("key") in phone_keys:
                    v = a.get("value")
                    if isinstance(v, str) and v.strip():
                        return v.strip()
        return ""

    def find_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Page through inbox users and return the first contact whose email matches."""
        url = self._url(self.list_path)
        email_l = email.lower().strip()
        try:
            for page in range(1, 51):  # generous cap
                body = dict(self._base_body)
                body["page"] = page
                r = requests.post(url, headers=self._headers(), json=body, timeout=30)
                if r.status_code != 200:
                    log.error(
                        "BotPenguin list failed: status=%s body=%s",
                        r.status_code,
                        r.text[:500],
                    )
                    return None
                data = r.json() if r.content else {}
                # Extract list of contacts from flexible shapes
                contacts = None
                if isinstance(data, dict):
                    if isinstance(data.get("data"), list):
                        contacts = data["data"]
                    elif isinstance(data.get("users"), list):
                        contacts = data["users"]
                    elif isinstance(data.get("contacts"), list):
                        contacts = data["contacts"]
                    else:
                        for v in data.values():
                            if isinstance(v, list):
                                contacts = v
                                break
                elif isinstance(data, list):
                    contacts = data

                if contacts is None:
                    log.warning("BotPenguin: unknown list format on page %s", page)
                    return None
                if not contacts:
                    # No more data
                    return None

                for c in contacts:
                    cand = self._extract_email(c).lower()
                    if cand and cand == email_l:
                        return c

                # Check pagination meta to break early if available
                if isinstance(data, dict):
                    meta = data.get("meta") or data.get("pagination") or {}
                    total_pages = (
                        meta.get("totalPages")
                        or meta.get("pages")
                        or meta.get("total_pages")
                    )
                    if isinstance(total_pages, int) and page >= total_pages:
                        break
            return None
        except Exception as e:
            log.warning("BotPenguin search failed: %s", e)
            return None

    def update_contact_attributes(self, contact_id: str, attrs: Dict[str, Any]) -> bool:
        """Update attributes with workspace‑compatible strategy.

        Tries the following in order:
          1) PUT to configured path with attributes array payload
          2) If not 2xx, PUT to configured path with flat map payload
          3) If path includes '/attributes' and fails, retry on '/inbox/users/{id}'
        """
        base_headers = self._headers()

        def attrs_array_payload() -> Dict[str, Any]:
            return {
                "attributes": [
                    {"key": str(k), "value": str(v) if v is not None else ""}
                    for k, v in attrs.items()
                ]
            }

        def flat_payload() -> Dict[str, Any]:
            return {k: ("" if v is None else v) for k, v in attrs.items()}

        tried = []
        # 1) PUT to configured path
        path = self.update_path.replace("{contact_id}", contact_id)
        url = self._url(path)
        for payload in (attrs_array_payload(), flat_payload()):
            try:
                r = requests.put(url, headers=base_headers, json=payload, timeout=20)
                tried.append((url, r.status_code, r.text[:300]))
                if 200 <= r.status_code < 300:
                    return True
            except Exception as e:
                tried.append((url, "EXC", str(e)))

        # 2) If configured path used '/attributes', try updating the user resource directly
        if "/attributes" in path:
            alt_path = path.replace("/attributes", "")
            alt_url = self._url(alt_path)
            for payload in (attrs_array_payload(), flat_payload()):
                try:
                    r = requests.put(alt_url, headers=base_headers, json=payload, timeout=20)
                    tried.append((alt_url, r.status_code, r.text[:300]))
                    if 200 <= r.status_code < 300:
                        return True
                except Exception as e:
                    tried.append((alt_url, "EXC", str(e)))

        # Log attempts for debugging
        for u, s, b in tried:
            log.warning("BotPenguin update attempt: url=%s status=%s body=%s", u, s, b)
        return False


def get_phone_from_botpenguin(visitor_email: str) -> Optional[str]:
    """Retrieve phone number from BotPenguin contact by email."""
    try:
        client = BotPenguinClient()
    except Exception as e:
        log.debug("BotPenguin not configured: %s", e)
        return None

    contact = client.find_contact_by_email(visitor_email)
    if not contact:
        log.debug("BotPenguin: no contact found for %s", visitor_email)
        return None

    phone = client._extract_phone(contact)
    if phone:
        log.info("BotPenguin: retrieved phone for %s", visitor_email)
        return phone
    
    log.debug("BotPenguin: no phone found for %s", visitor_email)
    return None


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

    contact_id = str(contact.get("_id") or contact.get("id") or contact.get("uuid") or "").strip()
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

