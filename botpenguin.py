# fetch_botpenguin_contacts.py
# Python 3.8+
# pip install requests

import requests
import json
import time

API_URL = "https://api.v7.botpenguin.com/inbox/users"

# IMPORTANT: Replace this with your EXACT token from Postman (without "Bearer ")
API_TOKEN = "VJrJBzCwXgRqLGRu8IeVZIk5OXXxDVXxWLxOkuwmscvPyuzz8coKmAoYRE5QJpcniBvKk4ccjEmPo6Ga6MlpCHFMnxf7ZjBzueheooI1KcYhXLb8xilkelel5eRYpPcrf4VK53JAE3y0fDBp7k86TgAopUiIRjk8xUK2ABXwe96kZLUHERywwTNpmDctw2q7wa4sSbkuOOGzcplQQDINhUQhCTSrEaoyFmC2R_6862add8833c9f93263e210e_c"

# Default request body taken from BotPenguin docs; adjust filters as needed.
BASE_BODY = {
    "_agentAssigned": [],
    "_botAutomation": [],
    "_botFacebook": [],
    "_botTelegram": [],
    "_botWebsite": [],
    "_botWhatsapp": [],
    "applicableFilters": [],
    "createdAt": {
        "startAt": "",
        "endsAt": ""
    },
    "ctwaNewUsers": False,
    "ctwaOldUsers": False,
    "hasOrdered": {
        "status": False,
        "lastAt": ""
    },
    "isLiveChatActive": False,
    "isOnline": False,
    "isSubscriber": True,
    "lastMessageBy": [],
    "lastSeenAt": {
        "startAt": "",
        "endsAt": ""
    },
    "searchText": "",
    "segments": [],
    "status": [],
    "tags": [],
    "tagsV2": [],
    "userInteracted": False,
    "page": 1,
    "isExport": "none",
    "isContact": False
}

def fetch_all_contacts(max_pages=1000, sleep_between_requests=0.2):
    """
    Fetch all contacts by paging through the API.
    Returns a list of contacts (as returned by API).
    """
    # Debug: Print token info (first/last few chars only for security)
    if len(API_TOKEN) > 20:
        print(f"[DEBUG] Using token: {API_TOKEN[:10]}...{API_TOKEN[-10:]}")
        print(f"[DEBUG] Token length: {len(API_TOKEN)}")
    else:
        print("[ERROR] Token seems too short or not set!")
        return []
    
    # Try with AuthType: Key AND Bearer format
    HEADERS = {
        "AuthType": "Key",
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Debug: Print the exact headers being sent
    print(f"[DEBUG] Authorization header: Bearer {API_TOKEN[:20]}...")
    print(f"[DEBUG] AuthType: Key")
    
    all_contacts = []
    page = 1

    session = requests.Session()
    session.headers.update(HEADERS)

    while page <= max_pages:
        body = dict(BASE_BODY)
        body["page"] = page

        print(f"\n[INFO] Requesting page {page}...")
        
        try:
            resp = session.post(API_URL, json=body, timeout=30)
        except requests.RequestException as e:
            print(f"[ERROR] Request failed on page {page}: {e}")
            break

        print(f"[DEBUG] Response status code: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"[ERROR] Non-200 response on page {page}: {resp.status_code}")
            print(f"[DEBUG] Response headers: {dict(resp.headers)}")
            try:
                print(f"[DEBUG] Response body: {resp.text}")
            except Exception:
                pass
            
            # If it's an auth error, no point continuing
            if resp.status_code in [401, 403]:
                print("\n[ERROR] Authentication failed. Please check:")
                print("1. Your token is correct and not expired")
                print("2. The token doesn't have extra spaces or line breaks")
                print("3. You're using the exact token from Postman")
                break
            break

        try:
            data = resp.json()
        except ValueError:
            print("[ERROR] Response is not valid JSON. Raw response:")
            print(resp.text)
            break

        # The docs don't give an exact schema for the returned JSON body.
        page_items = None

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                page_items = data["data"]
            elif "users" in data and isinstance(data["users"], list):
                page_items = data["users"]
            elif "contacts" in data and isinstance(data["contacts"], list):
                page_items = data["contacts"]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        page_items = v
                        break
        elif isinstance(data, list):
            page_items = data

        if page_items is None:
            print(f"[WARN] Couldn't determine contacts list structure on page {page}.")
            print("[DEBUG] Response structure:")
            print(json.dumps(data, indent=2)[:500])  # Print first 500 chars
            with open("last_response.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("Full response saved to 'last_response.json'")
            break

        if not page_items:
            print(f"[INFO] No items returned on page {page}. Stopping.")
            break

        print(f"[INFO] Retrieved {len(page_items)} items from page {page}")
        all_contacts.extend(page_items)

        if isinstance(data, dict):
            meta = data.get("meta") or data.get("pagination") or {}
            total_pages = meta.get("totalPages") or meta.get("pages") or meta.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                print("[INFO] Reached last page according to meta info.")
                break

        page += 1
        time.sleep(sleep_between_requests)

    return all_contacts

def main():
    if API_TOKEN == "YOUR_TOKEN_HERE":
        print("Please set your API_TOKEN variable in the script before running.")
        return

    contacts = fetch_all_contacts()
    print(f"\n[DONE] Total contacts fetched: {len(contacts)}")

    if contacts:
        with open("all_contacts.json", "w", encoding="utf-8") as f:
            json.dump(contacts, f, indent=2, ensure_ascii=False)
        print("Saved contacts to all_contacts.json")
    else:
        print("No contacts to save.")

if __name__ == "__main__":
    main()