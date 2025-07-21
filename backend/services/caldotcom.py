import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

CAL_API_KEY = os.getenv("CAL_API_KEY")
BASE_URL = "https://api.cal.com/v1"
CAL_USERNAME = os.getenv("CAL_USERNAME")


def get_event_type_id_from_username(username: str = None):
    if not username:
        username = CAL_USERNAME
    url = f"{BASE_URL}/event-types"
    headers = {"Authorization": f"Bearer {CAL_API_KEY}"}
    params = {"username": username}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    # Return the first event type id found, or None
    event_types = data.get("eventTypes") or data.get("event_types") or data
    if isinstance(event_types, list) and event_types:
        return event_types[0].get("id")
    return None


def get_available_slots(event_type_id: str = None, username: str = None, timezone: str = "UTC"):
    if not username:
        username = CAL_USERNAME
    if not event_type_id:
        event_type_id = get_event_type_id_from_username(username)
    url = f"{BASE_URL}/availability"
    headers = {"Authorization": f"Bearer {CAL_API_KEY}"}
    today = datetime.utcnow().date()
    end_date = today + timedelta(days=7)
    params = {
        "username": username,
        "eventTypeId": event_type_id,
        "timezone": timezone,
        "startDate": today.isoformat(),
        "endDate": end_date.isoformat(),
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def book_slot(event_type_id: str = None, name: str = "", email: str = "", start_time: str = "", timezone: str = "UTC", username: str = None):
    if not username:
        username = CAL_USERNAME
    if not event_type_id:
        event_type_id = get_event_type_id_from_username(username)
    url = f"{BASE_URL}/bookings"
    headers = {
        "Authorization": f"Bearer {CAL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "eventTypeId": event_type_id,
        "attendees": [{"name": name, "email": email}],
        "start": start_time,
        "timezone": timezone
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
