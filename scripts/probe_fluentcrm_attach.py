from pathlib import Path
import sys
import json
from typing import Any, Dict, Optional

from dotenv import load_dotenv


def _pp(label: str, resp) -> None:
    try:
        ct = resp.headers.get("Content-Type", "")
    except Exception:
        ct = ""
    body = ""
    try:
        if "json" in ct:
            body = json.dumps(resp.json(), indent=2)[:800]
        else:
            body = (resp.text or "")[:800]
    except Exception:
        try:
            body = (resp.text or "")[:800]
        except Exception:
            body = "<no body>"
    print(f"{label} -> {resp.status_code}")
    print(body)


def attempt_sync_segments(client, contact_id: int, list_ids: list[int]) -> bool:
    import requests
    ok = False
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
    for p in payloads:
        try:
            r = requests.post(
                client._url("/subscribers/sync-segments"),
                headers=client._headers(),
                auth=client._auth(),
                json=p,
                timeout=20,
            )
            _pp("POST /subscribers/sync-segments", r)
            if 200 <= r.status_code < 300:
                ok = True
        except Exception as e:
            print("sync-segments error:", e)
    return ok


def attempt_do_bulk_action(client, contact_id: int, list_id: int, action: str) -> bool:
    """
    Try generic bulk action endpoint with many payload variants:
    - action names: attach_lists, add_lists, add_to_lists, sync_segments
    - subscriber id keys: subscribers, subscriber_ids, selected_ids, ids
    - list id keys: lists, list_ids
    - selection type: optional {"type": "selected"}
    """
    import requests

    if action in ("attach_lists", "add_lists", "add_to_lists", "sync_segments"):
        actions = [action]
    else:
        actions = [action, "attach_lists", "add_lists", "add_to_lists", "sync_segments"]

    subscriber_keys = ["subscribers", "subscriber_ids", "selected_ids", "ids"]
    list_keys = ["lists", "list_ids"]
    types = [None, "selected"]

    ok = False
    for act in actions:
        for sk in subscriber_keys:
            for lk in list_keys:
                for t in types:
                    p = {"action": act, sk: [contact_id], lk: [list_id]}
                    if t:
                        p["type"] = t
                    if act == "sync_segments":
                        p.update({"tags": [], "remove_lists": [], "remove_tags": []})
                    try:
                        r = requests.post(
                            client._url("/subscribers/do-bulk-action"),
                            headers=client._headers(),
                            auth=client._auth(),
                            json=p,
                            timeout=20,
                        )
                        _pp(f"POST /subscribers/do-bulk-action {act} {sk} {lk} type={t}", r)
                        if 200 <= r.status_code < 300:
                            ok = True
                    except Exception as e:
                        print("do-bulk-action error:", e)
    return ok


def attempt_property_update(client, contact_id: int, list_ids: list[int]) -> bool:
    """
    PUT /subscribers/subscribers-property with explicit column/value for lists.
    """
    import requests
    payloads = [
        {"subscriber_ids": [contact_id], "column": "lists", "value": list_ids, "action": "add"},
        {"subscriber_ids": [contact_id], "column": "lists", "value": list_ids, "operator": "attach"},
        {"ids": [contact_id], "column": "lists", "value": list_ids, "action": "add"},
    ]
    ok = False
    for p in payloads:
        try:
            r = requests.put(
                client._url("/subscribers/subscribers-property"),
                headers=client._headers(),
                auth=client._auth(),
                json=p,
                timeout=20,
            )
            _pp("PUT /subscribers/subscribers-property", r)
            if 200 <= r.status_code < 300:
                ok = True
        except Exception as e:
            print("subscribers-property error:", e)
    return ok


def attempt_bulk_add_update(client, contact_id: int, email: str, list_ids: list[int]) -> bool:
    """
    POST /subscribers/bulk-add-update with id-based and email-based shapes.
    """
    import requests
    payloads = [
        {"subscribers": [{"id": contact_id, "lists": list_ids}]},
        {"subscribers": [{"email": email, "lists": list_ids, "status": "subscribed"}]},
        {"subscribers": [{"email": email, "list_ids": list_ids, "status": "subscribed"}]},
    ]
    ok = False
    for p in payloads:
        try:
            r = requests.post(
                client._url("/subscribers/bulk-add-update"),
                headers=client._headers(),
                auth=client._auth(),
                json=p,
                timeout=20,
            )
            _pp("POST /subscribers/bulk-add-update", r)
            if 200 <= r.status_code < 300:
                ok = True
        except Exception as e:
            print("bulk-add-update error:", e)
    return ok


