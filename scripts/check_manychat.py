from pathlib import Path
import sys
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    # Ensure project root importable
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    try:
        from app.integrations.manychat_service import ManyChatClient
        import requests
    except Exception as e:
        print("Import error:", type(e).__name__, e)
        return 2

    try:
        client = ManyChatClient()
    except Exception as e:
        print("Config error:", e)
        return 3

    # Simple connectivity check: get custom fields
    try:
        url = client._url('/fb/page/getInfo')
        r = requests.get(url, headers=client._headers(), timeout=15)
        print(f"GET {url} -> {r.status_code}")
        if r.status_code == 200:
            print("OK: API key accepted.")
            return 0
        else:
            print((r.text or '')[:300])
            return 1
    except Exception as e:
        print("Request error:", type(e).__name__, e)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
