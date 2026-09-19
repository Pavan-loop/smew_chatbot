import json
from collections.abc import AsyncIterator
import uuid
from fastapi import Header

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.llm.tools import TOOLS

from app.llm.openai_client import stream, ToolCallEvent
from app.prompt.system import SYSTEM_PROMPT

router = APIRouter()

class ChatRequest(BaseModel):
  message: str = Field(min_length=1, max_length=500)
  history: list[dict] = Field(default_factory=list)
  lead_captured: bool = False

def sse(payload: dict) -> str:
  return f"data: {json.dumps(payload)}\n\n"

async def event_stream(message: str, history: list[dict], visitor_id: str, lead_captured: bool) -> AsyncIterator[str]:
  yield sse({"type": "visitor", "visitor_id": visitor_id})
  lead_note = ("\n\nNOTE: This Customer has already submitted their contact details this session do not call capture_lead under any circumstances"
  if lead_captured else ""
  )
  recent = history[-20:]

  messages = (
    [{"role": "system", "content": SYSTEM_PROMPT + lead_note}]
    + recent
    + [{"role": "user", "content": message}]
    )
  try:
    async for chunk in stream(messages, tools=TOOLS if not lead_captured else None):
      if isinstance(chunk, ToolCallEvent):
        yield sse({
          "type" : "action",
          "action" : "show_lead_form", 
          "service" : chunk.arguments.get("service"),
          "notes" : chunk.arguments.get("notes"),
        })
      else:
        yield sse({"type": "text", "text": chunk})
  except Exception as e: 
    yield sse({"type": "error", "text": "Something went wrong. Call us at 9986464819."})
  finally:
    yield sse({"type":"done"})

@router.post("/chat")
async def chat(body: ChatRequest, x_visitor_id: str | None = Header(default=None)) -> StreamingResponse:
  visitor_id = x_visitor_id or str(uuid.uuid4())

  return StreamingResponse(
    event_stream(body.message, body.history, visitor_id, body.lead_captured),
    media_type="text/event-stream",
    headers={
      "Cache-Control" : "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering" : "no"
    },
  )