"""Deterministic conversation transitions and conservative output checks."""

import re
from dataclasses import dataclass

from app.models import Extraction, SessionMemory

COPY = {
    "en": {
        "greeting": "Hi! Welcome to SMEW. How can we help with your fabrication work?",
        "failure": "The assistant is temporarily unavailable. You can call or WhatsApp Prashanth at 9986464819.",
        "saved": "Thanks, your callback request is saved. Prashanth will review the details and confirm his availability.",
        "price": "The price depends on size, material and design; the site visit is free, with a quote after the visit.",
        "service": "What would you like made or repaired—gates, window grills, railings, or something else?",
        "size": "Do you happen to know the approximate size? It's fine if you haven't measured it yet.",
        "design": "Have you picked a design or reference photo, or is that still undecided?",
        "location": "Which area is your place in?",
        "consent": "Would you like to share your contact number so Prashanth can discuss the work with you?",
        "time": "What's a convenient time for Prashanth to call you?",
        "form": "Whenever you're ready, share your number using the form below. Prashanth will confirm when he's available to call.",
        "declined": "No problem at all. You can call or WhatsApp Prashanth at 9986464819 whenever you're ready.",
        "out_of_area": "SMEW serves Mysuru and nearby areas only. We cannot arrange work in that location.",
        "uncertain_area": "Prashanth can confirm whether your area is covered. Please contact him at 9986464819.",
        "ack": "You're welcome! Happy to help.",
        "help": "For specific requirements, you can contact Prashanth at 9986464819.",
        "closing": "You're welcome to message us again whenever you need help. Take care!",
        "pending_ack": "You're welcome! If you'd like a callback, share your number and consent in the form above whenever you're ready.",
        "memory": "I can use details from this chat, but I can't identify you across separate chats or devices.",
        "remembered": "In this chat, you mentioned {details}. I can't identify you across separate chats or devices.",
        "suggestion": "That's completely fine—you don't need a design ready. Prashanth can discuss suitable options with you during the site visit.",
        "house": "Of course, we can help with the fabrication for your house.",
        "unknown_size": "No worries—we can take the measurements during the site visit.",
        "location_city": "Which city is the work in—Mysuru or another city?",
        "coverage_pending": "Prashanth can check whether we cover your area before we plan a visit.",
        "skylight_review": "Prashanth will need to review the skylight requirement before confirming whether we can take it up.",
    },
    "kn": {
        "greeting": "ನಮಸ್ಕಾರ! SMEW ಗೆ ಸ್ವಾಗತ. ನಿಮಗೆ ಯಾವ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದ ಬಗ್ಗೆ ಸಹಾಯ ಬೇಕು?",
        "failure": "ಈಗ ಸಹಾಯಕ ಲಭ್ಯವಿಲ್ಲ. ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಕರೆ ಅಥವಾ WhatsApp ಮಾಡಬಹುದು.",
        "saved": "ನಿಮ್ಮ ಕರೆ ವಿನಂತಿಯನ್ನು ಉಳಿಸಲಾಗಿದೆ. ಪ್ರಶಾಂತ್ ಅವರು ನಿಮ್ಮ ವಿಚಾರಣೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಕರೆ ಸಮಯವನ್ನು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "price": "ಬೆಲೆ ಗಾತ್ರ, ಮೆಟೀರಿಯಲ್ ಮತ್ತು ವಿನ್ಯಾಸವನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ. ಸ್ಥಳ ಪರಿಶೀಲನೆ ಉಚಿತ; ಅದರ ನಂತರ ಕೊಟೇಶನ್ ನೀಡಲಾಗುತ್ತದೆ.",
        "service": "ನಿಮಗೆ ಯಾವ ಕೆಲಸ ಅಥವಾ ರಿಪೇರಿ ಬೇಕು—ಗೇಟ್, ಕಿಟಕಿ ಗ್ರಿಲ್, ರೇಲಿಂಗ್ ಅಥವಾ ಬೇರೆ ಕೆಲಸವೇ?",
        "size": "ಅಂದಾಜು ಗಾತ್ರ ಗೊತ್ತಿದೆಯೇ? ಇನ್ನೂ ಅಳತೆ ಮಾಡಿಲ್ಲದಿದ್ದರೂ ಪರವಾಗಿಲ್ಲ.",
        "design": "ವಿನ್ಯಾಸ ಅಥವಾ ಮಾದರಿ ಫೋಟೋ ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಾ, ಅಥವಾ ಇನ್ನೂ ನಿರ್ಧರಿಸಿಲ್ಲವೇ?",
        "location": "ನಿಮ್ಮ ಸ್ಥಳ ಯಾವ ಪ್ರದೇಶದಲ್ಲಿದೆ?",
        "consent": "ಪ್ರಶಾಂತ್ ಅವರು ಕೆಲಸದ ಬಗ್ಗೆ ಸಂಪರ್ಕಿಸಲು ನಿಮ್ಮ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ನೀಡಲು ಒಪ್ಪಿಗೆಯಿದೆಯೇ?",
        "time": "ಪ್ರಶಾಂತ್ ಅವರು ಕರೆ ಮಾಡಲು ನಿಮಗೆ ಯಾವ ಸಮಯ ಅನುಕೂಲ?",
        "form": "ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ಕೆಳಗಿನ ಫಾರ್ಮ್‌ನಲ್ಲಿ ನಿಮ್ಮ ಸಂಖ್ಯೆ ನೀಡಿ. ಕರೆ ಮಾಡಲು ಯಾವಾಗ ಲಭ್ಯವಿದ್ದಾರೆ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "declined": "ಪರವಾಗಿಲ್ಲ. ನಿಮಗೆ ಅನುಕೂಲವಾದಾಗ ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ WhatsApp ಮಾಡಬಹುದು.",
        "out_of_area": "SMEW ಮೈಸೂರು ಮತ್ತು ಹತ್ತಿರದ ಪ್ರದೇಶಗಳಲ್ಲಿ ಮಾತ್ರ ಸೇವೆ ನೀಡುತ್ತದೆ. ಆ ಸ್ಥಳದಲ್ಲಿ ಕೆಲಸ ಮಾಡಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "uncertain_area": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಸೇವೆ ಲಭ್ಯವಿದೆಯೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸಬಹುದು. 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಸಂಪರ್ಕಿಸಿ.",
        "ack": "ಧನ್ಯವಾದಗಳು!",
        "help": "ನಿಮ್ಮ ಕೆಲಸದ ವಿವರಗಳಿಗಾಗಿ ಪ್ರಶಾಂತ್ ಅವರನ್ನು 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಸಂಪರ್ಕಿಸಬಹುದು.",
        "closing": "SMEW ಅನ್ನು ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಸಹಾಯ ಬೇಕಾದಾಗ ಮತ್ತೆ ಇಲ್ಲಿ ಕೇಳಬಹುದು.",
        "pending_ack": "ಧನ್ಯವಾದಗಳು! ಕರೆ ವಿನಂತಿಗಾಗಿ ಮೇಲಿನ ಫಾರ್ಮ್‌ನಲ್ಲಿ ನಿಮ್ಮ ಸಂಖ್ಯೆ ಮತ್ತು ಸಂಪರ್ಕಿಸಲು ಒಪ್ಪಿಗೆ ನೀಡಿ.",
        "memory": "ಈ ಚಾಟ್‌ನ ವಿವರಗಳನ್ನು ಬಳಸಬಹುದು. ಆದರೆ ಬೇರೆ ಚಾಟ್ ಅಥವಾ ಸಾಧನದಲ್ಲಿ ನಿಮ್ಮನ್ನು ಗುರುತಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "remembered": "ಈ ಚಾಟ್‌ನಲ್ಲಿ ನೀವು {details} ಬಗ್ಗೆ ತಿಳಿಸಿದ್ದೀರಿ. ಬೇರೆ ಚಾಟ್ ಅಥವಾ ಸಾಧನದಲ್ಲಿ ನಿಮ್ಮನ್ನು ಗುರುತಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "suggestion": "ಪರವಾಗಿಲ್ಲ, ಈಗಲೇ ವಿನ್ಯಾಸ ಆಯ್ಕೆ ಮಾಡಬೇಕಿಲ್ಲ. ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ವೇಳೆ ಪ್ರಶಾಂತ್ ಅವರು ಸೂಕ್ತ ಆಯ್ಕೆಗಳನ್ನು ತಿಳಿಸಿ ಸಹಾಯ ಮಾಡಬಹುದು.",
        "house": "ಖಂಡಿತ, ನಿಮ್ಮ ಮನೆಯ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದ ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡಬಹುದು.",
        "unknown_size": "ಚಿಂತಿಸಬೇಡಿ—ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ವೇಳೆ ಅಳತೆ ತೆಗೆದುಕೊಳ್ಳಬಹುದು.",
        "location_city": "ಕೆಲಸ ಯಾವ ನಗರದಲ್ಲಿದೆ—ಮೈಸೂರು ಅಥವಾ ಬೇರೆ ನಗರವೇ?",
        "coverage_pending": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಸೇವೆ ನೀಡಬಹುದೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸಬೇಕು.",
        "skylight_review": "ಸ್ಕೈಲೈಟ್ ಕೆಲಸವನ್ನು ಕೈಗೊಳ್ಳಬಹುದೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸಿ ಖಚಿತಪಡಿಸಬೇಕು.",
    },
    "kanglish": {
        "greeting": "Namaskara! SMEW ge swagatha. Nimma fabrication kelasa bagge heli, help madona.",
        "failure": "Iga assistant available illa. Prashanth avarige 9986464819 ge call athava WhatsApp madi.",
        "saved": "Nimma callback request save aagide. Prashanth avaru enquiry nodi call time confirm madtare.",
        "price": "Price size, material mattu design mele depend aagutte. Site visit free; adara nantara quotation kodtare.",
        "service": "Nimage yaava kelasa athava repair beku—gate, window grill, railing athava bere kelasa na?",
        "size": "Approximate size gothideya? Innu measure madillandre parvagilla.",
        "design": "Design athava reference photo choose madiddira, illa innu decide madilva?",
        "location": "Nimma place yaava area alli ide?",
        "consent": "Prashanth avaru kelasa bagge contact madoke nimma contact number share madoke okay na?",
        "time": "Prashanth avaru call madoke yaava time nimage convenient?",
        "form": "Ready aadaga kelagina form alli nimma number share madi. Call madoke Prashanth avaru availability confirm madtare.",
        "declined": "Parvagilla. Ready aadaga Prashanth avarige 9986464819 ge WhatsApp madi.",
        "out_of_area": "SMEW Mysuru mattu hattirada areas alli mathra service kodutte. Aa location alli kelasa madoke aagalla.",
        "uncertain_area": "Nimma area cover aagutta anta Prashanth avaru confirm madtare. 9986464819 ge contact madi.",
        "ack": "Dhanyavadagalu!",
        "help": "Nimma requirement bagge Prashanth avarige 9986464819 ge contact madi.",
        "closing": "SMEW contact madiddakke dhanyavadagalu. Fabrication help bekadaga matte illi keli.",
        "pending_ack": "Dhanyavadagalu! Callback bekandre melina form alli nimma number mattu contact consent kodi.",
        "memory": "Ee chat details use madabahudu. Bere chat athava device alli nimmanu guruthisoke aagalla.",
        "remembered": "Ee chat alli neevu {details} bagge heliddira. Bere chat athava device alli nimmanu guruthisoke aagalla.",
        "suggestion": "Parvagilla, iga design decide madbeku anta illa. Site visit time alli Prashanth avaru suitable options discuss madi help madabahudu.",
        "house": "Khanditha, nimma mane fabrication kelasa bagge help madabahudu.",
        "unknown_size": "Parvagilla—site visit time alli measurements thagobahudu.",
        "location_city": "Kelasa yaava city alli ide—Mysuru athava bere city na?",
        "coverage_pending": "Nimma area cover madabahuda anta Prashanth avaru confirm madabeku.",
        "skylight_review": "Skylight kelasa thagobahuda anta Prashanth avaru requirement nodi confirm madabeku.",
    },
}


