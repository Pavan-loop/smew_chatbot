"""Deterministic conversation transitions and conservative output checks."""

import re
from dataclasses import dataclass

from app.models import Extraction, SessionMemory

COPY = {
    "en": {
        "greeting": "Hello! Ask us about gates, grills, railings or other steel fabrication in Mysuru.",
        "failure": "The assistant is temporarily unavailable. You can call or WhatsApp Prashanth at 9986464819.",
        "saved": "Your callback request is saved. Prashanth will review your enquiry; the callback time will be confirmed by him.",
        "price": "The price depends on size, material and design. The site visit is free, and the quote is shared after it.",
        "service": "What would you like made or repaired?",
        "size": "Do you know the approximate size? If not, it can be measured during the site visit.",
        "design": "Do you have a design or reference, or would you like a suggestion?",
        "location": "Which area is the work in?",
        "consent": "May we collect your contact number so Prashanth can get in touch about this enquiry?",
        "time": "What is a convenient time to call you?",
        "form": "You can submit your callback request using the form below. Prashanth will confirm availability.",
        "declined": "That's fine. You can reach Prashanth on WhatsApp at 9986464819 whenever you're ready.",
        "out_of_area": "SMEW serves Mysuru and nearby areas only. We cannot arrange work in that location.",
        "uncertain_area": "Prashanth can confirm whether your area is covered. Please contact him at 9986464819.",
        "ack": "You're welcome!",
        "help": "For specific requirements, you can contact Prashanth at 9986464819.",
    },
    "kn": {
        "greeting": "ನಮಸ್ಕಾರ! ಮೈಸೂರಿನಲ್ಲಿ ಗೇಟ್, ಗ್ರಿಲ್, ರೇಲಿಂಗ್ ಅಥವಾ ಇತರ ಸ್ಟೀಲ್ ಕೆಲಸಗಳ ಬಗ್ಗೆ ಕೇಳಬಹುದು.",
        "failure": "ಈಗ ಸಹಾಯಕ ಲಭ್ಯವಿಲ್ಲ. ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಕರೆ ಅಥವಾ WhatsApp ಮಾಡಬಹುದು.",
        "saved": "ನಿಮ್ಮ ಕರೆ ವಿನಂತಿಯನ್ನು ಉಳಿಸಲಾಗಿದೆ. ಪ್ರಶಾಂತ್ ಅವರು ನಿಮ್ಮ ವಿಚಾರಣೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಕರೆ ಸಮಯವನ್ನು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "price": "ಬೆಲೆ ಗಾತ್ರ, ಮೆಟೀರಿಯಲ್ ಮತ್ತು ವಿನ್ಯಾಸವನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ. ಸ್ಥಳ ಪರಿಶೀಲನೆ ಉಚಿತ; ಅದರ ನಂತರ ಕೊಟೇಶನ್ ನೀಡಲಾಗುತ್ತದೆ.",
        "service": "ನಿಮಗೆ ಯಾವ ಕೆಲಸ ಅಥವಾ ರಿಪೇರಿ ಬೇಕು?",
        "size": "ಅಂದಾಜು ಗಾತ್ರ ಗೊತ್ತಿದೆಯೇ? ಗೊತ್ತಿಲ್ಲದಿದ್ದರೆ ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ವೇಳೆ ಅಳತೆ ಮಾಡಬಹುದು.",
        "design": "ನಿಮ್ಮ ಬಳಿ ವಿನ್ಯಾಸ ಅಥವಾ ಫೋಟೋ ಇದೆಯೇ, ಅಥವಾ ಸಲಹೆ ಬೇಕೇ?",
        "location": "ಕೆಲಸ ಯಾವ ಪ್ರದೇಶದಲ್ಲಿದೆ?",
        "consent": "ಈ ವಿಚಾರಣೆಯ ಬಗ್ಗೆ ಪ್ರಶಾಂತ್ ಅವರು ಸಂಪರ್ಕಿಸಲು ನಿಮ್ಮ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಪಡೆಯಬಹುದೇ?",
        "time": "ನಿಮಗೆ ಕರೆ ಮಾಡಲು ಯಾವ ಸಮಯ ಅನುಕೂಲ?",
        "form": "ಕೆಳಗಿನ ಫಾರ್ಮ್ ಮೂಲಕ ಕರೆ ವಿನಂತಿಯನ್ನು ಸಲ್ಲಿಸಬಹುದು. ಪ್ರಶಾಂತ್ ಅವರು ಲಭ್ಯತೆಯನ್ನು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "declined": "ಪರವಾಗಿಲ್ಲ. ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ WhatsApp ಮಾಡಬಹುದು.",
        "out_of_area": "SMEW ಮೈಸೂರು ಮತ್ತು ಹತ್ತಿರದ ಪ್ರದೇಶಗಳಲ್ಲಿ ಮಾತ್ರ ಸೇವೆ ನೀಡುತ್ತದೆ. ಆ ಸ್ಥಳದಲ್ಲಿ ಕೆಲಸ ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "uncertain_area": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಸೇವೆ ಲಭ್ಯವಿದೆಯೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸಬಹುದು. 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಸಂಪರ್ಕಿಸಿ.",
        "ack": "ಧನ್ಯವಾದಗಳು!",
        "help": "ನಿಮ್ಮ ಕೆಲಸದ ವಿವರಗಳಿಗಾಗಿ ಪ್ರಶಾಂತ್ ಅವರನ್ನು 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಸಂಪರ್ಕಿಸಬಹುದು.",
    },
    "kanglish": {
        "greeting": "Namaskara! Mysurinali gate, grill, railing athava bere steel kelasa bagge kelabahudu.",
        "failure": "Iga assistant available illa. Prashanth avarige 9986464819 ge call athava WhatsApp madi.",
        "saved": "Nimma callback request save aagide. Prashanth avaru enquiry nodi call time confirm madtare.",
        "price": "Price size, material mattu design mele depend aagutte. Site visit free; adara nantara quotation kodtare.",
        "service": "Nimage yaava kelasa athava repair beku?",
        "size": "Approximate size gothideya? Gothillandre site visit time alli measure madabahudu.",
        "design": "Nimma hatra design athava photo ideya, illa suggestion beka?",
        "location": "Kelasa yaava area alli ide?",
        "consent": "Ee enquiry bagge Prashanth avaru contact madoke nimma mobile number thagobahuda?",
        "time": "Nimage call madoke yaava time convenient?",
        "form": "Kelagina form alli callback request submit madi. Prashanth avaru availability confirm madtare.",
        "declined": "Parvagilla. Ready aadaga Prashanth avarige 9986464819 ge WhatsApp madi.",
        "out_of_area": "SMEW Mysuru mattu hattirada areas alli mathra service kodutte. Aa location alli kelasa madoke aagalla.",
        "uncertain_area": "Nimma area cover aagutta anta Prashanth avaru confirm madtare. 9986464819 ge contact madi.",
        "ack": "Dhanyavadagalu!",
        "help": "Nimma requirement bagge Prashanth avarige 9986464819 ge contact madi.",
    },
}


