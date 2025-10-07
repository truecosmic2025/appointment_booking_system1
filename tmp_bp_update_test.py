import os, requests, json
from dotenv import load_dotenv
load_dotenv()
base = os.getenv('BOTPENGUIN_BASE_URL','https://api.v7.botpenguin.com').rstrip('/')
headers = {'AuthType':'Key','Authorization': f"Bearer {os.getenv('BOTPENGUIN_API_KEY').strip()}", 'Content-Type':'application/json'}
id = '68e38aa565bb65210fc74df6'
url = f"{base}/inbox/users/{id}/attributes"
payload = {'attributes':[{'key':'booking_time','value':'2025-10-07T12:00:00+05:30'},{'key':'demo_session_coach','value':'Coach Test'}]}
print('URL:', url)
r = requests.put(url, headers=headers, json=payload, timeout=20)
print('status:', r.status_code)
print('body:', r.text[:500])
