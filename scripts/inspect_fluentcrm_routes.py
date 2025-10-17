from pathlib import Path
import sys, json
from dotenv import load_dotenv

def main():
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import os, requests
    base = os.getenv('FLUENTCRM_BASE_URL','').rstrip('/')
    auth = None
    user = os.getenv('FLUENTCRM_BASIC_USER','').strip()
    pwd = os.getenv('FLUENTCRM_BASIC_PASS','').strip()
    if user and pwd:
        auth=(user,pwd)
    url = base + '/wp-json'
    r = requests.get(url, timeout=20, auth=auth)
    print('GET', url, '->', r.status_code)
    data = r.json() if r.content else {}
    routes = data.get('routes', {})
    keys = [k for k in routes.keys() if 'fluent-crm' in k]
    print('FluentCRM routes count:', len(keys))
    for k in sorted(keys):
        print(k)
    # Show details for list-related endpoints
    for k in sorted(keys):
        if '/lists' in k or '/subscribers' in k or '/contacts' in k:
            print('---', k, '---')
            try:
                print(json.dumps(routes[k], indent=2)[:1200])
            except Exception:
                print(str(routes[k])[:1200])

    # Focused endpoints for precise payload/method expectations
    focus = [
        '/fluent-crm/v2/lists/(?P<id>[0-9]+)/subscribers',
        '/fluent-crm/v2/contacts/(?P<id>[0-9]+)/lists',
        '/fluent-crm/v2/subscribers/(?P<id>[0-9]+)/lists',
        '/fluent-crm/v2/subscribers/sync-segments',
        '/fluent-crm/v2/subscribers/do-bulk-action',
    ]
    print('=== Focused endpoints ===')
    for k in focus:
        if k in routes:
            print('---', k, '---')
            try:
                print(json.dumps(routes[k], indent=2))
            except Exception:
                print(str(routes[k]))

    # Heuristic search for any lists attach endpoints under subscribers/contacts
    print('=== Heuristic: subscribers/*lists* and contacts/*lists* ===')
    for k in sorted(routes.keys()):
        if 'fluent-crm' in k and 'subscribers' in k and 'lists' in k:
            print('---', k, '---')
            try:
                print(json.dumps(routes[k], indent=2)[:1200])
            except Exception:
                print(str(routes[k])[:1200])
    for k in sorted(routes.keys()):
        if 'fluent-crm' in k and 'contacts' in k and 'lists' in k:
            print('---', k, '---')
            try:
                print(json.dumps(routes[k], indent=2)[:1200])
            except Exception:
                print(str(routes[k])[:1200])

    return 0

if __name__ == '__main__':
    raise SystemExit(main())
