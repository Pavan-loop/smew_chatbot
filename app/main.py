from fastapi import FastAPI
from app.api.routes.chat import router as chat_router 
app = FastAPI()

@app.get("/healthz")
async def liveness():
    return {"status": "ok"}

app.include_router(chat_router, prefix="/api")