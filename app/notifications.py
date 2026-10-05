import asyncio
import logging
import random
import time

import httpx

from app.config import Settings
from app.database import Database

log = logging.getLogger("smew")


def format_lead(lead: dict) -> str:
    return "\n".join(
        [
            "New callback request — SMEW",
            "Lead ID: " + lead["id"],
            "Phone: " + lead["phone"],
            "Name: " + (lead["name"] or "Not provided"),
            "Details: " + (lead["notes"] or "Not provided"),
            "Preferred language: " + lead["language"],
            "Consent: explicitly accepted in callback form",
            "Call times are customer preferences, not confirmed appointments.",
        ]
    )[:4000]


class NotificationWorker:
    def __init__(self, settings: Settings, database: Database, client: httpx.AsyncClient):
        self.settings, self.database, self.client = settings, database, client
        self.last_tick = 0.0

    async def tick(self):
        self.last_tick = time.time()
        lead = await asyncio.to_thread(self.database.claim_notification)
        if not lead:
            return False
        sent, code, retry = False, "telegram_unavailable", None
        token = self.settings.telegram_bot_token.get_secret_value()
        if not token or not self.settings.telegram_chat_id:
            code = "telegram_not_configured"
        else:
            try:
                response = await self.client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": self.settings.telegram_chat_id, "text": format_lead(lead)},
                    timeout=10,
                )
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("Invalid Telegram response")
                sent = response.status_code == 200 and body.get("ok") is True
                code = "" if sent else f"telegram_http_{response.status_code}"
                raw_retry = body.get("parameters", {}).get("retry_after")
                retry = min(86400, max(0, raw_retry)) if isinstance(raw_retry, (int, float)) else None
            except (httpx.RequestError, ValueError, TypeError):
                code = "telegram_network_or_response"
        delay = max(float(retry or 0), min(3600, 15 * 2 ** min(lead["attempts"], 8)) + random.uniform(0, 5))
        dead = not sent and lead["attempts"] >= self.settings.max_notification_attempts
        await asyncio.to_thread(
            self.database.notification_result,
            lead["id"],
            sent=sent,
            error=code,
            retry_seconds=delay,
            dead=dead,
        )
        if not sent:
            await asyncio.to_thread(self.database.error, code)
            log.warning("notification_delivery_failed code=%s", code)
        return True

    async def run(self):
        cleaned_at = 0.0
        while True:
            try:
                if time.time() - cleaned_at > 3600:
                    await asyncio.to_thread(
                        self.database.cleanup,
                        self.settings.conversation_retention_days,
                        self.settings.lead_retention_days,
                    )
                    cleaned_at = time.time()
                worked = await self.tick()
                await asyncio.sleep(0.1 if worked else self.settings.worker_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never log provider exception strings or Telegram URLs containing tokens.
                log.error("notification_worker_error")
                await asyncio.sleep(self.settings.worker_interval_seconds)
