import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import asyncio
from core.agent import agent_loop

if __name__ == "__main__":
    # Simulate a user utterance that should trigger qualification and booking
    user_utterance = "Hey, I'm the founder of a B2B SaaS and want to book a growth strategy call next week."
    print(f"[simulate_call] User says: {user_utterance}")
    result = asyncio.run(agent_loop(user_utterance))
    print("[simulate_call] Agent response:")
    for k, v in result.items():
        print(f"  {k}: {v}")
