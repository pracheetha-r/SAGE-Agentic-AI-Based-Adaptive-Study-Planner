import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None
    HttpError = Exception
    GOOGLE_AUTH_AVAILABLE = False

import config
import database as db

TZ = ZoneInfo(config.TIMEZONE)


def _load_creds():
    if not GOOGLE_AUTH_AVAILABLE or not os.path.exists(config.GOOGLE_TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(config.GOOGLE_TOKEN_FILE,
                                                  config.GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(config.GOOGLE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception:
            return None
    return creds if creds.valid else None


def is_connected():
    return _load_creds() is not None


def has_client_file():
    return GOOGLE_AUTH_AVAILABLE and os.path.exists(config.GOOGLE_CREDENTIALS_FILE)


def account_label():
    """Calendar title of the primary calendar (normally the Google account email).
    Saved the last time we talked to Google, so the UI can show it offline."""
    return db.get_setting("calendar_label", "")


def connect():
    """Opens the browser for Google consent, then stores token.json."""
    flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_FILE,
                                                     config.GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0)
    with open(config.GOOGLE_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def _service():
    creds = _load_creds()
    return build("calendar", "v3", credentials=creds, cache_discovery=False) if creds else None


def _to_local(iso):
    return datetime.fromisoformat(iso).astimezone(TZ).replace(tzinfo=None)


def _iso(dt):
    return dt.replace(tzinfo=TZ).isoformat()


def _fetch(svc, start, end):
    resp = svc.events().list(
        calendarId="primary", timeMin=_iso(start), timeMax=_iso(end),
        singleEvents=True, orderBy="startTime", maxResults=250).execute()
    if resp.get("summary"):
        db.set_setting("calendar_label", resp["summary"])
    return resp.get("items", [])


def _external_events(items):
    """Timed events that are not SAGE's own and that block study time."""
    out = []
    for ev in items:
        if ev.get("status") == "cancelled" or ev.get("transparency") == "transparent":
            continue
        if ev.get("extendedProperties", {}).get("private", {}).get("sage_session_id"):
            continue
        s, e = ev.get("start", {}), ev.get("end", {})
        if "dateTime" not in s or "dateTime" not in e:
            continue                                   # all-day events are ignored
        out.append({"start": _to_local(s["dateTime"]), "end": _to_local(e["dateTime"]),
                    "title": ev.get("summary", "Busy")})
    return out


def get_busy_intervals(start, end):
    """Returns (busy_list, status)."""
    svc = _service()
    if svc is None:
        return [], "disabled"
    try:
        items = _fetch(svc, start, end)
    except Exception:
        return [], "unavailable"
    return [(e["start"], e["end"]) for e in _external_events(items)], "ok"


def get_day_events(day):
    """Calendar events for one day (for the schedule view). [] if unavailable."""
    svc = _service()
    if svc is None:
        return []
    try:
        start = datetime.combine(day, time.min)
        return _external_events(_fetch(svc, start, start + timedelta(days=1)))
    except Exception:
        return []


def _event_body(s):
    fmt = "%Y-%m-%dT%H:%M:%S"
    return {
        "summary": f"SAGE: {s['topic']}",
        "description": f"{s['subject']} study session planned by SAGE",
        "start": {"dateTime": s["start"].strftime(fmt), "timeZone": config.TIMEZONE},
        "end": {"dateTime": s["end"].strftime(fmt), "timeZone": config.TIMEZONE},
        "extendedProperties": {"private": {"sage_session_id": str(s["id"])}},
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": 10}]},
    }


def sync_all():
    """Push the local plan to Google Calendar. Returns a status string."""
    svc = _service()
    if svc is None:
        return "disabled"
    try:
        events = svc.events()
        for s in db.get_sessions(statuses=["cancelled"]):
            if s["event_id"]:
                try:
                    events.delete(calendarId="primary", eventId=s["event_id"]).execute()
                except HttpError as e:
                    if e.resp.status not in (404, 410):
                        raise
            db.delete_session(s["id"])

        for s in db.get_sessions(statuses=["planned"]):
            if s["sync_status"] == "synced":
                continue
            body = _event_body(s)
            if s["event_id"]:
                events.patch(calendarId="primary", eventId=s["event_id"], body=body).execute()
                eid = s["event_id"]
            else:
                eid = f"sage{s['id']:08d}a"
                try:
                    events.insert(calendarId="primary", body={**body, "id": eid}).execute()
                except HttpError as e:
                    if e.resp.status == 409:
                        events.patch(calendarId="primary", eventId=eid, body=body).execute()
                    else:
                        raise
            db.update_event(s["id"], eid, "synced")
        return "synced"
    except Exception as e:
        return f"pending ({type(e).__name__})"