def text(language: str, key: str) -> str:
    return COPY.get(language, COPY["en"])[key]


@dataclass
class Plan:
    mode: str
    show_form: bool = False


def short_answer(message: str) -> str:
    return re.sub(r"\s+", " ", message.casefold().strip()).rstrip(" .!,?")


def conversational_reply(memory: SessionMemory, message: str, language: str) -> str | None:
    """Handle exact social replies without advancing enquiry or contact permission."""
    answer = short_answer(message)
    if answer in {
        "do you remember me",
        "remember me",
        "do you remember our conversation",
        "do you remember what i told you",
        "nannannu nenapideya",
        "ನಾನು ನೆನಪಿದ್ದೀನಾ",
    }:
        details = [value for value in (memory.state.service, memory.state.location) if value]
        if details:
            return text(language, "remembered").format(details=", ".join(details))
        return text(language, "memory")
    if answer in {"hi", "hey", "hello", "namaskara", "ನಮಸ್ಕಾರ"}:
        return text(language, "greeting")
    if answer in {
        "nothing",
        "nothing else",
        "that's all",
        "that is all",
        "no more questions",
        "no further questions",
        "bye",
        "goodbye",
        "ashte",
        "bere enu illa",
        "ಅಷ್ಟೇ",
        "ಇನ್ನೇನೂ ಇಲ್ಲ",
    }:
        return text(language, "closing")
    # "No thanks" to a pending consent question must still be a refusal.
    if memory.awaiting not in ("consent", "time") and answer in {
        "thank you",
        "thanks",
        "thanks bro",
        "thank you bro",
        "dhanyavadagalu",
        "ಧನ್ಯವಾದಗಳು",
    }:
        key = "pending_ack" if memory.form_shows and not memory.lead_saved else "ack"
        return text(language, key)
    return None


