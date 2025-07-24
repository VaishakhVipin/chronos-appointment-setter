from fastapi import APIRouter, WebSocket, Request, Response, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from xml.etree.ElementTree import Element, tostring
import asyncio
from services.assembly import stream_transcribe
from core.agent import agent_loop
import os
import json
from datetime import datetime, timedelta
from services.gmail import send_email
from dotenv import load_dotenv
load_dotenv()
import base64
import httpx
import websockets
import numpy as np
from scipy.signal import resample

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

@router.websocket("/twilio/stream")
async def twilio_stream(websocket: WebSocket):
    await websocket.accept()
    print("[twilio] WebSocket connection accepted")
    try:
        # 1. Get AssemblyAI temporary token
        token_resp = httpx.post(
            "https://streaming.assemblyai.com/v3/token?expires_in_seconds=600",
            headers={"authorization": os.getenv("ASSEMBLYAI_API_KEY")}
        )
        token = token_resp.json()["token"]
        print(f"[assemblyai] Got streaming token: {token}")
        # 2. Connect to AssemblyAI streaming API
        aai_ws_url = f"wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&formatted_finals=true&token={token}"
        async with websockets.connect(aai_ws_url) as aai_ws:
            print("[assemblyai] Connected to streaming API")
            try:
                async def recv_aai():
                    async for msg in aai_ws:
                        data = json.loads(msg)
                        if data.get("text"):
                            print(f"[assemblyai] Transcript: {data['text']}")
                recv_task = asyncio.create_task(recv_aai())
                audio_buffer = b""
                MIN_CHUNK_SIZE = 1600  # 50ms at 16kHz, 16-bit mono
                while True:
                    msg = await websocket.receive_text()
                    print("[twilio] Received message:", msg)  # Log every incoming message
                    data = json.loads(msg)
                    if data.get("event") == "media":
                        # Twilio sends base64-encoded mulaw or PCM audio
                        audio_b64 = data["media"]["payload"]
                        audio_bytes = base64.b64decode(audio_b64)
                        # --- BEGIN RESAMPLING LOGIC ---
                        input_sample_rate = 8000  # <-- set this to actual rate if different
                        if input_sample_rate != 16000:
                            import numpy as np
                            from scipy.signal import resample
                            input_pcm = np.frombuffer(audio_bytes, dtype=np.int16)
                            output_pcm = resample(input_pcm, int(len(input_pcm) * 16000 / input_sample_rate)).astype(np.int16)
                            audio_bytes_16k = output_pcm.tobytes()
                        else:
                            audio_bytes_16k = audio_bytes
                        # --- END RESAMPLING LOGIC ---
                        # Buffer and send only >=50ms chunks
                        audio_buffer += audio_bytes_16k
                        while len(audio_buffer) >= MIN_CHUNK_SIZE:
                            chunk = audio_buffer[:MIN_CHUNK_SIZE]
                            await aai_ws.send(chunk)
                            audio_buffer = audio_buffer[MIN_CHUNK_SIZE:]
                    elif data.get("event") == "stop":
                        print("[twilio] Stream stopped by Twilio")
                        # Send any remaining audio in the buffer
                        if audio_buffer:
                            await aai_ws.send(audio_buffer)
                            audio_buffer = b""
                        break
            except WebSocketDisconnect:
                print("[twilio] WebSocket disconnected")
            except Exception as e:
                print("[twilio/stream] Exception:", e)
                import traceback; traceback.print_exc()
            finally:
                await websocket.close()
                if 'recv_task' in locals():
                    recv_task.cancel()
                    try:
                        await recv_task
                    except Exception:
                        pass
                print("[twilio/stream] WebSocket closed")
        print("[twilio] WebSocket closed")
    except Exception as e:
        print("[twilio/stream] Outer exception:", e)
        import traceback; traceback.print_exc()
        await websocket.close()
        print("[twilio/stream] WebSocket closed (outer)")

@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    import os
    response = Element("Response")
    say = Element("Say")
    say.text = "Welcome to Chronos! Please speak after the beep."
    response.append(say)
    start = Element("Start")
    base_ws_url = os.getenv("SERVER_URL", "wss://your-ngrok-or-server-url")
    stream_url = f"{base_ws_url}/twilio/stream"
    stream = Element("Stream", {
        "url": stream_url
    })
    start.append(stream)
    response.append(start)
    pause = Element("Pause", {"length": "60"})
    response.append(pause)
    xml_str = tostring(response, encoding="unicode")
    return PlainTextResponse(xml_str, media_type="application/xml")

@router.post("/twilio/voice/recording", name="twilio_voice_recording")
async def twilio_voice_recording(request: Request):
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    caller = form.get("From")
    # TODO: Send recording_url to AssemblyAI for transcription
    print(f"[twilio] Received recording from {caller}: {recording_url}")
    return PlainTextResponse("<Response><Say>Thank you. Your message has been received.</Say></Response>", media_type="application/xml")

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
