from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.chat import router as chat_router 
from app.api.routes.lead import router as lead_router
from app.core.config import settings
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)

@app.get("/healthz")
async def liveness():
    return {"status": "ok"}

app.include_router(chat_router, prefix="/api")
app.include_router(lead_router, prefix="/api")