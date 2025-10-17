import os
import sys
import json
import traceback
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    # Ensure repo root is importable when running from scripts/
    try:
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass
    load_dotenv()
    try:
        from app.integrations.fluentcrm_service import FluentCRMClient
    except Exception as e:
        print(f"Import error: {type(e).__name__}: {e}")
        return 2

    try:
        client = FluentCRMClient()
    except Exception as e:
        print(f"Config error: {e}")
        print("Required: FLUENTCRM_BASE_URL; Optional: FLUENTCRM_BASIC_USER/FLUENTCRM_BASIC_PASS or FLUENTCRM_API_TOKEN")
        return 3

    try:
        import requests
    except Exception as e:
        print("The 'requests' package is required. Install and retry.")
        print(f"Import error: {type(e).__name__}: {e}")
        return 4

    url = client._url('/lists')
    try:
        r = requests.get(url, headers=client._headers(), auth=client._auth(), timeout=15)
        print(f"GET {url} -> {r.status_code}")
        ct = r.headers.get('Content-Type', '')
        if 'application/json' in ct:
            try:
                js = r.json()
                # Print a compact summary
                if isinstance(js, dict) and 'data' in js:
                    data = js['data']
                else:
                    data = js
                if isinstance(data, list):
                    print(f"Lists returned: {len(data)}")
                else:
                    if isinstance(js, dict):
                        print("Response JSON keys:", list(js.keys()))
                    else:
                        print("Response type:", type(js).__name__)
            except Exception:
                print("JSON parse failed. Body (first 300 chars):")
                print((r.text or "")[:300])
        else:
            print("Non-JSON response. Body (first 300 chars):")
            print((r.text or "")[:300])
        # Return 0 for 2xx, 1 otherwise
        return 0 if 200 <= r.status_code < 300 else 1
    except Exception:
        traceback.print_exc()
        return 5


if __name__ == "__main__":
    sys.exit(main())
