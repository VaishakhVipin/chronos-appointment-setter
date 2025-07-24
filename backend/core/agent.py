import os
import traceback
import json
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from services.gpt import parse_intent
from services.caldotcom import get_available_slots, book_slot_v2, get_event_type_id_by_duration
from services.tts import speak
import random
import uuid
import time
import asyncio
import re
from typing import Tuple
from services.twilio_sms import send_sms

# Hardcoded business context
BUSINESS_CONTEXT = {
    "offer": "30-minute growth strategy call",
    "offer_value": "Diagnose your bottlenecks + outline 3 ways to grow revenue",
    "seller": "Obelisk Acquisitions",
    "contacts": [
        {"name": "Vaishakh", "role": "Closer / Strategy Head"},
        {"name": "Aryan", "role": "Fulfillment / Onboarding"}
    ]
}

# Hardcoded qualification profile
QUALIFICATION_PROFILE = {
    "ideal_user": {
        "type": "agency or B2B SaaS founder",
        "revenue": "above $10k/month",
        "pain_points": ["lead flow", "offer not converting", "wants scaling clarity"]
    },
    "non_ideal_routes": {
        "cold_sellers": "Aryan",
        "job seekers": "Ignore or send canned TTS",
        "generic service offers": "Aryan"
    }
}

# Global session memory dict
SESSION_MEMORY = {}
# Global Cal.com 401 cache
CAL_API_401_CACHE = {"last_401": 0}

# --- JUNK MESSAGE PATTERNS ---
JUNK_PATTERNS = [
    r"^(thanks|thank you|ok|cool|awesome|great)[.!]?$",
    r"^(hmm|uhh|huh|nah|nah bro|nope)$"
]

# --- RESPONSE TEMPLATES ---
ROUTER_RESPONSE_TEMPLATES = {
    "duplicate_intent_within_30s": lambda state: state.get("last_gemini_response") or "Got it — anything else I can help with?",
    "junk_message": lambda state: "All good. Let me know when you're ready to continue.",
    "pending_booking": lambda state: "Hold tight — we're just finishing up your booking. Will ping you once it's confirmed."
}

# --- ROUTER LOGGING ---
def log_router_action(session_id, reason, user_utterance, action_taken):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "reason": reason,
        "user_utterance": user_utterance,
        "action_taken": action_taken
    }
    print(f"[router] {log_entry}")
    try:
        with open("router_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[router] Failed to log: {e}")

# --- ROUTER FUNCTION ---
def should_skip_gemini(user_utterance: str, session_state: dict) -> Tuple[bool, str]:
    now = time.time()
    # 1. Pending booking
    if session_state.get("booking_pending"):
        return True, "pending_booking"
    # 2. Junk message
    for pat in JUNK_PATTERNS:
        if re.match(pat, user_utterance.strip(), re.IGNORECASE):
            return True, "junk_message"
    # 3. Duplicate intent within 30s
    last_intent = session_state.get("last_intent")
    last_intent_time = session_state.get("last_intent_time")
    if last_intent and last_intent_time:
        if session_state.get("last_user_utterance") == user_utterance.strip() and (now - last_intent_time) < 30:
            return True, "duplicate_intent_within_30s"
    return False, None

def get_session_state(session_id):
    if session_id not in SESSION_MEMORY:
        SESSION_MEMORY[session_id] = {
            "last_intent": None,
            "last_slot": None,
            "last_contact": None,
            "errors": [],
            "last_booking": None,  # Track last booking per session
            "cancelled": False,
            "qualified": None,     # Cache qualification result
            "last_user_utterance": None,  # Cache last user input
            "last_intent_result": None,   # Cache last intent/slot/duration
        }
    return SESSION_MEMORY[session_id]

def pick_contact():
    # For now, always pick the first contact (Vaishakh)
    return BUSINESS_CONTEXT["contacts"][0]

async def generate_llm_reply(intent, slot, contact, error=None):
    from services.gpt import model
    prompt = f"""
You are an AI scheduling assistant. Be direct and concise. Help the user book, reschedule, or cancel a call. Only ask for what is needed. Do not repeat information or add unnecessary politeness.
Intent: {intent}
Slot: {slot}
Contact: {contact['name']} ({contact['role']})
"""
    if error:
        prompt += f"\nError: {error}\nRespond with a short, actionable next step."
    res = await asyncio.to_thread(model.generate_content, prompt)
    raw = res.text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    return raw

