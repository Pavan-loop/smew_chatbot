import time
import uuid
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.store import LeadRecord, store

router = APIRouter()


class LeadRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    name: str | None = None
    service: str | None = None
    notes: str | None = None
    visitor_id: str | None = None


def format_message(lead: LeadRequest) -> str:
    lines = ["🔥 New Lead — SMEW"]
    lines.append(f"📞 {lead.phone}" + (f" · {lead.name}" if lead.name else ""))
    if lead.service:
        lines.append(f"🔧 {lead.service}")
    if lead.notes:
        lines.append(f"📝 {lead.notes}")
    return "\n".join(lines)


async def send_telegram(message: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_chat_id, "text": message},
            )
            return resp.status_code == 200
    except Exception:
        return False


@router.post("/lead")
async def submit_lead(body: LeadRequest):
    message = format_message(body)
    sent = await send_telegram(message)

    store.record_lead(
        id=str(uuid.uuid4())[:8],
        ts=time.time(),
        visitor_id=body.visitor_id or "unknown",
        phone=body.phone,
        name=body.name,
        service=body.service,
        notes=body.notes,
        telegram_sent=sent,
    )

    return {"ok": True, "notified": sent}