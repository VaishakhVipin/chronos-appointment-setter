import os
import google.generativeai as genai
from dotenv import load_dotenv
import json
import asyncio
from functools import lru_cache

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# Pre-load/warm-up the model (dummy call)
def _warmup():
    try:
        model.generate_content("Hello! This is a warmup.")
    except Exception:
        pass
_warmup()

# Simple in-memory cache for prompt/response pairs
_gemini_cache = {}

def _cache_key(prompt):
    return hash(prompt)

async def async_generate_content(prompt, streaming=False):
    key = _cache_key(prompt)
    if key in _gemini_cache:
        return _gemini_cache[key]
    # Use streaming if available
    if hasattr(model, 'generate_content'):
        if streaming:
            # If streaming is supported, use it (Gemini API may not support this yet)
            res = model.generate_content(prompt, stream=True)
            # Collect the streamed response
            raw = "".join([chunk.text for chunk in res])
        else:
            res = model.generate_content(prompt)
            raw = res.text.strip()
    else:
        res = model.generate_content(prompt)
        raw = res.text.strip()
    _gemini_cache[key] = raw
    return raw

# --- INTENT & SLOT EXTRACTION (DETAILED GUIDELINES, CONCISE OUTPUT) ---
async def parse_intent(user_input: str):
    prompt = f"""
You are an expert AI scheduling agent. Your job is to extract the user's intent (book_call, cancel_call, general_query), the most likely requested time (plain text), and the call duration (e.g. '15m', '30m', '1 hour', or null if not specified) from the following message. Be accurate and context-aware.

User message:
{user_input}

Respond in JSON:
{{"intent":..., "datetime":..., "duration":...}}
"""
    raw = await async_generate_content(prompt)
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed.get("intent"), parsed.get("datetime"), parsed.get("duration")
    except Exception as e:
        print("❌ Error parsing Gemini output:", e)
        print("🔴 Raw:", raw)
        return "unknown", "unknown", None

# --- LLM REPLY GENERATION (DETAILED GUIDELINES, CONCISE OUTPUT) ---
async def generate_llm_reply(intent, slot, contact, business_context, error=None, timezone=None):
    prompt = f"""
You are an AI scheduling assistant for {business_context['seller']}.
Your job is to help users book, reschedule, or cancel calls as efficiently as possible.
Guidelines:
- Always confirm or mention the time zone when discussing or confirming a booking.
- Be direct, concise, and only ask for what is needed to complete the booking.
- Do not repeat information or add unnecessary politeness.
- Never generate a verbose or epic response; keep it short and actionable.
- If the user is booking, confirm the time, date, and time zone.

Intent: {intent}
Slot: {slot}
Contact: {contact['name']} ({contact['role']})
Offer: {business_context['offer']}
Time zone: {timezone or 'America/New_York'}
"""
    if error:
        prompt += f"\nError: {error}\nRespond with a short, actionable next step."
    raw = await async_generate_content(prompt)
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    return raw

# --- QUALIFICATION CLASSIFICATION (DEEPER, STRICTER) ---
async def classify_qualification(user_utterance: str, business_context, qualification_profile):
    prompt = f"""
You are a lead qualification AI for {business_context['seller']}.
Guidelines:
- Only qualify if the user CLEARLY matches ALL of the ideal client profile:
  - Type: {qualification_profile['ideal_user']['type']}
  - Revenue: {qualification_profile['ideal_user']['revenue']}
  - Pain points: {', '.join(qualification_profile['ideal_user']['pain_points'])}
- If the message is generic, random, not business-related, or does not mention relevant business context, DO NOT qualify.
- If in doubt, disqualify and explain why.
- If not qualified, route to the correct contact or ignore as appropriate.
- Provide a short explanation of your reasoning in the JSON response.

User message: "{user_utterance}"

Respond ONLY in this JSON format:
{{
  "qualified": true/false,
  "reason": "...",
  "route_to": null or "Aryan" or "Ignore"
}}
"""
    raw = await async_generate_content(prompt)
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