def attempt_lists_attach_variants(client, contact_id: int, list_id: int) -> bool:
    """
    Try list-centric attach endpoints:
      - POST /lists/attach
      - POST /lists/attach-subscribers
      - POST /lists/{id}/attach-subscribers
      - POST /lists/{id}/attach_subscribers
    With payload subscriber key variants.
    """
    import requests
    ok = False
    endpoints = [
        "/lists/attach",
        "/lists/attach-subscribers",
        f"/lists/{list_id}/attach-subscribers",
        f"/lists/{list_id}/attach_subscribers",
    ]
    subscriber_keys = ["subscribers", "subscriber_ids", "ids"]

    for ep in endpoints:
        for sk in subscriber_keys:
            payload = {"list_id": list_id, sk: [contact_id]}
            try:
                r = requests.post(
                    client._url(ep),
                    headers=client._headers(),
                    auth=client._auth(),
                    json=payload,
                    timeout=20,
                )
                _pp(f"POST {ep} ({sk})", r)
                if 200 <= r.status_code < 300:
                    ok = True
            except Exception as e:
                print(f"{ep} error:", e)
    return ok


def verify_via_list_endpoint(client, contact_id: int, list_id: int) -> Optional[bool]:
    """
    If lists/{id}/subscribers exists, confirm membership by scanning subscribers.
    Returns True/False if endpoint is available; None if not available.
    """
    import requests
    url = client._url(f"/lists/{list_id}/subscribers")
    try:
        r = requests.get(url, headers=client._headers(), auth=client._auth(), timeout=20)
        print(f"GET /lists/{list_id}/subscribers -> {r.status_code}")
        if r.status_code == 404:
            return None
        if 200 <= r.status_code < 300:
            js = r.json() if r.content else {}
            # acceptable shapes: {data: {items: []}} or {data: []} or [] or {subscribers: []}
            items = []
            if isinstance(js, dict):
                if isinstance(js.get("data"), dict) and isinstance(js["data"].get("items"), list):
                    items = js["data"]["items"]
                elif isinstance(js.get("data"), list):
                    items = js["data"]
                elif isinstance(js.get("subscribers"), list):
                    items = js["subscribers"]
            elif isinstance(js, list):
                items = js
            # look for id matches
            for it in items:
                try:
                    sid = int(it.get("id") or it.get("ID") or it.get("subscriber_id") or it.get("contact_id") or 0)
                    if sid == contact_id:
                        return True
                except Exception:
                    pass
            return False
        return None
    except Exception as e:
        print("verify_via_list_endpoint error:", e)
        return None


def verify_via_contact(client, contact_id: int, target_lids: list[int]) -> bool:
    """
    Verify membership by requesting with 'with=lists' where supported, then fallback.
    """
    import requests
    lids: set[int] = set()
    paths = [
        f"/subscribers/{contact_id}?with=lists",
        f"/contacts/{contact_id}?with=lists",
        f"/subscribers/{contact_id}",
        f"/contacts/{contact_id}",
    ]
    for p in paths:
        try:
            r = requests.get(client._url(p), headers=client._headers(), auth=client._auth(), timeout=20)
            _pp(f"GET {p}", r)
            try:
                js = r.json() if r.content else {}
            except Exception:
                js = {}
            if isinstance(js, dict):
                lids |= client._extract_list_ids(js)
        except Exception:
            pass
    print("Contact lists detected:", sorted(lids))
    return any(int(x) in lids for x in target_lids or [])

def print_contact_debug(client, contact_id: int) -> None:
    """Dump raw contact/subscriber payloads including lists when available."""
    import requests
    paths = [
        f"/subscribers/{contact_id}?with=lists",
        f"/contacts/{contact_id}?with=lists",
        f"/subscribers/{contact_id}",
        f"/contacts/{contact_id}",
    ]
    for p in paths:
        try:
            r = requests.get(client._url(p), headers=client._headers(), auth=client._auth(), timeout=20)
            _pp(f"GET {p}", r)
        except Exception as e:
            print("debug fetch error:", e)