def design_suggestion(memory: SessionMemory) -> str:
    """Keep the helper compatible while deferring all design advice to the site visit."""
    return text(memory.state.language, "suggestion")


GENERIC_SERVICES = {
    "fabrication",
    "fabrication assistance",
    "fabrication work",
    "steel fabrication",
    "home fabrication",
    "house fabrication",
    "ms fabrication",
    "ss fabrication",
    "custom order",
    "general fabrication",
}


UNKNOWN_ANSWERS = {
    "no",
    "nope",
    "nah",
    "i don't know",
    "i dont know",
    "don't know",
    "dont know",
    "not sure",
    "no idea",
    "i have no idea",
    "not yet",
    "haven't decided",
    "haven't picked one",
    "no design yet",
    "idk",
    "not decided",
    "gothilla",
    "gotilla",
    "illa",
    "ಇಲ್ಲ",
    "ಗೊತ್ತಿಲ್ಲ",
    "ತಿಳಿದಿಲ್ಲ",
}
SHORT_ACKS = {
    "yes",
    "yeah",
    "yep",
    "okay",
    "ok",
    "sure",
    "thanks",
    "thank you",
    "sari",
    "houdu",
    "ಸರಿ",
    "ಹೌದು",
    "ಧನ್ಯವಾದಗಳು",
}
PRICE_INTENT = re.compile(
    r"\b(?:price\w*|cost\w*|estimat\w*|quot(?:e|ation)\w*|rates?|charges?|eshtu)\b|\bhow much\b|ಬೆಲೆ|ವೆಚ್ಚ|ಅಂದಾಜು|ದರ|ಎಷ್ಟು",
    re.I,
)
DESIGN_INTENT = re.compile(r"\b(?:suggest\w*|suggession|recommend\w*)\b|ಸಲಹೆ|ಸೂಚಿಸಿ", re.I)
PRODUCT_WORDS = re.compile(
    r"\b(?:gate\w*|grill\w*|window\w*|railing\w*|balcon\w*|skylight\w*|shutter\w*|door\w*|"
    r"stair\w*|canop\w*|pergola\w*|roof\w*|weld\w*|repair\w*)\b|ಗೇಟ್|ಗ್ರಿಲ್|ಕಿಟಕಿ|ರೇಲಿಂಗ್|ಬಾಲ್ಕನಿ|ಶಟರ್",
    re.I,
)
MYSURU = re.compile(r"\b(?:mysuru|mysore|mysurinali|mysuralli)\b|ಮೈಸೂರು|ಮೈಸೂರಿನಲ್ಲಿ", re.I)
SHARED_AREA = re.compile(r"\b(?:j\.?\s*p\.?\s*nagar|jayanagar|vijayanagar)\b", re.I)


