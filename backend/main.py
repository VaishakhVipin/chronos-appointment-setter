from fastapi import FastAPI
from routes.voice import router as voice_router

app = FastAPI()
app.include_router(voice_router)

@app.get("/")
def home():
    return {"status": "Chronos Backend Live"}