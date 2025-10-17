from pathlib import Path
import sys
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from app.integrations.fluentcrm_service import FluentCRMClient

    email = sys.argv[1] if len(sys.argv) > 1 else "test@example.com"
    name = sys.argv[2] if len(sys.argv) > 2 else "Test User"
    first = name.split(" ")[0]
    last = " ".join(name.split(" ")[1:])

    c = FluentCRMClient()
    print("Configured base:", c.base_url)

    list_id = c.ensure_list(c.default_list_name)
    print("ensure_list ->", list_id)

    contact = c.find_contact_by_email(email)
    print("find_contact ->", bool(contact))

    if not contact:
        contact = c.create_contact(email=email, first_name=first, last_name=last, status="subscribed", list_ids=[list_id] if list_id else None)
        print("create_contact ->", bool(contact))
    if not contact:
        print("Contact create failed")
        return 1

    cid = int(contact.get("id") or contact.get("ID") or contact.get("contact_id") or 0)
    print("contact_id ->", cid)
    if not cid:
        return 2

    c.update_contact(cid, {"status": "subscribed"})
    if list_id:
        ok = c.add_contact_to_lists(cid, [list_id])
        print("attach lists ->", ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
