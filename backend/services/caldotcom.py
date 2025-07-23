import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

CAL_API_KEY = os.getenv("CAL_API_KEY")
BASE_URL = "https://api.cal.com/v2"
CAL_USERNAME = os.getenv("CAL_USERNAME")
CAL_API_VERSION = "2024-08-13"  # required by v2 API

# --- v2 Booking Endpoints ---
def create_booking(event_type_id, name, email, start_time, timezone="UTC", length_in_minutes=30, username=None, **kwargs):
    """
    Create a booking using Cal.com v2 API.
    """
    if not username:
        username = CAL_USERNAME
    url = f"{BASE_URL}/bookings"
    headers = {
        "Content-Type": "application/json",
        "cal-api-version": CAL_API_VERSION,
        "Authorization": f"Bearer {CAL_API_KEY}"
    }
    payload = {
        "start": start_time,
        "attendee": {
            "name": name,
            "email": email,
            "timeZone": timezone,
            "language": "en"
        },
        "eventTypeId": event_type_id,
        "username": username,
        "lengthInMinutes": length_in_minutes
    }
    payload.update(kwargs)
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def reschedule_booking(booking_uid, new_start_time, rescheduled_by, rescheduling_reason=None):
    """
    Reschedule a booking using Cal.com v2 API.
    """
    url = f"{BASE_URL}/bookings/{booking_uid}/reschedule"
    headers = {
        "Content-Type": "application/json",
        "cal-api-version": CAL_API_VERSION,
        "Authorization": f"Bearer {CAL_API_KEY}"
    }
    payload = {
        "start": new_start_time,
        "rescheduledBy": rescheduled_by
    }
    if rescheduling_reason:
        payload["reschedulingReason"] = rescheduling_reason
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def get_booking(booking_uid):
    """
    Get a booking by UID using Cal.com v2 API.
    """
    url = f"{BASE_URL}/bookings/{booking_uid}"
    headers = {
        "cal-api-version": CAL_API_VERSION,
        "Authorization": f"Bearer {CAL_API_KEY}"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def cancel_booking(booking_uid, cancelled_by=None, cancellation_reason=None):
    """
    Cancel a booking using Cal.com v2 API.
    """
    url = f"{BASE_URL}/bookings/{booking_uid}/cancel"
    headers = {
        "Content-Type": "application/json",
        "cal-api-version": CAL_API_VERSION,
        "Authorization": f"Bearer {CAL_API_KEY}"
    }
    payload = {}
    if cancelled_by:
        payload["cancelledBy"] = cancelled_by
    if cancellation_reason:
        payload["cancellationReason"] = cancellation_reason
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def get_available_slots(event_type_id: str = None, username: str = None, timezone: str = "UTC"):
    """
    Fetch available slots for a given event type and user using Cal.com v1 API.
    Returns the JSON response from the API.
    """
    if not username:
        username = CAL_USERNAME
    if not event_type_id:
        raise ValueError("event_type_id must be provided for get_available_slots.")
    url = "https://api.cal.com/v1/availability"
    today = datetime.utcnow().date()
    end_date = today + timedelta(days=7)
    params = {
        "username": username,
        "eventTypeId": event_type_id,
        "timezone": timezone,
        "dateFrom": today.isoformat(),
        "dateTo": end_date.isoformat(),
        "apiKey": CAL_API_KEY
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def book_slot_v2(
    *,
    start,
    name,
    email,
    timezone,
    event_type_id=None,
    event_type_slug=None,
    username=None,
    length_in_minutes=None,
    booking_fields_responses=None,
    debug=False
):
    """
    Book a slot on Cal.com v2 API.
    Required:
      - start: ISO UTC time (e.g. '2025-07-24T10:00:00Z')
      - name, email, timezone: attendee info
      - Either event_type_id (int) OR event_type_slug (str) + username (str)
    Optional:
      - length_in_minutes: int (ONLY for event types with multiple possible lengths)
      - booking_fields_responses: dict
      - debug: bool (print payload and response)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CAL_API_KEY}",
        "cal-api-version": CAL_API_VERSION
    }
    payload = {
        "start": start,
        "attendee": {
            "name": name,
            "email": email,
            "timeZone": timezone
        }
    }
    # Only one event type method
    if event_type_id is not None:
        payload["eventTypeId"] = int(event_type_id)
    elif event_type_slug and username:
        payload["eventTypeSlug"] = event_type_slug
        payload["username"] = username
    else:
        raise ValueError("Must provide either event_type_id or (event_type_slug and username)")
    # Only include lengthInMinutes if provided (for multi-length event types)
    if length_in_minutes is not None:
        payload["lengthInMinutes"] = int(length_in_minutes)
    if booking_fields_responses:
        payload["bookingFieldsResponses"] = booking_fields_responses
    if debug:
        print("[caldotcom.book_slot_v2] Payload:", payload)
    response = requests.post(f"{BASE_URL}/bookings", headers=headers, json=payload)
    if debug or not response.ok:
        print("[caldotcom.book_slot_v2] Response status:", response.status_code)
        print("[caldotcom.book_slot_v2] Response body:", response.text)
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise
    return response.json()


def debug_booking(event_type_id, name, email, start_time, timezone="UTC", username=None, api_key=None):
    """
    Debug helper to POST a booking to Cal.com and print the full request/response.
    Returns a tuple: (status_code, response_json_or_text)
    """
    if not username:
        username = CAL_USERNAME
    if not api_key:
        api_key = CAL_API_KEY
    try:
        event_type_id_num = int(event_type_id)
    except Exception:
        event_type_id_num = event_type_id
    url = f"{BASE_URL}/bookings"
    headers = {"Content-Type": "application/json"}
    params = {"apiKey": api_key}
    payload = {
        "eventTypeId": event_type_id_num,
        "attendees": [{"name": name, "email": email}],
        "start": start_time,
        "timezone": timezone
    }
    print("[caldotcom.debug_booking] URL:", url)
    print("[caldotcom.debug_booking] Params:", params)
    print("[caldotcom.debug_booking] Headers:", headers)
    print("[caldotcom.debug_booking] Payload:", payload)
    resp = requests.post(url, headers=headers, params=params, json=payload)
    print("[caldotcom.debug_booking] Status:", resp.status_code)
    try:
        print("[caldotcom.debug_booking] Response JSON:", resp.json())
        return resp.status_code, resp.json()
    except Exception:
        print("[caldotcom.debug_booking] Response Text:", resp.text)
        return resp.status_code, resp.text


def get_event_type_id_by_duration(duration: str, username: str = None):
    """
    Fetch all event types for the user and return the event type id that matches the given duration string.
    Duration can be '15m', '30m', '1 hour', etc. (case-insensitive, flexible match).
    Returns None if not found.
    """
    if not username:
        username = CAL_USERNAME
    url = f"{BASE_URL}/event-types"
    params = {"username": username, "apiKey": CAL_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    event_types = data.get("eventTypes") or data.get("event_types") or data
    if not isinstance(event_types, list):
        return None
    # Normalize duration string for matching
    norm_duration = duration.lower().replace(' ', '') if duration else None
    for et in event_types:
        # Safely handle None for description, name, and length
        name = (et.get('name') or '').lower().replace(' ', '')
        desc = (et.get('description') or '').lower().replace(' ', '')
        et_length = et.get('length')
        et_duration = str(et_length).lower().replace(' ', '') if et_length is not None else ''
        # Match if duration string is in name, description, or matches length
        if norm_duration:
            if norm_duration in name or norm_duration in desc:
                return et.get('id')
            # Try to match '30m' to 30, '15m' to 15, '1hour' to 60, etc.
            if 'm' in norm_duration:
                try:
                    mins = int(norm_duration.replace('m',''))
                    if et_length == mins:
                        return et.get('id')
                except Exception:
                    pass
            elif 'hour' in norm_duration:
                try:
                    if '1hour' in norm_duration and et_length == 60:
                        return et.get('id')
                    if '2hour' in norm_duration and et_length == 120:
                        return et.get('id')
                except Exception:
                    pass
    return None
