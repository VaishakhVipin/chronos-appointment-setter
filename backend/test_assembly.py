import os
import httpx
import asyncio
import websockets
import base64
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

TTS_TEXT = "This is a test of Deepgram TTS and AssemblyAI real-time transcription."
TTS_FILE = "test_tts.wav"
TTS_MODEL = "aura-orion-en"  # Use "aura-asteria-en" for female

async def generate_deepgram_tts(text, filename, model):
    url = f"https://api.deepgram.com/v1/speak?model={model}&sample_rate=16000&encoding=linear16"
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    response = httpx.post(url, headers=headers, json={"text": text})
    response.raise_for_status()
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"[deepgram] TTS audio saved to {filename}")

async def stream_to_assemblyai(audio_path):
    # 1. Get AssemblyAI streaming token
    token_resp = httpx.get(
        "https://streaming.assemblyai.com/v3/token?expires_in_seconds=600",
        headers={"authorization": ASSEMBLYAI_API_KEY}
    )
    print("[assemblyai] Token response:", token_resp.status_code, token_resp.text)
    token = token_resp.json().get("token")
    if not token:
        raise Exception(f"Failed to get AssemblyAI token: {token_resp.text}")
    ws_url = f"wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&formatted_finals=true&token={token}"
    print(f"[assemblyai] Connecting to {ws_url}")
    async with websockets.connect(ws_url) as ws:
        print("[assemblyai] Connected to streaming API")
        # Read audio file and stream in chunks
        import soundfile as sf
        import numpy as np
        data, samplerate = sf.read(audio_path, dtype='int16')
        if samplerate != 16000:
            raise Exception("Audio file must be 16kHz for AssemblyAI streaming.")
        if data.ndim > 1:
            data = data[:, 0]  # Use first channel if stereo
        chunk_size = 3200  # 100ms at 16kHz, 16-bit mono
        idx = 0
        async def recv_transcripts():
            final_sentence = None
            try:
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        # Only print the final transcript as a proper sentence
                        if data.get("message_type") == "FinalTranscript" and data.get("text"):
                            final_sentence = data["text"]
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass
            if final_sentence:
                print("\n[assemblyai] Final transcript sentence:", final_sentence)
        recv_task = asyncio.create_task(recv_transcripts())
        while idx < len(data):
            chunk = data[idx:idx+chunk_size]
            await ws.send(chunk.tobytes())
            await asyncio.sleep(0.1)  # simulate real-time
            idx += chunk_size
        await ws.send(b"")  # send empty to signal end
        await asyncio.sleep(2)
        recv_task.cancel()
        print("[assemblyai] Streaming complete.")

if __name__ == "__main__":
    import json
    import soundfile as sf
    asyncio.run(generate_deepgram_tts(TTS_TEXT, TTS_FILE, TTS_MODEL))
    asyncio.run(stream_to_assemblyai(TTS_FILE))