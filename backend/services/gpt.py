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

# --- INTENT PARSING ---
async def parse_intent(user_input: str):
    prompt = f"""
You are a highly skilled, consultative sales strategist for a B2B growth agency. Your job is to:
- Listen deeply to the caller's needs, goals, and pain points.
- If the user's message is vague or lacks detail, do NOT immediately try to build rapport or help. Instead, gently ask qualifying questions to determine their intent and fit. Only proceed to help or build rapport if they are qualified or provide more information.
- Extract the user's intent: are they looking to book a call, cancel, or just asking questions?
- If the user's needs are unclear, ask a smart, open-ended follow-up (e.g., 'Can you tell me a bit more about your current challenges?').
- Only suggest a call if you genuinely believe it will help the caller.
- Never sound pushy—be consultative, insightful, and human.

Here's the user input:
{user_input}

Respond ONLY in this JSON format:
{{
  "intent": "...",
  "datetime": "...",
  "duration": "..."  // e.g., '15m', '30m', '1 hour', or null
}}
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

# --- LLM REPLY GENERATION ---
async def generate_llm_reply(intent, slot, contact, business_context, error=None):
    import random
    prompt = f"""
You are a highly skilled, consultative sales strategist for {business_context['seller']}.
Your job is to:
- Listen deeply to the caller's needs, goals, and pain points.
- Respond with empathy, insight, and helpfulness.
- Ask clarifying questions if you need more info.
- Only suggest a call if you genuinely believe it will help the caller.
- If the user is not a fit, explain why and offer a helpful next step or resource.
- Never sound pushy—be consultative, insightful, and human.

Context:
Intent: {intent}
Slot: {slot}
Offer: {business_context['offer']}
Seller: {business_context['seller']}
Contact: {contact['name']} ({contact['role']})

{f'Error: {error}' if error else ''}

Respond with a single, natural, human-sounding sentence.
"""
    raw = await async_generate_content(prompt)
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
    return raw

# --- QUALIFICATION CLASSIFICATION (CONSULTATIVE, NUANCED) ---
async def classify_qualification(user_utterance: str, business_context, qualification_profile):
    prompt = f"""
You are a sales qualification expert for {business_context['seller']}.
Guidelines:
- Listen for signals of business type, revenue, and pain points, but also use your judgment: if the user seems promising but is missing one detail, ask a follow-up question.
- If the user is not a fit, explain why in a friendly, constructive way.
- If the user is confused or not ready, offer to answer questions or provide resources instead of pushing for a call.
- Only qualify if the user CLEARLY matches the ideal client profile:
  - Type: {qualification_profile['ideal_user']['type']}
  - Revenue: {qualification_profile['ideal_user']['revenue']}
  - Pain points: {', '.join(qualification_profile['ideal_user']['pain_points'])}
- If the message is generic, random, not business-related, or does not mention relevant business context, DO NOT qualify.
- If in doubt, disqualify and explain why.
- If not qualified, route to the correct contact or ignore as appropriate.
- Provide a short explanation of your reasoning in the JSON response.

User message: "{user_utterance}"

Respond ONLY in this JSON format:
{
  "qualified": true/false,
  "reason": "...",
  "route_to": null or "Aryan" or "Ignore"
}
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
