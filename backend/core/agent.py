import os
import traceback
import json
from datetime import datetime
from services.gpt import parse_intent
from services.caldotcom import get_available_slots, book_slot
from services.tts import speak

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

# Simple state dict for session memory
state = {
    "last_intent": None,
    "last_slot": None,
    "last_contact": None,
    "errors": []
}

def pick_contact():
    # For now, always pick the first contact (Vaishakh)
    return BUSINESS_CONTEXT["contacts"][0]

def generate_llm_reply(intent, slot, contact, error=None):
    from services.gpt import model
    prompt = f"""
You're a friendly scheduling assistant for {BUSINESS_CONTEXT['seller']}. Based on the intent and slot info below, generate a natural, helpful sentence to say back to the user.

Intent: {intent}
Slot: {slot}
Offer: {BUSINESS_CONTEXT['offer']}
Seller: {BUSINESS_CONTEXT['seller']}
Contact: {contact['name']} ({contact['role']})
"""
    if error:
        prompt += f"\nError: {error}\nIf there is an error, suggest a helpful next step or alternative."
    res = model.generate_content(prompt)
    raw = res.text.strip()
    # Remove markdown code block if present
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    return raw

def classify_qualification(user_utterance: str):
    from services.gpt import model
    prompt = f"""
You are a qualification assistant for {BUSINESS_CONTEXT['seller']}.
Here is the ideal client profile:
{QUALIFICATION_PROFILE['ideal_user']}
Non-ideal routes: {QUALIFICATION_PROFILE['non_ideal_routes']}

Based on this user's message, are they a qualified prospect for our growth strategy call? If not, label them and suggest how to respond.

User message: "{user_utterance}"

Respond ONLY in this JSON format:
{{
  "qualified": true/false,
  "reason": "...",
  "route_to": null or "Aryan" or "Ignore"
}}
"""
    res = model.generate_content(prompt)
    raw = res.text.strip()
    # Remove markdown code block if present
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

async def agent_loop(user_utterance: str):
    try:
        print(f"[agent] User utterance: {user_utterance}")
        # 1. Qualification step
        qualification = classify_qualification(user_utterance)
        print(f"[agent] Qualification: {qualification}")
        # 2. Run Gemini (intent/slot extraction)
        intent, slot = parse_intent(user_utterance)
        print(f"[agent] Gemini intent: {intent}, slot: {slot}")
        contact = pick_contact()
        state["last_intent"] = intent
        state["last_slot"] = slot
        state["last_contact"] = contact["name"]
        state["errors"] = []
        response_text = ""
        booking_confirmation = None
        error = None
        # 3. Routing logic
        if qualification["qualified"]:
            # Proceed to booking
            if intent == "book_call":
                try:
                    slots = get_available_slots()
                    print(f"[agent] Available slots: {slots}")
                    # Pick first available slot
                    first_slot = None
                    for day in slots.get('availability', []):
                        if day.get('slots'):
                            first_slot = day['slots'][0]
                            break
                    if first_slot:
                        booking_confirmation = book_slot(
                            name=contact["name"],
                            email="sample@example.com",
                            start_time=first_slot,
                            timezone=os.getenv("TIMEZONE", "America/New_York")
                        )
                        print(f"[agent] Booking confirmation: {booking_confirmation}")
                        slot = first_slot
                        response_text = generate_llm_reply(intent, slot, contact)
                    else:
                        error = "No available slots"
                        state["errors"].append(error)
                        response_text = generate_llm_reply(intent, slot, contact, error=error)
                except Exception as e:
                    error = f"Booking error: {e}"
                    state["errors"].append(error)
                    print(f"[agent] Booking error: {e}\n{traceback.format_exc()}")
                    response_text = generate_llm_reply(intent, slot, contact, error=error)
            elif intent == "cancel_call":
                response_text = generate_llm_reply(intent, slot, contact)
            else:
                response_text = generate_llm_reply(intent, slot, contact)
        else:
            # Not qualified
            if qualification.get("route_to"):
                # Route to team member
                route_contact = next((c for c in BUSINESS_CONTEXT["contacts"] if c["name"] == qualification["route_to"]), None)
                if route_contact:
                    response_text = generate_llm_reply(
                        intent,
                        slot,
                        route_contact,
                        error=f"User not qualified. Route to {route_contact['name']}"
                    )
                else:
                    response_text = generate_llm_reply(
                        intent,
                        slot,
                        contact,
                        error=f"User not qualified. Route to {qualification['route_to']}"
                    )
            else:
                # Polite decline
                response_text = generate_llm_reply(
                    intent,
                    slot,
                    contact,
                    error=f"User not qualified. Reason: {qualification.get('reason')}"
                )
        # 4. Convert to TTS
        tts_path = speak(response_text)
        print(f"[agent] TTS path: {tts_path}")
        # 5. Log qualified leads/bookings
        if qualification["qualified"] or (intent == "book_call" and booking_confirmation):
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_utterance": user_utterance,
                "intent": intent,
                "slot": slot,
                "contact": contact["name"],
                "qualification": qualification
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
            "qualification": qualification
        }
    except Exception as e:
        print(f"[agent] Error: {e}\n{traceback.format_exc()}")
        fallback_text = generate_llm_reply("unknown", None, pick_contact(), error=str(e))
        tts_path = speak(fallback_text)
        state["errors"].append(str(e))
        return {
            "text": fallback_text,
            "tts_path": tts_path,
            "intent": "unknown",
            "slot": None,
            "contact": pick_contact()["name"],
            "errors": state["errors"],
            "qualification": {"qualified": False, "reason": str(e), "route_to": None}
        } 