def business_question(message: str) -> bool:
    """Allow factual side questions without turning ordinary slot answers into model prose."""
    question = re.search(r"\?|^(?:what|which|how|why|when|where|can|do|does|is|are)\b", message, re.I)
    topic = re.search(
        r"\b(?:hours?|open\w*|close\w*|materials?|ms|ss|steel|rust|finish\w*|paint\w*|powder|"
        r"gst|invoice\w*|tax|warrant\w*|certif\w*|services?|offer\w*|whatsapp|phone|"
        r"repair\w*|deliver\w*|install\w*|visit\w*|gate\w*|grill\w*|railing\w*|window\w*|skylight\w*)\b|ಮೆಟೀರಿಯಲ್|ಸಮಯ|ಬಣ್ಣ|ಜಿಎಸ್‌ಟಿ",
        message,
        re.I,
    )
    return bool(question and topic)


def normalize_turn(memory: SessionMemory, patch: Extraction, message: str, business: dict) -> Extraction:
    """Keep current-turn acts tied to current text, even if a model echoes old facts."""
    answer = short_answer(message)
    updates = {
        "asks_price": bool(PRICE_INTENT.search(message)),
        "is_ack": answer in SHORT_ACKS and memory.awaiting is None,
        "design_preference": None,
    }
    if re.search(r"\bbuild\w*.{0,20}\bhouse\b", message, re.I):
        updates["purpose"] = "home"
    if business_question(message) and memory.awaiting == "consent":
        updates["contact_consent"] = None
    if patch.purpose == "home" and not re.search(r"\b(?:house|home|mane)\b|ಮನೆ", message, re.I):
        updates["purpose"] = None
    if patch.purpose == "commercial" and not re.search(
        r"\b(?:commercial|shop|office|warehouse|factory)\b|ಅಂಗಡಿ|ಕಚೇರಿ", message, re.I
    ):
        updates["purpose"] = None
    negative_design = re.search(r"(?:no|not|don't|do not).{0,15}(?:suggest|recommend)", message, re.I)
    if DESIGN_INTENT.search(message) and not negative_design and not answer.startswith("thanks for"):
        updates["design_preference"] = "recommend"
    elif memory.awaiting == "design" and answer in UNKNOWN_ANSWERS:
        updates["design_preference"] = "recommend"
    elif memory.awaiting == "design" and answer in {"yes", "yeah", "yep", "i have one", "ಹೌದು", "houdu"}:
        updates["design_preference"] = "own"
    elif patch.design_preference == "own" and re.search(
        r"design|reference|photo|sketch|pinterest|ವಿನ್ಯಾಸ|ಫೋಟೋ", message, re.I
    ):
        updates["design_preference"] = "own"
    # Short answers, measurements and place names cannot silently change the product list.
    if memory.state.service and not PRODUCT_WORDS.search(message):
        updates["service"] = None
    if answer in UNKNOWN_ANSWERS and memory.awaiting == "size":
        updates["size"] = "To be measured during the site visit"
    if answer in UNKNOWN_ANSWERS or answer in SHORT_ACKS:
        updates["location"] = None
        updates["area_status"] = None
    elif patch.location is None:
        updates["area_status"] = None
    # Never infer Bengaluru from "JP Nagar" alone. The customer must identify the city.
    excluded = next(
        (
            city
            for city in business["not_served"]
            if re.search(r"\b" + re.escape(city) + r"\b", message, re.I)
        ),
        None,
    )
    is_place_answer = memory.awaiting in ("location", "location_city")
    if not business_question(message):
        if excluded:
            updates.update(location=message.strip(), area_status="unserved")
        elif MYSURU.search(message) and (is_place_answer or patch.location):
            previous = memory.state.location
            location = patch.location or "Mysuru"
            if memory.awaiting == "location_city" and previous and not MYSURU.search(previous):
                location = previous + ", Mysuru"
            updates.update(location=location, area_status="served")
        elif SHARED_AREA.search(message):
            area = SHARED_AREA.search(message).group(0)
            if memory.state.location and MYSURU.search(memory.state.location):
                updates.update(location=area + ", Mysuru", area_status="served")
            else:
                updates.update(location=area, area_status="uncertain")
    if memory.awaiting == "location_city" and answer in UNKNOWN_ANSWERS:
        # The owner may review an uncertain enquiry; this does not confirm service coverage.
        memory.asked["location_city"] = 2
    if memory.awaiting == "location" and answer in UNKNOWN_ANSWERS:
        updates.update(location="Not provided", area_status="uncertain")
        memory.asked["location_city"] = 2
    return normalize_consent_reply(memory, patch.model_copy(update=updates), message)


