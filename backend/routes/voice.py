from fastapi import APIRouter, WebSocket
import asyncio
from services.assembly import stream_transcribe
from core.agent import agent_loop
import os
import json
from datetime import datetime, timedelta
from services.gmail import send_email
from dotenv import load_dotenv
load_dotenv()

router = APIRouter()

@router.websocket("/stream")
async def handle_stream(websocket: WebSocket):
    await websocket.accept()
    print("🟢 WebSocket connected")
    async def audio_chunk_iter():
        while True:
            chunk = await websocket.receive_bytes()
            if not chunk:
                break
            yield chunk
    try:
        async for final_text in stream_transcribe(audio_chunk_iter()):
            print(f"📝 Final transcript: {final_text}")
            result = await agent_loop(final_text)
            await websocket.send_json({"text": result["text"], "tts_path": result["tts_path"]})
            with open(result["tts_path"], "rb") as f:
                audio_bytes = f.read()
            await websocket.send_bytes(audio_bytes)
    except Exception as e:
        print(f"❌ Error in stream: {e}")
    finally:
        await websocket.close()
        print("🔴 WebSocket closed")

@router.post("/send_daily_digest")
def send_daily_digest(clear_log: bool = False):
    log_path = "daily_log.jsonl"
    if not os.path.exists(log_path):
        return {"status": "no log file"}
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", ""))
                if ts > yesterday:
                    entries.append(entry)
            except Exception:
                continue
    qualified = [e for e in entries if e["qualification"].get("qualified")]
    if not qualified:
        print("[digest] No qualified leads for the day. No email sent.")
        return {"status": "no qualified leads"}
    # Format digest
    date_str = now.strftime("%B %d")
    subject = f"[DAILY DIGEST] {len(qualified)} Qualified Conversations - {date_str}"
    body = f"[DAILY DIGEST] {len(qualified)} Qualified Conversations - {date_str}\n\n"
    for i, e in enumerate(qualified, 1):
        body += f"{i}. User: \"{e['user_utterance']}\"\n"
        body += f"   → Qualified: {'✅' if e['qualification']['qualified'] else '❌'}\n"
        body += f"   → Intent: {e['intent']}\n"
        body += f"   → Slot: {e['slot']}\n"
        body += f"   → Routed to: {e['contact']}\n\n"
    to_email = os.getenv("DAILY_DIGEST_EMAIL")
    if not to_email:
        print("[digest] DAILY_DIGEST_EMAIL not set in .env")
        return {"status": "no email configured"}
    send_email(subject, body, to_email)
    print(f"[digest] Sent daily digest to {to_email}")
    if clear_log:
        open(log_path, "w").close()
        print("[digest] Cleared daily_log.jsonl after sending.")
    return {"status": "sent", "to": to_email, "count": len(qualified)}
