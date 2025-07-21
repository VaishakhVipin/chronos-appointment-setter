import os
import asyncio
import websockets
import json
from dotenv import load_dotenv
load_dotenv()

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
ASSEMBLYAI_URL = "wss://api.assemblyai.com/v2/realtime/ws?sample_rate=16000"

async def stream_transcribe(audio_chunk_iter):
    """
    Async generator that sends PCM audio chunks to AssemblyAI and yields final transcriptions.
    audio_chunk_iter: async iterator yielding raw PCM 16kHz mono bytes
    """
    async with websockets.connect(
        ASSEMBLYAI_URL,
        extra_headers={"Authorization": ASSEMBLYAI_API_KEY},
        max_size=10 * 1024 * 1024,  # 10MB
    ) as ws:
        print("🟢 Connected to AssemblyAI streaming API")
        async def sender():
            async for chunk in audio_chunk_iter:
                await ws.send(chunk)
            await ws.send(json.dumps({"terminate_session": True}))

        async def receiver():
            while True:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("message_type") == "FinalTranscript":
                        text = data.get("text", "")
                        if text:
                            print(f"📝 Final transcript: {text}")
                            yield text
                    elif data.get("message_type") == "SessionTerminated":
                        print("🔴 AssemblyAI session terminated")
                        break
                except websockets.ConnectionClosed:
                    print("🔴 WebSocket closed")
                    break

        sender_task = asyncio.create_task(sender())
        receiver_gen = receiver()
        try:
            async for final_text in receiver_gen:
                yield final_text
        finally:
            await sender_task