REVIEWED_MODES = {
    "service",
    "size",
    "design",
    "location",
    "location_city",
    "consent",
    "time",
    "form",
    "out_of_area",
    "uncertain_area",
    "declined",
    "ack",
}


def reviewed_reply(
    memory: SessionMemory, patch: Extraction, plan: Plan, message: str, previous_awaiting: str | None
) -> str:
    language = memory.state.language
    parts = []
    if plan.mode not in ("out_of_area", "declined"):
        if patch.asks_price:
            parts.append(text(language, "price"))
        if "skylight" in message.casefold() and patch.service and patch.design_preference != "recommend":
            parts.append(text(language, "skylight_review"))
        if plan.mode == "service" and patch.purpose == "home" and not memory.state.service:
            parts.append(text(language, "house"))
        if previous_awaiting == "size" and short_answer(message) in UNKNOWN_ANSWERS:
            parts.append(text(language, "unknown_size"))
        if (
            patch.design_preference == "recommend"
            and memory.state.service
            and plan.mode not in ("location_city", "uncertain_area", "ack")
        ):
            parts.append(design_suggestion(memory))
        if plan.mode == "consent" and memory.state.area_status == "uncertain":
            parts.append(text(language, "coverage_pending"))
    parts.append(text(language, plan.mode))
    return " ".join(parts)


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
    if patch.service and short_answer(patch.service) in GENERIC_SERVICES:
        patch = patch.model_copy(update={"service": None})
    if memory.state.service and short_answer(memory.state.service) in GENERIC_SERVICES:
        memory.state.service = None
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


