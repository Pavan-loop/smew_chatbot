import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()

class LeadRequest(BaseModel):
  phone: str = Field(min_length=10, max_length=15)
  name: str | None = None
  service: str | None = None
  notes: str | None = None

def format_message(lead: LeadRequest) -> str:
  lines = ["New Lead - SMEW"]
  lines.append(f"Phone Number: {lead.phone}")
  lines.append(f"Customer name: {lead.name}" if lead.name else "")
  if lead.service:
    lines.append(f"service: {lead.service}")
  if lead.notes:
    lines.append(f"Notes: {lead.notes}")
  return "\n".join(lines)

async def send_telegram(message: str) -> bool: 
  if not settings.telegram_bot_token or not settings.telegram_chat_id:
    return False
  try:
    async with httpx.AsyncClient(timeout=10.0) as client:
      resp = await client.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={
          "chat_id": settings.telegram_chat_id,
          "text": message,
        },
      )
      return resp.status_code == 200
  except Exception:
    return False

@router.post("/lead")
async def submit_lead(body: LeadRequest):
  message = format_message(body)
  sent = await send_telegram(message)
  return {"ok": True, "notified": sent}

