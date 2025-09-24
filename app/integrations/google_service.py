import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def creds_from_json(creds_json: Optional[str]) -> Optional[Credentials]:
    if not creds_json:
        return None
    data = json.loads(creds_json)
    return Credentials.from_authorized_user_info(data, SCOPES)


def to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def list_freebusy(creds_json: str, start: datetime, end: datetime, calendar_id: str = 'primary') -> List[dict]:
    creds = creds_from_json(creds_json)
    if not creds:
        return []
    service = build('calendar', 'v3', credentials=creds)
    body = {
        "timeMin": to_rfc3339(start),
        "timeMax": to_rfc3339(end),
        "items": [{"id": calendar_id}],
    }
    resp = service.freebusy().query(body=body).execute()
    busy = resp.get('calendars', {}).get(calendar_id, {}).get('busy', [])
    return busy


def create_event_with_meet(
    creds_json: str,
    summary: str,
    start: datetime,
    end: datetime,
    attendees: List[dict],
    description: str = "",
    calendar_id: str = 'primary',
):
    creds = creds_from_json(creds_json)
    if not creds:
        raise RuntimeError("Google not connected")
    service = build('calendar', 'v3', credentials=creds)
    event = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': to_rfc3339(start)},
        'end': {'dateTime': to_rfc3339(end)},
        'attendees': attendees,
        'conferenceData': {
            'createRequest': {
                'requestId': f"req-{int(datetime.utcnow().timestamp())}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            }
        },
    }
    created = service.events().insert(
        calendarId=calendar_id,
        body=event,
        conferenceDataVersion=1,
        sendUpdates='all',
    ).execute()
    meet_link = None
    conf = created.get('conferenceData', {})
    for ep in conf.get('entryPoints', []) or []:
        if ep.get('entryPointType') == 'video':
            meet_link = ep.get('uri')
            break
    return created.get('id'), meet_link


def cancel_event(creds_json: str, event_id: str, calendar_id: str = 'primary'):
    creds = creds_from_json(creds_json)
    if not creds:
        return
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates='all').execute()
    except HttpError:
        pass


def reschedule_event(creds_json: str, event_id: str, start, end, calendar_id: str = 'primary'):
    creds = creds_from_json(creds_json)
    if not creds:
        return
    service = build('calendar', 'v3', credentials=creds)
    body = {
        'start': {'dateTime': to_rfc3339(start)},
        'end': {'dateTime': to_rfc3339(end)},
    }
    service.events().patch(calendarId=calendar_id, eventId=event_id, body=body, sendUpdates='all').execute()
