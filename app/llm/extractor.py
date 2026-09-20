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
  "design_preference": "own" if they already have a design/reference/photo in mind or a specific look they described, "recommend" if they said they don't have one and want a suggestion (e.g. "you decide", "whatever you recommend", "no idea, suggest something"), else null,
  "asked_price": true ONLY if the LATEST customer message asks about price, cost, rate or estimate,
  "wants_visit": true if at any point they asked for or agreed to a site visit or measurement,
  "agreed_to_quote": true if at any point they agreed to receive a quote,
  "is_ack": true ONLY if the LATEST customer message is a closing acknowledgement with nothing else (thanks, ok noted, fine, cool). A yes / yeah / sure / okay in reply to a question or offer from the assistant is an ANSWER, not an acknowledgement: set is_ack false, and if the assistant had offered a site visit or quote, set wants_visit or agreed_to_quote to true,
  "contact_consent": true or false ONLY if the assistant's LAST message asked permission to take their contact number so someone can get in touch, and the latest customer message clearly answers that specific question (yes/sure/ok = true, no/not now/maybe later = false). If the assistant's last message did not ask that, or the customer's answer is ambiguous, use null,
  "preferred_time": if the assistant's LAST message asked what a good time to call is, the customer's answer as they said it (e.g. "evenings after 6", "tomorrow morning"), else null
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