def main() -> int:
    # Ensure repo root import path and env
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.integrations.fluentcrm_service import FluentCRMClient

    email = sys.argv[1] if len(sys.argv) > 1 else "test@example.com"
    name = sys.argv[2] if len(sys.argv) > 2 else "Test User"
    first = name.split(" ")[0]
    last = " ".join(name.split(" ")[1:])

    c = FluentCRMClient()
    print("Base:", c.base_url)

    # resolve list id
    if getattr(c, "default_list_id", None):
        list_id = int(c.default_list_id)
        print("Using configured list id:", list_id)
    else:
        list_id = c.ensure_list(c.default_list_name) or 0
        print("Ensured list:", list_id)

    # find or create contact
    contact = c.find_contact_by_email(email)
    if not contact:
        contact = c.create_contact(email=email, first_name=first, last_name=last, status="subscribed", list_ids=[list_id] if list_id else None)
        print("Created contact:", bool(contact))
    if not contact:
        print("No contact; abort")
        return 1

    try:
        cid = int(contact.get("id") or contact.get("ID") or contact.get("contact_id") or 0)
    except Exception:
        cid = 0
    print("Contact id:", cid)
    if not cid:
        return 2

    # ensure status subscribed
    c.update_contact(cid, {"status": "subscribed"})

    ok = False

    # 1) sync-segments
    if list_id:
        ok = attempt_sync_segments(c, cid, [list_id])
        v = verify_via_list_endpoint(c, cid, list_id)
        if v is True:
            print("Verified via list endpoint after sync-segments: True")
            return 0
        elif v is False:
            print("List endpoint available but not attached after sync-segments")
        else:
            # fallback verification via contact if endpoint not available
            if verify_via_contact(c, cid, [list_id]):
                print("Verified via contact after sync-segments: True")
                return 0

    # 2) contacts/{id}/lists variants
    if list_id:
        ok_contacts = attempt_contacts_lists_variants(c, cid, list_id)
        v = verify_via_list_endpoint(c, cid, list_id)
        if v is True:
            print("Verified via list endpoint after contacts/{id}/lists: True")
            return 0
        elif v is None and verify_via_contact(c, cid, [list_id]):
            print("Verified via contact after contacts/{id}/lists: True")
            return 0
        ok = ok or ok_contacts

    # 3) do-bulk-action variants
    for action in ("attach_lists", "add_lists", "add_to_lists", "sync_segments"):
        if list_id:
            ok2 = attempt_do_bulk_action(c, cid, list_id, action)
            v = verify_via_list_endpoint(c, cid, list_id)
            if v is True:
                print(f"Verified via list endpoint after do-bulk-action:{action}: True")
                return 0
            elif v is False:
                print(f"List endpoint available but not attached after do-bulk-action:{action}")
            else:
                if verify_via_contact(c, cid, [list_id]):
                    print(f"Verified via contact after do-bulk-action:{action}: True")
                    return 0
            ok = ok or ok2

    # 3) subscribers-property bulk property update
    if list_id:
        ok3 = attempt_property_update(c, cid, [list_id])
        v = verify_via_list_endpoint(c, cid, list_id)
        if v is True:
            print("Verified via list endpoint after subscribers-property: True")
            return 0
        elif v is None and verify_via_contact(c, cid, [list_id]):
            print("Verified via contact after subscribers-property: True")
            return 0
        ok = ok or ok3

    # 4) bulk-add-update endpoint
    if list_id:
        ok4 = attempt_bulk_add_update(c, cid, email, [list_id])
        v = verify_via_list_endpoint(c, cid, list_id)
        if v is True:
            print("Verified via list endpoint after bulk-add-update: True")
            return 0
        elif v is None and verify_via_contact(c, cid, [list_id]):
            print("Verified via contact after bulk-add-update: True")
            return 0
        ok = ok or ok4

    print_contact_debug(c, cid)
    print("Final outcome: attached=", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())