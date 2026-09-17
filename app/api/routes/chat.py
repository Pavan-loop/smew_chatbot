import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm.openai_client import stream
from app.prompt.system import SYSTEM_PROMPT

router = APIRouter()

class ChatRequest(BaseModel):
  message: str = Field(min_length=1, max_length=500)

def sse(payload: dict) -> str:
  return f"data: {json.dumps(payload)}\n\n"

async def event_stream(message: str) -> AsyncIterator[str]:
  messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": message},
  ]
  try:
    async for chunk in stream(messages):
      yield sse({"type": "text", "text": chunk})
  except Exception as e: 
    yield sse({"type": "error", "text": "Something went wrong. Call us at 9986464819."})
  finally:
    yield sse({"type":"done"})

@router.post("/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
  return StreamingResponse(
    event_stream(body.message),
    media_type="text/event-stream",
    headers={
      "Cache-Control" : "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffereing" : "no"
    },
  )