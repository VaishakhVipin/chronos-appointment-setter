import os
from services.caldotcom import book_slot_v2
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    event_type_id = os.getenv("CAL_EVENT_TYPE_ID")
    if not event_type_id:
        print("ERROR: Please set CAL_EVENT_TYPE_ID in your environment or .env file.")
        exit(1)
    event_type_id = int(event_type_id)
    username = os.getenv("CAL_USERNAME")
    print(f"Testing Cal.com integration for user: {username}, event_type_id: {event_type_id}")

    name = "Test User"
    email = "testuser@example.com"
    # Use timezone-aware UTC datetime
    start_time = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat().replace('+00:00', 'Z')
    timezone_str = "America/New_York"
    print(f"Booking slot at {start_time}...")
    try:
        booking = book_slot_v2(
            start=start_time,
            name=name,
            email=email,
            timezone=timezone_str,
            event_type_id=event_type_id,
            username=username,
            debug=True
        )
        print("Booking response:", booking)
    except Exception as e:
        print("Booking failed:", e) 