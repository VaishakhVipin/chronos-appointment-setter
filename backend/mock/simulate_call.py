import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import asyncio
from core.agent import agent_loop
import time

user_utterances = [
    "Hey, I'm the founder of a B2B SaaS and want to book a 30m growth strategy call next week.",
    "How about Thursday at 4pm?",
    "Can I speak to Aryan instead?",
    "Actually, I want to cancel my call.",
    "Thanks!",
    # Additional test cases for dynamic duration
    "I'd like to book a 15m intro call.",
    "Can I get a 1 hour consultation on Friday?"
]

if __name__ == "__main__":
    print("=== Simulated Conversation ===")
    for i, user_utterance in enumerate(user_utterances, 1):
        print(f"\n[User {i}]: {user_utterance}")
        start = time.time()
        try:
            result = asyncio.run(agent_loop(user_utterance))
        except Exception as e:
            print(f"[simulate_call] Exception: {e}")
            continue
        print("[Agent]:")
        for k, v in result.items():
            print(f"  {k}: {v}")
        # Print Cal.com error details if present
        for err in result.get('errors', []):
            if 'Client Error' in err and 'cal.com' in err:
                print("\n[simulate_call] Cal.com API error details:")
                import re
                import requests
                match = re.search(r'for url: (https://api.cal.com[^\" ]+)', err)
                if match:
                    url = match.group(1)
                    print(f"  URL: {url}")
        print(f"[simulate_call] Step took {time.time() - start:.2f} seconds")

    # Optionally, keep the manual debug_booking section for manual testing only, or comment it out.
    # --- Cal.com booking debug ---
    print("\n=== Cal.com Booking Debug ===")
    print("[simulate_call] Skipped manual debug_booking: event_type_id is now determined dynamically based on user utterance duration and v2 API is used via agent.py (book_slot_v2).")
    # If you want to manually test booking, use the new dynamic logic in agent_loop or caldotcom.get_event_type_id_by_duration