def text(language: str, key: str) -> str:
    return COPY.get(language, COPY["en"])[key]


@dataclass
class Plan:
    mode: str
    show_form: bool = False


def normalize_consent_reply(memory: SessionMemory, patch: Extraction, message: str) -> Extraction:
    """Resolve clear short answers only to the pending contact-permission question."""
    if memory.awaiting != "consent":
        return patch
    answer = re.sub(r"\s+", " ", message.casefold().strip()).rstrip(" .!,")
    accepted = {
        "yes",
        "yes please",
        "yes, please",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "go ahead",
        "please do",
        "houdu",
        "howdu",
        "haudu",
        "sari",
        "ಹೌದು",
        "ಸರಿ",
    }
    declined = {
        "no",
        "no thanks",
        "no, thanks",
        "no thank you",
        "no, thank you",
        "not now",
        "don't contact me",
        "do not contact me",
        "beda",
        "illa",
        "ಬೇಡ",
        "ಇಲ್ಲ",
    }
    if answer in accepted:
        return patch.model_copy(update={"contact_consent": True, "is_ack": False})
    if answer in declined:
        return patch.model_copy(update={"contact_consent": False, "is_ack": False})
    return patch


def merge(memory: SessionMemory, patch: Extraction, requested_language: str):
    previous_service = memory.state.service
    # A changed product invalidates its size/design, not the customer's location.
    if patch.service and previous_service and patch.service.lower() != previous_service.lower():
        memory.state.size = None
        memory.state.design_preference = None
        memory.state.material = None
        for slot in ("size", "design"):
            memory.asked.pop(slot, None)
    for key in (
        "service",
        "purpose",
        "material",
        "size",
        "design_preference",
        "location",
        "timeline",
        "preferred_time",
    ):
        value = getattr(patch, key)
        if value is not None:
            setattr(memory.state, key, value)
    if patch.location is not None:
        # A new uncertain location must invalidate an old 'served' determination.
        memory.state.area_status = patch.area_status or "uncertain"
    elif patch.area_status:
        memory.state.area_status = patch.area_status
    # Consent can only be interpreted in response to the server's actual question.
    if memory.awaiting == "consent" and patch.contact_consent is not None:
        memory.state.contact_consent = patch.contact_consent
    memory.state.language = (
        "kn" if patch.language == "kn" else "kanglish" if patch.language == "kanglish" else requested_language
    )


