import os
import logging
from typing import Any, Dict, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


log = logging.getLogger(__name__)


class FluentCRMClient:
    """Minimal FluentCRM REST API client for upserting contacts and managing lists.

    Env vars:
      - FLUENTCRM_BASE_URL (required): e.g., https://example.com
      - FLUENTCRM_API_TOKEN (optional): Bearer token header
      - FLUENTCRM_BASIC_USER (optional): Basic auth username (e.g., WP user)
      - FLUENTCRM_BASIC_PASS (optional): Basic auth password or Application Password
      - FLUENTCRM_LIST_NAME (optional): default list name to assign; default: WEBSITE 1 TO 1 SESSIONS
      - FLUENTCRM_LIST_ID (optional): if set, use this numeric list id directly
    """

    def __init__(self) -> None:
        if requests is None:
            raise RuntimeError("The 'requests' package is required for FluentCRM integration")
        self.base_url = (os.getenv("FLUENTCRM_BASE_URL", "").strip().rstrip("/"))
        if not self.base_url:
            raise RuntimeError("FLUENTCRM_BASE_URL not configured")
        self.api_token = os.getenv("FLUENTCRM_API_TOKEN", "").strip()
        self.basic_user = os.getenv("FLUENTCRM_BASIC_USER", "").strip()
        self.basic_pass = os.getenv("FLUENTCRM_BASIC_PASS", "").strip()
        self.default_list_name = os.getenv("FLUENTCRM_LIST_NAME", "WEBSITE 1 TO 1 SESSIONS").strip() or "WEBSITE 1 TO 1 SESSIONS"
        try:
            self.default_list_id = int(os.getenv("FLUENTCRM_LIST_ID", "").strip()) if os.getenv("FLUENTCRM_LIST_ID") else None
        except Exception:
            self.default_list_id = None
        try:
            auth_mode = "Bearer" if self.api_token else ("Basic" if (self.basic_user and self.basic_pass) else "None")
            list_info = f"id={self.default_list_id}" if self.default_list_id else f"name='{self.default_list_name}'"
            log.info("FluentCRM client configured: base_url=%s, auth_mode=%s, list=%s", self.base_url, auth_mode, list_info)
        except Exception:
            pass

    def _headers(self) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            h["Authorization"] = f"Bearer {self.api_token}"
        return h

    def _auth(self) -> Optional[Tuple[str, str]]:
        if self.basic_user and self.basic_pass:
            return (self.basic_user, self.basic_pass)
        return None

    def _url(self, path: str) -> str:
        # All endpoints under /wp-json/fluent-crm/v2
        if not path.startswith("/wp-json"):
            path = "/wp-json/fluent-crm/v2" + (path if path.startswith("/") else ("/" + path))
        return f"{self.base_url}{path}"

    # --- Helpers for contact/subscriber retrieval & membership checks ---
    def _get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        # Try fetching with embedded lists first (where supported), then fall back.
        try:
            r = requests.get(self._url(f"/contacts/{contact_id}?with=lists"), headers=self._headers(), auth=self._auth(), timeout=15)
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    return js.get("data") or js.get("contact") or js
                return js
        except Exception:
            pass
        try:
            r = requests.get(self._url(f"/contacts/{contact_id}"), headers=self._headers(), auth=self._auth(), timeout=15)
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    return js.get("data") or js.get("contact") or js
                return js
        except Exception:
            pass
        try:
            r = requests.get(self._url(f"/subscribers/{contact_id}?with=lists"), headers=self._headers(), auth=self._auth(), timeout=15)
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    return js.get("data") or js.get("subscriber") or js
                return js
        except Exception:
            pass
        try:
            r = requests.get(self._url(f"/subscribers/{contact_id}"), headers=self._headers(), auth=self._auth(), timeout=15)
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    return js.get("data") or js.get("subscriber") or js
                return js
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_list_ids(obj: Dict[str, Any]) -> set[int]:
        ids: set[int] = set()
        try:
            # Common shapes: lists: [ {id:..}, ... ] or list_ids: [..]
            if isinstance(obj.get("list_ids"), list):
                for i in obj["list_ids"]:
                    try:
                        ids.add(int(i))
                    except Exception:
                        pass
            if isinstance(obj.get("lists"), list):
                for it in obj["lists"]:
                    try:
                        if isinstance(it, dict) and it.get("id") is not None:
                            ids.add(int(it["id"]))
                    except Exception:
                        pass
            # Nested under data/contact/subscriber
            for k in ("data", "contact", "subscriber"):
                v = obj.get(k)
                if isinstance(v, dict):
                    ids |= FluentCRMClient._extract_list_ids(v)
        except Exception:
            pass
        return ids

    # Lists
    def get_lists(self) -> list[Dict[str, Any]]:
        try:
            r = requests.get(self._url("/lists"), headers=self._headers(), auth=self._auth(), timeout=20)
            if r.status_code == 200:
                js = r.json() or {}
                # Accept several response shapes: {data: []}, {lists: []}, or []
                if isinstance(js, dict):
                    if isinstance(js.get("data"), list):
                        return js["data"]
                    if isinstance(js.get("lists"), list):
                        return js["lists"]
                if isinstance(js, list):
                    return js
            else:
                log.info("FluentCRM get_lists failed: %s %s", r.status_code, (r.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM get_lists error: %s", e)
        return []

    def ensure_list(self, name: str) -> Optional[int]:
        # Try to find by name/case-insensitive. If multiple matches exist (duplicate titles),
        # prefer the highest numeric id (most recently created).
        try:
            matches: list[int] = []
            for it in self.get_lists():
                title = str(it.get("title") or it.get("name") or "").strip()
                if title and title.lower() == (name or "").strip().lower():
                    try:
                        matches.append(int(it.get("id")))
                    except Exception:
                        pass
            if matches:
                return max(matches)
        except Exception:
            pass
        # Create if missing
        try:
            r = requests.post(
                self._url("/lists"),
                headers=self._headers(),
                auth=self._auth(),
                json={"title": name},
                timeout=20,
            )
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    # Accept {data:{id:..}}, {lists:{id:..}}, or {item:{id:..}}
                    for k in ("data", "lists", "item"):
                        data = js.get(k)
                        if isinstance(data, dict) and data.get("id") is not None:
                            try:
                                return int(data.get("id"))
                            except Exception:
                                pass
                log.info("FluentCRM create list parse issue: %s", (r.text or "")[:300])
            else:
                log.info("FluentCRM create list failed: %s %s", r.status_code, (r.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM ensure_list error: %s", e)
        return None

    # Contacts
    def find_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a contact/subscriber by exact email across multiple endpoints/shapes.

        Some installations ignore the `email` param for index endpoints or return
        loosely filtered results. This method enforces exact-email matching by
        scanning candidate lists from several endpoints and response shapes.
        """
        target = (email or "").strip().lower()
        if not target:
            return None

        def candidates_from_json(js: Any) -> list[Dict[str, Any]]:
            out: list[Dict[str, Any]] = []
            try:
                if isinstance(js, dict):
                    # Common keys at top-level
                    for key in ("data", "contacts", "subscribers", "items", "list", "results"):
                        v = js.get(key)
                        if isinstance(v, list):
                            out.extend([x for x in v if isinstance(x, dict)])
                        elif isinstance(v, dict):
                            inner = v.get("data") or v.get("items") or v.get("subscribers") or v.get("contacts")
                            if isinstance(inner, list):
                                out.extend([x for x in inner if isinstance(x, dict)])
                    # Also scan any list-valued fields
                    for v in js.values():
                        if isinstance(v, list):
                            out.extend([x for x in v if isinstance(x, dict)])
                        elif isinstance(v, dict):
                            inner = v.get("data") or v.get("items") or v.get("subscribers") or v.get("contacts")
                            if isinstance(inner, list):
                                out.extend([x for x in inner if isinstance(x, dict)])
                elif isinstance(js, list):
                    out.extend([x for x in js if isinstance(x, dict)])
            except Exception:
                pass
            return out

        def extract_email(obj: Dict[str, Any]) -> str:
            try:
                e = str(obj.get("email") or obj.get("user_email") or "").strip().lower()
                if e:
                    return e
                for k in ("data", "contact", "subscriber"):
                    v = obj.get(k)
                    if isinstance(v, dict):
                        ee = str(v.get("email") or v.get("user_email") or "").strip().lower()
                        if ee:
                            return ee
            except Exception:
                pass
            return ""

        # Try multiple endpoints and parameter styles; require exact email match
        attempts: list[tuple[str, Dict[str, Any]]] = [
            ("/contacts", {"email": email}),
            ("/subscribers", {"email": email}),
            ("/subscribers/search-contacts", {"search": email}),
            ("/contacts", {"search": email}),
            ("/subscribers", {"search": email}),
        ]
        for idx, (path, params) in enumerate(attempts, start=1):
            try:
                r = requests.get(self._url(path), headers=self._headers(), auth=self._auth(), params=params, timeout=20)
                if 200 <= r.status_code < 300:
                    js = r.json() or {}
                    cands = candidates_from_json(js)
                    for cand in cands:
                        if extract_email(cand) == target:
                            return cand
                else:
                    log.info("FluentCRM find contact attempt %s failed: %s %s", idx, r.status_code, (r.text or "")[:300])
            except Exception:
                # Swallow and try next strategy
                pass
        return None

    def create_contact(self, email: str, first_name: str = "", last_name: str = "", status: str = "subscribed", list_ids: Optional[list[int]] = None) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {"email": email, "status": status}
        if first_name:
            payload["first_name"] = first_name
        if last_name:
            payload["last_name"] = last_name
        if list_ids:
            payload["lists"] = list_ids
        try:
            # Try /contacts first
            r = requests.post(self._url("/contacts"), headers=self._headers(), auth=self._auth(), json=payload, timeout=20)
            if 200 <= r.status_code < 300:
                js = r.json() or {}
                if isinstance(js, dict):
                    return js.get("data") or js.get("contact") or js
                return js
            # If route missing, try subscribers
            if r.status_code == 404:
                r2 = requests.post(self._url("/subscribers"), headers=self._headers(), auth=self._auth(), json=payload, timeout=20)
                if 200 <= r2.status_code < 300:
                    js2 = r2.json() or {}
                    if isinstance(js2, dict):
                        return js2.get("data") or js2.get("subscriber") or js2
                    return js2
                log.info("FluentCRM create subscriber failed: %s %s", r2.status_code, (r2.text or "")[:300])
            else:
                log.info("FluentCRM create contact failed: %s %s", r.status_code, (r.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM create error: %s", e)
        return None

    def update_contact(self, contact_id: int, data: Dict[str, Any]) -> bool:
        try:
            r = requests.put(self._url(f"/contacts/{contact_id}"), headers=self._headers(), auth=self._auth(), json=data, timeout=20)
            if 200 <= r.status_code < 300:
                return True
            if r.status_code == 404:
                r2 = requests.put(self._url(f"/subscribers/{contact_id}"), headers=self._headers(), auth=self._auth(), json=data, timeout=20)
                return 200 <= r2.status_code < 300
            log.info("FluentCRM update contact failed: %s %s", r.status_code, (r.text or "")[:300])
            return False
        except Exception as e:
            log.info("FluentCRM update error: %s", e)
            return False

    def _verify_list_membership(self, contact_id: int, target_ids: list[int]) -> bool:
        """Check if contact currently has any of the target list IDs."""
        try:
            obj = self._get_contact(contact_id) or {}
            current = self._extract_list_ids(obj or {})
            target_set = set(int(x) for x in (target_ids or []))
            return bool(target_set & current)
        except Exception:
            return False

    def _get_contact_email(self, contact_id: int) -> Optional[str]:
        """Best-effort extraction of contact email from various response shapes."""
        try:
            obj = self._get_contact(contact_id) or {}
            if isinstance(obj, dict):
                email = str(obj.get("email") or obj.get("user_email") or "").strip()
                if email:
                    return email
                for k in ("data", "contact", "subscriber"):
                    v = obj.get(k)
                    if isinstance(v, dict):
                        e2 = str(v.get("email") or v.get("user_email") or "").strip()
                        if e2:
                            return e2
        except Exception:
            pass
        return None
    def _update_lists_variants(self, contact_id: int, list_ids: list[int]) -> bool:
        """Try multiple payload shapes against contacts/subscribers update endpoints to attach lists."""
        target_set = set(int(x) for x in list_ids or [])
        payloads: list[Dict[str, Any]] = [
            {"lists": list_ids},
            {"list_ids": list_ids},
            {"lists_map": {"attach": list_ids, "detach": []}},
            # Some installs expect object form with id keys
            {"lists": [{"id": int(x)} for x in (list_ids or [])]},
            {"list_ids": [{"id": int(x)} for x in (list_ids or [])]},
        ]
        for data in payloads:
            try:
                r = requests.put(
                    self._url(f"/contacts/{contact_id}"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=data,
                    timeout=20,
                )
                if 200 <= r.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if target_set & current:
                        return True
            except Exception:
                pass
            try:
                r2 = requests.put(
                    self._url(f"/subscribers/{contact_id}"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=data,
                    timeout=20,
                )
                if 200 <= r2.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if target_set & current:
                        return True
            except Exception:
                pass
        return False

    def add_contact_to_lists(self, contact_id: int, list_ids: list[int]) -> bool:
        target_set = set(int(x) for x in list_ids or [])
        # 1) Try robust update variants for lists
        try:
            if self._update_lists_variants(contact_id, list_ids):
                return True
        except Exception:
            pass

        # 2) Try explicit attach endpoints
        try:
            payloads = [
                {"lists": list_ids},
                {"list_ids": list_ids},
                {"lists_map": {"attach": list_ids, "detach": []}},
                {"lists": [{"id": int(x)} for x in (list_ids or [])]},
                {"list_ids": [{"id": int(x)} for x in (list_ids or [])]},
            ]
            r = None
            for data in payloads:
                r = requests.post(
                    self._url(f"/contacts/{contact_id}/lists"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=data,
                    timeout=20,
                )
                if 200 <= r.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if target_set & current:
                        return True
            if r is not None and r.status_code != 404:
                log.info("FluentCRM attach lists failed: %s %s", r.status_code, (r.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM attach error: %s", e)

        try:
            payloads = [
                {"lists": list_ids},
                {"list_ids": list_ids},
                {"lists_map": {"attach": list_ids, "detach": []}},
                {"lists": [{"id": int(x)} for x in (list_ids or [])]},
                {"list_ids": [{"id": int(x)} for x in (list_ids or [])]},
            ]
            r2 = None
            for data in payloads:
                r2 = requests.post(
                    self._url(f"/subscribers/{contact_id}/lists"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=data,
                    timeout=20,
                )
                if 200 <= r2.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if target_set & current:
                        return True
            if r2 is not None:
                log.info("FluentCRM attach lists (subscribers) failed: %s %s", r2.status_code, (r2.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM attach (subscribers) error: %s", e)

        # 3) Try subscribers/do-bulk-action with selected payloads; require verification
        try:
            payloads = [
                {"type": "selected", "action": "add_lists", "selected_ids": [contact_id], "lists": list_ids},
                {"type": "selected", "action": "add_lists", "selected_ids": [contact_id], "list_ids": list_ids},
                {"type": "selected", "action": "attach_lists", "selected_ids": [contact_id], "lists": list_ids},
                {"type": "selected", "action": "attach_lists", "selected_ids": [contact_id], "list_ids": list_ids},
                {"type": "selected", "action": "sync_segments", "selected_ids": [contact_id], "lists": list_ids, "tags": [], "remove_lists": [], "remove_tags": []},
                # Fallback variants without "type"
                {"action": "add_lists", "subscribers": [contact_id], "lists": list_ids},
                {"action": "add_lists", "subscribers": [contact_id], "list_ids": list_ids},
            ]
            rda = None
            for data in payloads:
                rda = requests.post(
                    self._url("/subscribers/do-bulk-action"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=data,
                    timeout=25,
                )
                if 200 <= rda.status_code < 300 and self._verify_list_membership(contact_id, list_ids):
                    return True
            if rda is not None:
                log.info("FluentCRM do-bulk-action did not verify attach: %s %s", rda.status_code, (rda.text or "")[:300])
        except Exception as e:
            log.info("FluentCRM do-bulk-action error: %s", e)

        # 4) Try attaching via list-centric endpoints
        for lid in list_ids or []:
            try:
                # POST /lists/{lid}/subscribers { subscribers: [contact_id] }
                r3 = requests.post(
                    self._url(f"/lists/{lid}/subscribers"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json={"subscribers": [contact_id]},
                    timeout=20,
                )
                if 200 <= r3.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if int(lid) in current:
                        return True
                else:
                    log.info("FluentCRM lists/%s/subscribers failed: %s %s", lid, r3.status_code, (r3.text or "")[:300])
            except Exception as e:
                log.info("FluentCRM list attach error (lists/%s/subscribers): %s", lid, e)

            try:
                # POST /lists/attach { list_id: lid, subscribers: [contact_id] } (guess)
                r4 = requests.post(
                    self._url(f"/lists/attach"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json={"list_id": lid, "subscribers": [contact_id]},
                    timeout=20,
                )
                if 200 <= r4.status_code < 300:
                    obj = self._get_contact(contact_id) or {}
                    current = self._extract_list_ids(obj or {})
                    if int(lid) in current:
                        return True
                else:
                    log.info("FluentCRM lists/attach failed: %s %s", r4.status_code, (r4.text or "")[:300])
            except Exception as e:
                log.info("FluentCRM list attach error (lists/attach): %s", e)

        # 4) Try subscribers/sync-segments bulk API with multiple payload variants; require verification
        try:
            payloads = [
                {
                    "subscribers": [contact_id],
                    "lists": list_ids,
                    "tags": [],
                    "remove_lists": [],
                    "remove_tags": [],
                },
                {
                    "subscribers": [contact_id],
                    "list_ids": list_ids,
                    "tags": [],
                    "remove_lists": [],
                    "remove_tags": [],
                },
                {
                    "subscribers": [contact_id],
                    "lists_map": {"attach": list_ids, "detach": []},
                    "tags": [],
                    "remove_lists": [],
                    "remove_tags": [],
                },
            ]
            for payload in payloads:
                r5 = requests.post(
                    self._url("/subscribers/sync-segments"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=payload,
                    timeout=20,
                )
                if 200 <= r5.status_code < 300 and self._verify_list_membership(contact_id, list_ids):
                    return True
            # If none succeeded with verification, log last response if present
            try:
                log.info("FluentCRM sync-segments did not verify attach; last resp: %s", (r5.text or "")[:300])  # type: ignore[name-defined]
            except Exception:
                pass
        except Exception as e:
            log.info("FluentCRM sync-segments error: %s", e)

        # 5) Try bulk-add-update with id/email forms; require verification
        try:
            email = self._get_contact_email(contact_id) or ""
            ba_payloads = [
                {"subscribers": [{"id": contact_id, "lists": list_ids}]},
                {"subscribers": [{"email": email, "lists": list_ids, "status": "subscribed"}]} if email else None,
                {"subscribers": [{"email": email, "list_ids": list_ids, "status": "subscribed"}]} if email else None,
            ]
            for p in [pp for pp in ba_payloads if pp]:
                r6 = requests.post(
                    self._url("/subscribers/bulk-add-update"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=p,
                    timeout=25,
                )
                if 200 <= r6.status_code < 300 and self._verify_list_membership(contact_id, list_ids):
                    return True
        except Exception as e:
            log.info("FluentCRM bulk-add-update error: %s", e)

        # 6) Try subscribers-property to attach lists; require verification
        try:
            sp_payloads = [
                {"subscriber_ids": [contact_id], "column": "lists", "value": list_ids, "action": "add"},
                {"subscriber_ids": [contact_id], "column": "lists", "value": list_ids, "operator": "attach"},
            ]
            for p in sp_payloads:
                r7 = requests.put(
                    self._url("/subscribers/subscribers-property"),
                    headers=self._headers(),
                    auth=self._auth(),
                    json=p,
                    timeout=20,
                )
                if 200 <= r7.status_code < 300 and self._verify_list_membership(contact_id, list_ids):
                    return True
        except Exception as e:
            log.info("FluentCRM subscribers-property error: %s", e)

        # Final verification log
        obj = self._get_contact(contact_id) or {}
        current = self._extract_list_ids(obj or {})
        log.info("FluentCRM: attach verification lists now=%s (wanted=%s) for contact_id=%s", sorted(current), list_ids, contact_id)
        return False


def sync_contact_to_fluentcrm(email: str, full_name: str | None) -> None:
    """Upsert contact in FluentCRM, add to the default list and set status to subscribed.

    Best-effort: logs issues and returns without raising.
    """
    try:
        client = FluentCRMClient()
    except Exception as e:
        log.info("FluentCRM not configured: %s", e)
        return

    # Resolve name parts
    first, last = "", ""
    if full_name:
        parts = [p for p in str(full_name).split(" ") if p]
        if parts:
            first = parts[0]
            last = " ".join(parts[1:]) if len(parts) > 1 else ""

    log.info("FluentCRM: syncing contact email=%s", email)
    # Determine target list(s)
    # Resolve target list id robustly: verify configured id exists; if not, ensure by name.
    target_id = None
    if getattr(client, "default_list_id", None):
        try:
            available = {int(it.get("id")) for it in (client.get_lists() or []) if it.get("id") is not None}
        except Exception:
            available = set()
        try:
            configured_id = int(client.default_list_id)  # type: ignore[arg-type]
        except Exception:
            configured_id = None  # type: ignore[assignment]
        if configured_id and configured_id in available:
            target_id = configured_id
            log.info("FluentCRM: using configured list id=%s", configured_id)
        else:
            target_id = client.ensure_list(client.default_list_name)
            if target_id:
                log.info("FluentCRM: configured list id=%s not found; ensured '%s' id=%s", client.default_list_id, client.default_list_name, target_id)
    else:
        target_id = client.ensure_list(client.default_list_name)
        if target_id:
            log.info("FluentCRM: ensured list '%s' id=%s", client.default_list_name, target_id)
        else:
            log.info("FluentCRM: default list '%s' not ensured; proceeding without list", client.default_list_name)
    list_ids = [target_id] if target_id else []

    # Upsert contact
    contact = client.find_contact_by_email(email)
    if not contact:
        contact = client.create_contact(email=email, first_name=first, last_name=last, status="subscribed", list_ids=list_ids)
        if not contact:
            # If create failed (e.g., 422 unique), try to fetch again before giving up
            contact = client.find_contact_by_email(email)
            if not contact:
                log.info("FluentCRM: failed to create contact for %s", email)
                return
        else:
            log.info("FluentCRM: created contact for %s", email)
    # Update status and lists
    try:
        cid = int(contact.get("id") or contact.get("ID") or contact.get("contact_id") or 0)
    except Exception:
        cid = 0
    if not cid:
        log.info("FluentCRM: contact id missing for %s", email)
        return
    # Ensure subscribed status and list membership
    if client.update_contact(cid, {"status": "subscribed"}):
        log.info("FluentCRM: set status=subscribed for contact_id=%s", cid)
    if list_ids:
        if client.add_contact_to_lists(cid, list_ids):
            log.info("FluentCRM: attached lists %s to contact_id=%s", list_ids, cid)
