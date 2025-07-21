import os
import google.generativeai as genai
from dotenv import load_dotenv
import json

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# --- INTENT PARSING ---
def parse_intent(user_input: str):
    prompt = f"""
You're a backend AI agent for a voice scheduling system. Your job is to extract:
1. The user's intent — only respond with 'book_call', 'cancel_call', or 'general_query'
2. The most likely time the user wants (in plain text, e.g. 'Friday 6pm')

Here's the user input:
\"\"\"{user_input}\"\"\"

Respond ONLY in this JSON format:
{{
  "intent": "...",
  "datetime": "..."
}}
"""
    res = model.generate_content(prompt)
    raw = res.text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed.get("intent"), parsed.get("datetime")
    except Exception as e:
        print("❌ Error parsing Gemini output:", e)
        print("🔴 Raw:", raw)
        return "unknown", "unknown"

# --- LLM REPLY GENERATION ---
def generate_llm_reply(intent, slot, contact, business_context, error=None):
    prompt = f"""
You're a friendly scheduling assistant for {business_context['seller']}. Based on the intent and slot info below, generate a natural, helpful sentence to say back to the user.

Intent: {intent}
Slot: {slot}
Offer: {business_context['offer']}
Seller: {business_context['seller']}
Contact: {contact['name']} ({contact['role']})
"""
    if error:
        prompt += f"\nError: {error}\nIf there is an error, suggest a helpful next step or alternative."
    res = model.generate_content(prompt)
    raw = res.text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    return raw

# --- QUALIFICATION CLASSIFICATION ---
def classify_qualification(user_utterance: str, business_context, qualification_profile):
    prompt = f"""
You are a qualification assistant for {business_context['seller']}.
Here is the ideal client profile:
{qualification_profile['ideal_user']}
Non-ideal routes: {qualification_profile['non_ideal_routes']}

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
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    try:
        q = json.loads(raw)
        return q
    except Exception as e:
        print(f"[gpt] Qualification parse error: {e}, raw: {raw}")
        return {"qualified": False, "reason": "Could not parse LLM output", "route_to": None}
