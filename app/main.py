from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.debug import router as debug_router
from app.api.routes.lead import router as lead_router
from app.core.config import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dashboard can run from any origin
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "x-visitor-id"],
)


import os

@app.get("/healthz")
async def liveness():
    return {
        "status": "ok",
        "debug_token_set": bool(settings.debug_token),
        "debug_env_names": [k for k in os.environ if "DEBUG" in k.upper()],
    }


app.include_router(chat_router, prefix="/api")
app.include_router(lead_router, prefix="/api")
app.include_router(debug_router, prefix="/api")