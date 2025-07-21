from fastapi import APIRouter, WebSocket
import asyncio
from services.assembly import stream_transcribe
from core.agent import agent_loop

router = APIRouter()

@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    print("🟢 WebSocket client connected")

    async def audio_chunk_iter():
        while True:
            chunk = await websocket.receive_bytes()
            if not chunk:
                break
            yield chunk

    try:
        async for final_text in stream_transcribe(audio_chunk_iter()):
            print(f"📝 Final transcript: {final_text}")
            # Pass to agent loop for processing
            result = await agent_loop(final_text)
            # result: {"text": ..., "tts_path": ...}
            # Send both text and TTS audio path (or stream audio if desired)
            await websocket.send_json({"text": result["text"], "tts_path": result["tts_path"]})
            # Optionally, stream the TTS audio file back as bytes
            with open(result["tts_path"], "rb") as f:
                audio_bytes = f.read()
            await websocket.send_bytes(audio_bytes)
    except Exception as e:
        print(f"❌ Error in stream: {e}")
    finally:
        await websocket.close()
        print("�� WebSocket closed") 