async def classify_qualification(user_utterance: str, business_context, qualification_profile):
    from services.gpt import model
    prompt = f"""
Given the following user message, return ONLY this JSON:
{{
  "qualified": true/false,
  "reason": "...",
  "route_to": null or "Aryan" or "Ignore"
}}
User message: "{user_utterance}"
"""
    res = await asyncio.to_thread(model.generate_content, prompt)
    raw = res.text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    import json
    try:
        q = json.loads(raw)
        return q
    except Exception as e:
        print(f"[agent] Qualification parse error: {e}, raw: {raw}")
        return {"qualified": False, "reason": "Could not parse LLM output", "route_to": None}

def split_date_ranges_to_slots(date_ranges, slot_length_minutes=30):
    slots = []
    for rng in date_ranges:
        start = date_parser.parse(rng['start'])
        end = date_parser.parse(rng['end'])
        curr = start
        while curr + timedelta(minutes=slot_length_minutes) <= end:
            slot_start = curr
            slot_end = curr + timedelta(minutes=slot_length_minutes)
            slots.append(slot_start.isoformat())
            curr = slot_end
    return slots

def ensure_mock_dir():
    mock_dir = os.path.join(os.path.dirname(__file__), '..', 'mock')
    mock_dir = os.path.abspath(mock_dir)
    if not os.path.exists(mock_dir):
        os.makedirs(mock_dir)
    return mock_dir