def outside_service_area(memory: SessionMemory, business: dict) -> bool:
    location = memory.state.location or ""
    return memory.state.area_status == "unserved" or any(
        re.search(r"\b" + re.escape(city) + r"\b", location, re.I) for city in business["not_served"]
    )


def plan_turn(memory: SessionMemory, patch: Extraction, business: dict) -> Plan:
    state = memory.state
    if outside_service_area(memory, business):
        state.area_status = "unserved"
        memory.awaiting = None
        return Plan("out_of_area")
    if memory.lead_saved:
        return Plan("help")
    if state.contact_consent is False:
        memory.awaiting = None
        return Plan("declined")
    if patch.is_ack and memory.awaiting is None:
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
                state.location = "Not provided"
                state.area_status = "uncertain"
                memory.asked["location_city"] = 2
                continue
        elif asked >= cap:
            if slot == "service":
                # Do not ask for measurements of an unidentified product.
                memory.awaiting = "service"
                return Plan("service")
            continue
        memory.asked[slot] = asked + 1
        memory.asked_turn[slot] = memory.turn
        memory.awaiting = slot
        return Plan(slot)
    if state.area_status != "served" and memory.asked.get("location_city", 0) < 2:
        memory.asked["location_city"] = memory.asked.get("location_city", 0) + 1
        memory.awaiting = "location_city"
        return Plan("location_city")
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
    # Main owns reviewed transitions and questions; this guard checks factual model prose.
    return reply.strip(), True