def plan_turn(memory: SessionMemory, patch: Extraction, business: dict) -> Plan:
    state = memory.state
    location = (state.location or "").lower()
    denied = any(re.search(r"\b" + re.escape(c.lower()) + r"\b", location) for c in business["not_served"])
    if denied or state.area_status == "unserved":
        memory.awaiting = None
        return Plan("out_of_area")
    if memory.lead_saved:
        return Plan("help")
    if state.contact_consent is False:
        memory.awaiting = None
        return Plan("declined")
    if patch.is_ack and memory.awaiting not in ("consent", "time"):
        return Plan("ack")
    for slot, attr, cap in (
        ("service", "service", 2),
        ("size", "size", 1),
        ("design", "design_preference", 1),
        ("location", "location", 3),
    ):
        if getattr(state, attr):
            continue
        asked = memory.asked.get(slot, 0)
        if slot == "location":
            if asked >= cap:
                return Plan("uncertain_area")
            if asked and memory.turn - memory.asked_turn.get(slot, -100) < 2:
                return Plan("help")
        elif asked >= cap:
            continue
        memory.asked[slot] = asked + 1
        memory.asked_turn[slot] = memory.turn
        memory.awaiting = slot
        return Plan(slot)
    if state.area_status != "served":
        return Plan("uncertain_area")
    if state.contact_consent is None:
        memory.awaiting = "consent"
        return Plan("consent")
    # This persisted consent survives the preferred-time response and restarts.
    if not state.preferred_time and memory.awaiting != "time":
        memory.awaiting = "time"
        return Plan("time")
    # Time is optional: a vague/skipped answer must not strand an accepted lead.
    memory.awaiting = None
    if memory.form_shows < 2 and (not memory.form_shows or memory.turn - memory.last_form_turn >= 4):
        memory.form_shows += 1
        memory.last_form_turn = memory.turn
        return Plan("form", True)
    return Plan("help")


CURRENCY_RE = re.compile(r"₹|\$|\b(?:rs\.?|inr|usd|rupees?|roopayi|rupayi)\b|ರೂಪಾಯಿ|ರೂ\.", re.I)
RATE_RE = re.compile(
    r"\d[\d,.]*\s*(?:/-|per\s*(?:foot|feet|sq|kg|ton)|/\s*(?:ft|kg|sqft))|(?:price|cost|charge|estimate).{0,40}\b(?:hundred|thousand|lakh|million)\b",
    re.I,
)
PRICE_RE = re.compile(
    r"(?:₹|\$|\b(?:rs\.?|inr|usd|rupees?)\b)\s*\d|\d[\d,.]*\s*(?:rupees?|ರೂಪಾಯಿ|ರೂ\.?|rs\b|inr\b)|(?:cost|price|rate|estimate)\s*(?:is|:|of|around|approximately)?\s*\d",
    re.I,
)
PROMISE_RE = re.compile(
    r"(?:deliver(?:ed|y)?|install(?:ed|ation)?|ready|complete(?:d)?)\s+(?:\w+\s+){0,4}(?:tomorrow|\d+\s*(?:days?|weeks?))|\d+\s*ದಿನಗಳಲ್ಲಿ",
    re.I,
)


def validated_reply(reply: str, memory: SessionMemory, plan: Plan) -> tuple[str, bool]:
    if (
        not reply.strip()
        or len(reply) > 1800
        or CURRENCY_RE.search(reply)
        or RATE_RE.search(reply)
        or PRICE_RE.search(reply)
        or PROMISE_RE.search(reply)
    ):
        return text(memory.state.language, "price") + " " + text(memory.state.language, plan.mode), False
    # Lead collection questions, consent, booking promises and area refusals use
    # reviewed templates. LLM prose cannot override these state transitions.
    if plan.mode in ("consent", "time", "form", "out_of_area", "uncertain_area", "declined"):
        return text(memory.state.language, plan.mode), True
    return reply.strip(), True
