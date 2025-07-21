# services/tts.py
import os
import requests
from dotenv import load_dotenv
load_dotenv()

def speak(text: str, filename: str = "response.wav") -> str:
    if not text or not isinstance(text, str) or not text.strip():
        print("❌ TTS Error: text must be a non-empty string.")
        return ""
    url = (
        "https://api.deepgram.com/v1/speak"
        "?model=aura-asteria-en"
        "&encoding=linear16"
        "&sample_rate=16000"
    )
    headers = {
        "Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {"text": text}
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(response.content)
            print(f"✅ TTS saved to: {filename}")
            return filename
        else:
            print("❌ TTS Error:", response.text)
            return ""
    except Exception as e:
        print("❌ TTS Error:", e)
        return ""
