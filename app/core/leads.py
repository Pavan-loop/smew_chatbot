"""Lead notification + recording, shared by the form endpoint and chat-typed numbers."""

import time
import uuid

import httpx

from app.core.config import settings
from app.core.store import store


def format_message(phone: str, name: str | None, service: str | None, notes: str | None) -> str:
    lines = ["🔔 New Lead — SMEW"]
    lines.append(f"📞 {phone}" + (f" · {name}" if name else ""))
    if service:
        lines.append(f"🔧 {service}")
    if notes:
        lines.append(f"📝 {notes}")
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


async def save_lead(
    *,
    phone: str,
    name: str | None,
    service: str | None,
    notes: str | None,
    visitor_id: str | None,
) -> bool:
    sent = await send_telegram(format_message(phone, name, service, notes))
    store.record_lead(
        id=str(uuid.uuid4())[:8],
        ts=time.time(),
        visitor_id=visitor_id or "unknown",
        phone=phone,
        name=name,
        service=service,
        notes=notes,
        telegram_sent=sent,
    )
    return sent
