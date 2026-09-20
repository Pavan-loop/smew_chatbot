"""LLM call #1 per turn: read the chat, return structured facts (never raises)."""

import logging

from app.core.config import settings
from app.core.conversation import ConversationState
from app.llm.openai_client import complete_json

log = logging.getLogger("smew.extractor")

EXTRACTOR_PROMPT = """You read a chat between a CUSTOMER and the assistant of a steel fabrication workshop in Mysuru, India (gates, grills, railings, shutters, etc.). Customers write English, Kanglish (Kannada in English letters) or Kannada script.

Return ONE JSON object and nothing else. Use only what the CUSTOMER said or clearly confirmed. Never guess: use null / false when unknown. Write values in English.

{
  "service": short phrase for what they want made or repaired, e.g. "main gate", "SS staircase railing", or null,
  "purpose": "home" or "commercial" or null,
  "material": "MS" or "SS" only if the customer stated a preference, else null,
  "size": dimensions or rough size as the customer said it, e.g. "10x6 ft", "two-car gate", or null,
  "location": area or town they mentioned, e.g. "Vijayanagar, Mysuru", or null,
  "timeline": when they want it done / a deadline, as said, or null,
  "has_design_reference": true if they mention a photo, design, Pinterest or reference image, else false,
  "asked_price": true ONLY if the LATEST customer message asks about price, cost, rate or estimate,
  "wants_visit": true if at any point they asked for or agreed to a site visit or measurement,
  "agreed_to_quote": true if at any point they agreed to receive a quote,
  "is_ack": true ONLY if the LATEST customer message is nothing but an acknowledgement (ok, thanks, fine, got it, hmm, cool)
}"""


async def extract_state(history: list[dict], message: str) -> tuple[ConversationState, dict]:
    lines = [
        f"{'CUSTOMER' if m['role'] == 'user' else 'ASSISTANT'}: {m['content']}"
        for m in history[-12:]
    ]
    lines.append(f"CUSTOMER (latest message): {message}")
    try:
        data, usage = await complete_json(
            [
                {"role": "system", "content": EXTRACTOR_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ],
            timeout=settings.extractor_timeout_seconds,
        )
        return ConversationState.from_dict(data), usage
    except Exception as exc:  # the bot must still reply if extraction fails
        log.warning("extractor failed: %s", exc)
        return ConversationState(), {}