async def agent_loop(user_utterance: str, session_id: str = 'simulate_call_user_1'):
    try:
        print(f"[agent] User utterance: {user_utterance}")
        state = get_session_state(session_id)
        # --- PRE-GEMINI ROUTER ---
        skip, reason = should_skip_gemini(user_utterance, state)
        if skip:
            response_text = ROUTER_RESPONSE_TEMPLATES[reason](state)
            log_router_action(session_id, reason, user_utterance, f"Skipped Gemini. Returned: {response_text}")
            # For junk, skip TTS to save tokens
            tts_path = None if reason == "junk_message" else await speak(response_text)
            return {
                "text": response_text,
                "tts_path": tts_path,
                "intent": state.get("last_intent"),
                "slot": state.get("last_slot"),
                "contact": state.get("last_contact"),
                "errors": state.get("errors", []),
                "qualification": state.get("last_qualification", {}),
                "session_id": session_id
            }
        # --- END ROUTER ---
        # 1. Qualification step (cache)
        if state.get("qualified") is not None and user_utterance == state.get("last_user_utterance"):
            qualification = state["qualified"]
            print(f"[agent] (cached) Qualification: {qualification}")
        else:
            qualification = await classify_qualification(user_utterance, BUSINESS_CONTEXT, QUALIFICATION_PROFILE)
            print(f"[agent] Qualification: {qualification}")
            state["qualified"] = qualification
        # 2. Intent/slot extraction (cache)
        if user_utterance == state.get("last_user_utterance") and state.get("last_intent_result") is not None:
            intent, slot, duration = state["last_intent_result"]
            print(f"[agent] (cached) Gemini intent: {intent}, slot: {slot}, duration: {duration}")
        else:
            intent, slot, duration = await parse_intent(user_utterance)
            print(f"[agent] Gemini intent: {intent}, slot: {slot}, duration: {duration}")
            state["last_intent_result"] = (intent, slot, duration)
        contact = pick_contact()
        state["last_intent"] = intent
        state["last_slot"] = slot
        state["last_contact"] = contact["name"]
        state["errors"] = []
        state["last_user_utterance"] = user_utterance
        response_text = ""
        booking_confirmation = None
        error = None
        now = time.time()
        # 3. Special case: gratitude/thanks utterance (handled by router now)
        # 4. Routing logic
        if qualification["qualified"]:
            # Fail-fast: skip booking if 401 seen in last 5 min
            if intent == "book_call" and (now - CAL_API_401_CACHE["last_401"] < 300):
                response_text = "Sorry, our booking system is temporarily unavailable. Redirecting you to a team member."
                state["errors"].append("Booking down: recent 401 from Cal.com API")
            elif intent == "book_call":
                try:
                    # Set booking_pending before booking
                    state["booking_pending"] = True
                    # Dynamically select event type based on duration
                    event_type_id = int(os.getenv("CAL_EVENT_TYPE_ID"))
                    if not event_type_id:
                        error = f"No event type found for duration: {duration}"
                        state["errors"].append(error)
                        response_text = await generate_llm_reply(intent, slot, contact, error=error)
                    else:
                        slots_response = get_available_slots(event_type_id=event_type_id)
                        print(f"[agent] Available slots: {slots_response}")
                        date_ranges = slots_response.get('dateRanges', [])
                        slots = split_date_ranges_to_slots(date_ranges)
                        first_slot = slots[0] if slots else None
                        if first_slot:
                            booking_confirmation = book_slot_v2(
                                start=first_slot,
                                name=contact["name"],
                                email="sample@example.com",
                                timezone=os.getenv("TIMEZONE", "America/New_York"),
                                event_type_id=event_type_id,
                                username=os.getenv("CAL_USERNAME"),
                                debug=True
                            )
                            print(f"[agent] Booking confirmation: {booking_confirmation}")
                            slot = first_slot
                            state["last_booking"] = {
                                "confirmation": booking_confirmation,
                                "slot": slot,
                                "contact": contact["name"]
                            }
                            state["cancelled"] = False
                            # --- Twilio SMS Notification ---
                            from_number = os.getenv("TWILIO_PHONE_NUMBER")
                            # Placeholder: set user_phone to the user's phone number after a successful call booking
                            user_phone = None  # TODO: Set this to the user's phone number from booking/contact/session data
                            if user_phone and from_number:
                                sms_message = f"Your call with {contact['name']} is confirmed for {first_slot} ({os.getenv('TIMEZONE', 'America/New_York')}). Reply to this SMS if you need to reschedule."
                                try:
                                    sms_sid = send_sms(user_phone, sms_message, from_number)
                                    print(f"[agent] SMS sent to {user_phone}, SID: {sms_sid}")
                                except Exception as e:
                                    print(f"[agent] Failed to send SMS: {e}")
                            response_text = await generate_llm_reply(intent, slot, contact, error=error)
                        else:
                            error = "No available slots"
                            state["errors"].append(error)
                            response_text = await generate_llm_reply(intent, slot, contact, error=error)
                except Exception as e:
                    error = f"Booking error: {e}"
                    state["errors"].append(error)
                    print(f"[agent] Booking error: {e}\n{traceback.format_exc()}")
                    if "401" in str(e):
                        CAL_API_401_CACHE["last_401"] = now
                    response_text = await generate_llm_reply(intent, slot, contact, error=error)
                finally:
                    state["booking_pending"] = False
            elif intent == "cancel_call":
                if state.get("last_booking") and not state.get("cancelled"):
                    state["cancelled"] = True
                    response_text = "No worries, your call has been canceled. If you’d ever like to reconnect, just ping us — we’ll be here."
                elif state.get("cancelled"):
                    response_text = "Your call was already cancelled."
                else:
                    response_text = "There is no active booking to cancel."
            else:
                response_text = await generate_llm_reply(intent, slot, contact, error=error)
        else:
            if qualification.get("route_to"):
                route_contact = next((c for c in BUSINESS_CONTEXT["contacts"] if c["name"] == qualification["route_to"]), None)
                if route_contact:
                    response_text = await generate_llm_reply(
                        intent,
                        slot,
                        route_contact,
                        error=f"User not qualified. Route to {route_contact['name']}"
                    )
                else:
                    response_text = await generate_llm_reply(
                        intent,
                        slot,
                        contact,
                        error=f"User not qualified. Route to {qualification['route_to']}"
                    )
            else:
                response_text = await generate_llm_reply(
                    intent,
                    slot,
                    contact,
                    error=f"User not qualified. Reason: {qualification.get('reason')}"
                )
        # 5. Convert to TTS with unique filename (async)
        mock_dir = ensure_mock_dir()
        tts_filename = os.path.join(mock_dir, f"response_{session_id}_{uuid.uuid4().hex[:8]}.wav")
        tts_path = await speak(response_text, filename=tts_filename)
        print(f"[agent] TTS path: {tts_path}")
        # Save last Gemini response for router
        state["last_gemini_response"] = response_text
        # 6. Log qualified leads/bookings
        if qualification["qualified"] or (intent == "book_call" and booking_confirmation):
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_utterance": user_utterance,
                "intent": intent,
                "slot": slot,
                "contact": contact["name"],
                "qualification": qualification,
                "session_id": session_id
            }
            with open("daily_log.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        return {
            "text": response_text,
            "tts_path": tts_path,
            "intent": intent,
            "slot": slot,
            "contact": contact["name"],
            "errors": state["errors"],
            "qualification": qualification,
            "session_id": session_id
        }
    except Exception as e:
        print(f"[agent] Error: {e}\n{traceback.format_exc()}")
        fallback_text = await generate_llm_reply("unknown", None, pick_contact(), error=str(e))
        tts_path = await speak(fallback_text)
        state = get_session_state(session_id)
        state["errors"].append(str(e))
        return {
            "text": fallback_text,
            "tts_path": tts_path,
            "intent": "unknown",
            "slot": None,
            "contact": pick_contact()["name"],
            "errors": state["errors"],
            "qualification": {"qualified": False, "reason": str(e), "route_to": None},
            "session_id": session_id
        } 