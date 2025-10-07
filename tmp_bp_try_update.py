import os, requests
from dotenv import load_dotenv
load_dotenv()
base = os.getenv('BOTPENGUIN_BASE_URL','https://api.v7.botpenguin.com').rstrip('/')
key = os.getenv('BOTPENGUIN_API_KEY','').strip()
headers = {'AuthType':'Key','Authorization': f'Bearer {key}', 'Content-Type':'application/json'}
id = '68e38aa565bb65210fc74df6'
for path in [f'/inbox/users/{id}/attributes', f'/inbox/users/{id}', f'/customer/{id}', f'/customers/{id}']:
  for method in ['PUT','PATCH','POST']:
    url = base + path
    payloads = []
    if 'attributes' in path:
      payloads.append({'attributes':[{'key':'booking_time','value':'2025-10-07T12:00:00+05:30'},{'key':'demo_session_coach','value':'Coach Test'}]})
    else:
      payloads.append({'booking_time':'2025-10-07T12:00:00+05:30','demo_session_coach':'Coach Test'})
      payloads.append({'attributes':[{'key':'booking_time','value':'2025-10-07T12:00:00+05:30'},{'key':'demo_session_coach','value':'Coach Test'}]})
    for payload in payloads:
      try:
        if method=='PUT':
          r = requests.put(url, headers=headers, json=payload, timeout=15)
        elif method=='PATCH':
          r = requests.patch(url, headers=headers, json=payload, timeout=15)
        else:
          r = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"{method} {path} -> {r.status_code}")
        print(r.text[:200])
      except Exception as e:
        print(f"{method} {path} -> exception {e}")
