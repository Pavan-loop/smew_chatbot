"""Deterministic conversation transitions and conservative output checks."""

import re
from dataclasses import dataclass

from app.models import Extraction, SessionMemory

COPY = {
    "en": {
        "greeting": "Hi! Welcome to SMEW. How can we help with your fabrication work?",
        "failure": "The assistant is temporarily unavailable. You can call or WhatsApp Prashanth at 9986464819.",
        "saved": "Thanks, your callback request is saved. Prashanth will review the details and confirm his availability.",
        "price": "Prices depend on the design, material (MS or SS) and size, so we don't quote a fixed rate in chat. Prashanth offers a free site visit and shares an exact quotation after it, and I can arrange a callback whenever you're ready.",
        "service": "What would you like made or repaired—gates, window grills, railings, or something else?",
        "size": "Do you happen to know the approximate size? It's fine if you haven't measured it yet.",
        "design": "Have you picked a design or reference photo, or is that still undecided?",
        "location": "Which area is the work in?",
        "consent": "Would you like to share your contact number so Prashanth can discuss the work with you?",
        "time": "What's a convenient time for Prashanth to call you?",
        "form": "Whenever you're ready, share your number using the form below. Prashanth will confirm when he's available to call.",
        "declined": "No problem at all. You can call or WhatsApp Prashanth at 9986464819 whenever you're ready.",
        "out_of_area": "Sorry, SMEW only works in Mysuru and nearby areas, so we can't take up work in that location.",
        "uncertain_area": "Prashanth can confirm whether we cover your area. You can reach him at 9986464819.",
        "ack": "You're welcome, happy to help!",
        "help": "Happy to help with anything else. For specific requirements, you can also reach Prashanth at 9986464819.",
        "closing": "You're welcome to message us again whenever you need help. Take care!",
        "pending_ack": "You're welcome! If you'd like a callback, share your number and consent in the form above whenever you're ready.",
        "memory": "I can use details from this chat, but I can't identify you across separate chats or devices.",
        "remembered": "In this chat, you mentioned {details}. I can't identify you across separate chats or devices.",
        "suggestion": "That's completely fine—you don't need a design ready. Prashanth can discuss suitable options with you during the site visit.",
        "house": "Of course, we can help with the fabrication for your house.",
        "package_new": "Congratulations on the new house! We can take care of all the fabrication: gates, window grills, railings, staircase and balcony work, shutters and more.",
        "package": "Great, we can take care of all the fabrication for your home: gates, window grills, railings, staircase and balcony work, shutters and more.",
        "package_confirm": "Got it, we'll plan for all the fabrication work.",
        "visit_offer": "Prashanth can visit the site for free to understand the full scope.",
        "unknown_size": "No worries—we can take the measurements during the site visit.",
        "location_city": "Which city is the work in—Mysuru or another city?",
        "coverage_pending": "Prashanth can check whether we cover your area before we plan a visit.",
        "skylight_review": "Prashanth will need to review the skylight requirement before confirming whether we can take it up.",
        "how_are_you": "I'm doing well, thank you for asking! I hope you're doing well too.",
        "how_are_you_short": "I'm doing well, thanks for asking!",
        "apology": "Sorry if I came across that way! I'm here to help, and you can always call or WhatsApp Prashanth at 9986464819 to talk to a person.",
        "apology_short": "Sorry about that!",
        "frustration": "Sorry about that, I may have missed what you meant. You can also call or WhatsApp Prashanth at 9986464819 anytime.",
        "compliment": "That's very kind of you, thank you!",
        "capabilities": "I can help with gates, grills, railings, shutters and repairs, or answer questions about pricing, location and timings.",
        "price_ranges": "As a rough guide: {ranges}. The final price depends on the design, material and size, and Prashanth confirms it after a free site visit.",
        "recap": "Just to recap: ",
    },
    "kn": {
        "greeting": "ನಮಸ್ಕಾರ! SMEW ಗೆ ಸ್ವಾಗತ. ನಿಮಗೆ ಯಾವ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದ ಬಗ್ಗೆ ಸಹಾಯ ಬೇಕು?",
        "failure": "ಈಗ ಸಹಾಯಕ ಲಭ್ಯವಿಲ್ಲ. ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಕರೆ ಅಥವಾ WhatsApp ಮಾಡಬಹುದು.",
        "saved": "ನಿಮ್ಮ ಕರೆ ವಿನಂತಿಯನ್ನು ಉಳಿಸಲಾಗಿದೆ. ಪ್ರಶಾಂತ್ ಅವರು ನಿಮ್ಮ ವಿಚಾರಣೆಯನ್ನು ಪರಿಶೀಲಿಸಿ ಕರೆ ಸಮಯವನ್ನು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "price": "ಬೆಲೆ ವಿನ್ಯಾಸ, ಮೆಟೀರಿಯಲ್ (MS ಅಥವಾ SS) ಮತ್ತು ಗಾತ್ರವನ್ನು ಅವಲಂಬಿಸಿರುವುದರಿಂದ ಚಾಟ್‌ನಲ್ಲಿ ನಿಗದಿತ ದರ ಹೇಳುವುದಿಲ್ಲ. ಪ್ರಶಾಂತ್ ಅವರು ಉಚಿತವಾಗಿ ಸ್ಥಳ ಪರಿಶೀಲನೆ ಮಾಡಿ ನಂತರ ನಿಖರ ಕೊಟೇಶನ್ ನೀಡುತ್ತಾರೆ; ನೀವು ಸಿದ್ಧರಾದಾಗ ಕರೆ ವ್ಯವಸ್ಥೆ ಮಾಡಬಹುದು.",
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
        "ack": "ಸಹಾಯ ಮಾಡಲು ಸಂತೋಷ!",
        "help": "ನಿಮ್ಮ ಕೆಲಸದ ವಿವರಗಳಿಗಾಗಿ ಪ್ರಶಾಂತ್ ಅವರನ್ನು 9986464819 ಸಂಖ್ಯೆಯಲ್ಲಿ ಸಂಪರ್ಕಿಸಬಹುದು.",
        "closing": "SMEW ಅನ್ನು ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಸಹಾಯ ಬೇಕಾದಾಗ ಮತ್ತೆ ಇಲ್ಲಿ ಕೇಳಬಹುದು.",
        "pending_ack": "ಧನ್ಯವಾದಗಳು! ಕರೆ ವಿನಂತಿಗಾಗಿ ಮೇಲಿನ ಫಾರ್ಮ್‌ನಲ್ಲಿ ನಿಮ್ಮ ಸಂಖ್ಯೆ ಮತ್ತು ಸಂಪರ್ಕಿಸಲು ಒಪ್ಪಿಗೆ ನೀಡಿ.",
        "memory": "ಈ ಚಾಟ್‌ನ ವಿವರಗಳನ್ನು ಬಳಸಬಹುದು. ಆದರೆ ಬೇರೆ ಚಾಟ್ ಅಥವಾ ಸಾಧನದಲ್ಲಿ ನಿಮ್ಮನ್ನು ಗುರುತಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "remembered": "ಈ ಚಾಟ್‌ನಲ್ಲಿ ನೀವು {details} ಬಗ್ಗೆ ತಿಳಿಸಿದ್ದೀರಿ. ಬೇರೆ ಚಾಟ್ ಅಥವಾ ಸಾಧನದಲ್ಲಿ ನಿಮ್ಮನ್ನು ಗುರುತಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.",
        "suggestion": "ಪರವಾಗಿಲ್ಲ, ಈಗಲೇ ವಿನ್ಯಾಸ ಆಯ್ಕೆ ಮಾಡಬೇಕಿಲ್ಲ. ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ವೇಳೆ ಪ್ರಶಾಂತ್ ಅವರು ಸೂಕ್ತ ಆಯ್ಕೆಗಳನ್ನು ತಿಳಿಸಿ ಸಹಾಯ ಮಾಡಬಹುದು.",
        "house": "ಖಂಡಿತ, ನಿಮ್ಮ ಮನೆಯ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದ ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡಬಹುದು.",
        "package_new": "ಹೊಸ ಮನೆಗೆ ಅಭಿನಂದನೆಗಳು! ಗೇಟ್, ಕಿಟಕಿ ಗ್ರಿಲ್, ರೇಲಿಂಗ್, ಮೆಟ್ಟಿಲು ಮತ್ತು ಬಾಲ್ಕನಿ ಕೆಲಸ, ಶಟರ್ ಸೇರಿದಂತೆ ಎಲ್ಲಾ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸವನ್ನು ನಾವು ಮಾಡಬಹುದು.",
        "package": "ಖಂಡಿತ, ಗೇಟ್, ಕಿಟಕಿ ಗ್ರಿಲ್, ರೇಲಿಂಗ್, ಮೆಟ್ಟಿಲು ಮತ್ತು ಬಾಲ್ಕನಿ ಕೆಲಸ, ಶಟರ್ ಸೇರಿದಂತೆ ನಿಮ್ಮ ಮನೆಯ ಎಲ್ಲಾ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸವನ್ನು ನಾವು ಮಾಡಬಹುದು.",
        "package_confirm": "ಸರಿ, ಎಲ್ಲಾ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸವನ್ನು ಗಮನಕ್ಕೆ ತೆಗೆದುಕೊಳ್ಳುತ್ತೇವೆ.",
        "visit_offer": "ಪೂರ್ಣ ಕೆಲಸವನ್ನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ಪ್ರಶಾಂತ್ ಅವರು ಉಚಿತವಾಗಿ ಸ್ಥಳಕ್ಕೆ ಭೇಟಿ ನೀಡಬಹುದು.",
        "unknown_size": "ಚಿಂತಿಸಬೇಡಿ—ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ವೇಳೆ ಅಳತೆ ತೆಗೆದುಕೊಳ್ಳಬಹುದು.",
        "location_city": "ಕೆಲಸ ಯಾವ ನಗರದಲ್ಲಿದೆ—ಮೈಸೂರು ಅಥವಾ ಬೇರೆ ನಗರವೇ?",
        "coverage_pending": "ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಸೇವೆ ನೀಡಬಹುದೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸಬೇಕು.",
        "skylight_review": "ಸ್ಕೈಲೈಟ್ ಕೆಲಸವನ್ನು ಕೈಗೊಳ್ಳಬಹುದೇ ಎಂದು ಪ್ರಶಾಂತ್ ಅವರು ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸಿ ಖಚಿತಪಡಿಸಬೇಕು.",
        "how_are_you": "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ, ಕೇಳಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು! ನೀವೂ ಚೆನ್ನಾಗಿದ್ದೀರಿ ಎಂದು ಭಾವಿಸುತ್ತೇನೆ.",
        "how_are_you_short": "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ, ಧನ್ಯವಾದಗಳು!",
        "apology": "ಕ್ಷಮಿಸಿ, ನನ್ನ ಉತ್ತರ ಹಾಗೆ ಅನ್ನಿಸಿದ್ದರೆ! ನಾನು ಸಹಾಯ ಮಾಡಲು ಇಲ್ಲಿದ್ದೇನೆ. ನೇರವಾಗಿ ಮಾತನಾಡಲು ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಗೆ ಕರೆ ಅಥವಾ WhatsApp ಮಾಡಬಹುದು.",
        "apology_short": "ಕ್ಷಮಿಸಿ!",
        "frustration": "ಕ್ಷಮಿಸಿ, ನಿಮ್ಮ ಮಾತು ನನಗೆ ಸರಿಯಾಗಿ ಅರ್ಥವಾಗದೇ ಇರಬಹುದು. ಯಾವಾಗ ಬೇಕಾದರೂ ಪ್ರಶಾಂತ್ ಅವರಿಗೆ 9986464819 ಗೆ ಕರೆ ಅಥವಾ WhatsApp ಮಾಡಬಹುದು.",
        "compliment": "ನಿಮ್ಮ ಮೆಚ್ಚುಗೆಗೆ ಧನ್ಯವಾದಗಳು!",
        "capabilities": "ಗೇಟ್, ಕಿಟಕಿ ಗ್ರಿಲ್, ರೇಲಿಂಗ್, ರೋಲಿಂಗ್ ಶಟರ್ ಮತ್ತು ರಿಪೇರಿ ಅಥವಾ ವೆಲ್ಡಿಂಗ್ ಕೆಲಸದಲ್ಲಿ ಸಹಾಯ ಮಾಡಬಹುದು; ಬೆಲೆ, ವಿಳಾಸ ಅಥವಾ ಸಮಯದ ಪ್ರಶ್ನೆಗಳಿಗೂ ಉತ್ತರಿಸಬಹುದು.",
        "price_ranges": "ಅಂದಾಜು ಮಾರ್ಗದರ್ಶನಕ್ಕಾಗಿ: {ranges}. ಅಂತಿಮ ಬೆಲೆ ವಿನ್ಯಾಸ, ಮೆಟೀರಿಯಲ್ ಮತ್ತು ಗಾತ್ರವನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ; ಉಚಿತ ಸ್ಥಳ ಪರಿಶೀಲನೆಯ ನಂತರ ಪ್ರಶಾಂತ್ ಅವರು ಖಚಿತಪಡಿಸುತ್ತಾರೆ.",
        "recap": "ಮತ್ತೊಮ್ಮೆ ಹೇಳುವುದಾದರೆ: ",
    },
    "kanglish": {
        "greeting": "Namaskara! SMEW ge swagatha. Nimma fabrication kelasa bagge heli, help madona.",
        "failure": "Iga assistant available illa. Prashanth avarige 9986464819 ge call athava WhatsApp madi.",
        "saved": "Nimma callback request save aagide. Prashanth avaru enquiry nodi call time confirm madtare.",
        "price": "Price design, material (MS athava SS) mattu size mele depend aagutte, adakke chat alli fixed rate heLalla. Prashanth avaru free site visit madi nantara exact quotation kodtare; ready aadaga callback arrange madabahudu.",
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
        "ack": "Help madidakke khushi aaytu!",
        "help": "Nimma requirement bagge Prashanth avarige 9986464819 ge contact madi.",
        "closing": "SMEW contact madiddakke dhanyavadagalu. Fabrication help bekadaga matte illi keli.",
        "pending_ack": "Dhanyavadagalu! Callback bekandre melina form alli nimma number mattu contact consent kodi.",
        "memory": "Ee chat details use madabahudu. Bere chat athava device alli nimmanu guruthisoke aagalla.",
        "remembered": "Ee chat alli neevu {details} bagge heliddira. Bere chat athava device alli nimmanu guruthisoke aagalla.",
        "suggestion": "Parvagilla, iga design decide madbeku anta illa. Site visit time alli Prashanth avaru suitable options discuss madi help madabahudu.",
        "house": "Khanditha, nimma mane fabrication kelasa bagge help madabahudu.",
        "package_new": "Hosa mane ge congratulations! Gate, window grill, railing, staircase mattu balcony kelasa, shutter ellavannu naavu madabahudu.",
        "package": "Khanditha, gate, window grill, railing, staircase mattu balcony kelasa, shutter seri nimma mane fabrication ella naavu madabahudu.",
        "package_confirm": "Sari, ella fabrication kelasa plan madtivi.",
        "visit_offer": "Full scope artha madkoloke Prashanth avaru free aagi site visit madabahudu.",
        "unknown_size": "Parvagilla—site visit time alli measurements thagobahudu.",
        "location_city": "Kelasa yaava city alli ide—Mysuru athava bere city na?",
        "coverage_pending": "Nimma area cover madabahuda anta Prashanth avaru confirm madabeku.",
        "skylight_review": "Skylight kelasa thagobahuda anta Prashanth avaru requirement nodi confirm madabeku.",
        "how_are_you": "Naanu chennagiddini, kelidakke thanks! Neevu kooda chennagiddira anta andkotini.",
        "how_are_you_short": "Naanu chennagiddini, thanks!",
        "apology": "Sorry, nanna reply haage anisidre! Naanu help madoke idini. Direct aagi matadbekandre Prashanth avarige 9986464819 ge call athava WhatsApp madi.",
        "apology_short": "Sorry!",
        "frustration": "Sorry, neevu heLiddu nanage sariyagi artha aagirlikilla. Yavaga bekadru Prashanth avarige 9986464819 ge call athava WhatsApp madi.",
        "compliment": "Thumba thanks, nimma maatige!",
        "capabilities": "Gate, window grill, railing, rolling shutter mattu repair athava welding kelasakke help madabahudu; price, location athava timings bagge questions ge kooda answer madabahudu.",
        "price_ranges": "Rough aagi: {ranges}. Final price design, material mattu size mele depend aagutte; free site visit nantara Prashanth avaru confirm madtare.",
        "recap": "Matte heLbekandre: ",
    },
}


def text(language: str, key: str) -> str:
    return COPY.get(language, COPY["en"])[key]


# Alternative phrasings so the bot never sends the same steering question twice in a row.
VARIANTS = {
    "en": {
        "greeting": ["Hello again! What can I help you with today?"],
        "invite": [
            "What can I help you with today: a gate, window grills, railings or a repair?",
            "Is there some fabrication work I can help you with?",
            "What are you planning to get made or fixed?",
        ],
        "service": [
            "Which work do you have in mind: a gate, grills, railings, shutters or a repair?",
            "What can we make or fix for you?",
        ],
        "location": ["Where is the site, which area?", "Could you tell me which area the work is in?"],
        "location_city": ["Just to check, which city is that in: Mysuru or somewhere else?"],
        "consent": ["Shall Prashanth give you a call about this?"],
        "help": ["Glad to help with anything else. You can also reach Prashanth directly at 9986464819."],
        "ack": ["Glad I could help!"],
    },
    "kn": {
        "greeting": ["ಮತ್ತೆ ನಮಸ್ಕಾರ! ಇಂದು ಯಾವ ಸಹಾಯ ಬೇಕು?"],
        "invite": [
            "ಇಂದು ಯಾವ ಕೆಲಸದಲ್ಲಿ ಸಹಾಯ ಬೇಕು—ಗೇಟ್, ಕಿಟಕಿ ಗ್ರಿಲ್, ರೇಲಿಂಗ್ ಅಥವಾ ರಿಪೇರಿ?",
            "ಯಾವುದಾದರೂ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದಲ್ಲಿ ಸಹಾಯ ಮಾಡಲೇ?",
        ],
        "service": ["ಯಾವ ಕೆಲಸ ಮಾಡಿಸಬೇಕು ಅಥವಾ ರಿಪೇರಿ ಮಾಡಬೇಕು ಎಂದು ತಿಳಿಸುತ್ತೀರಾ?"],
        "location": ["ಕೆಲಸ ಯಾವ ಪ್ರದೇಶದಲ್ಲಿದೆ ಎಂದು ತಿಳಿಸುತ್ತೀರಾ?"],
        "location_city": ["ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಲು, ಅದು ಯಾವ ನಗರದಲ್ಲಿದೆ—ಮೈಸೂರು ಅಥವಾ ಬೇರೆ ಊರೇ?"],
        "consent": ["ಈ ಕೆಲಸದ ಬಗ್ಗೆ ಪ್ರಶಾಂತ್ ಅವರು ನಿಮಗೆ ಕರೆ ಮಾಡಲೇ?"],
        "help": ["ಬೇರೆ ಏನಾದರೂ ಸಹಾಯ ಬೇಕಾದರೆ ಕೇಳಿ. ಪ್ರಶಾಂತ್ ಅವರನ್ನು 9986464819 ಗೆ ನೇರವಾಗಿ ಸಂಪರ್ಕಿಸಬಹುದು."],
        "ack": ["ಸಂತೋಷ!"],
    },
    "kanglish": {
        "greeting": ["Matte namaskara! Ivattu enu help beku?"],
        "invite": [
            "Ivattu yaava kelasakke help beku—gate, window grill, railing athava repair?",
            "Yavudadru fabrication kelasakke help madla?",
        ],
        "service": ["Yaava kelasa madisbeku athava repair madbeku anta heLtira?"],
        "location": ["Kelasa yaava area alli ide anta heLtira?"],
        "location_city": ["Confirm madkoloke, adu yaava city—Mysuru na athava bere ooru na?"],
        "consent": ["Ee kelasa bagge Prashanth avaru nimage call madla?"],
        "help": [
            "Bere enadru help beku andre keli. Prashanth avarige 9986464819 ge direct contact madabahudu."
        ],
        "ack": ["Khushi aaytu!"],
    },
}


def say(language: str, key: str, last: str = "", seed: int = 0) -> str:
    """Pick a phrasing for `key`, rotating by `seed` and never reusing one from the previous reply."""
    options = [text(language, key)] if key in COPY["en"] else []
    options += VARIANTS.get(language, VARIANTS["en"]).get(key, [])
    start = seed % len(options)
    rotated = options[start:] + options[:start]
    return next((option for option in rotated if option not in last), rotated[0])


@dataclass
class Plan:
    mode: str
    show_form: bool = False


def short_answer(message: str) -> str:
    return re.sub(r"\s+", " ", message.casefold().strip()).rstrip(" .!,?")


def conversational_reply(memory: SessionMemory, message: str, language: str, last: str = "") -> str | None:
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
    if GREETING_ONLY.fullmatch(answer):
        return say(language, "greeting", last)
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
        return say(language, key, last)
    return social_reply(memory, message, language, last)


GREETING = (
    r"(?:hi+|hey+|hello+|helo|hai|hiya|namaskara|namaste|good (?:morning|afternoon|evening)|ನಮಸ್ಕಾರ)"
    r"(?: there| bro| sir| madam| team| smew)?"
)
GREETING_ONLY = re.compile(GREETING)
HOW_ARE_YOU = (
    r"(?:how (?:are|r) (?:you|u)(?: doing)?(?: today)?|how(?:'s| is) it going|how do you do|hru|"
    r"what'?s up|wassup|hope you(?:'re| are) (?:well|good|fine|doing well)|hegiddira|hegidira|hegidiya|"
    r"chennagiddira|ಹೇಗಿದ್ದೀರಾ|ಹೇಗಿದ್ದೀರಿ|ಚೆನ್ನಾಗಿದ್ದೀರಾ)"
)
SOCIAL_TAIL = r"(?:[\s,!.]*(?:bro|sir|madam|buddy|friend|dear|ji))?"
HOW_ARE_YOU_ONLY = re.compile(rf"(?:{GREETING}[\s,!.]*)?{HOW_ARE_YOU}{SOCIAL_TAIL}")
HOW_ARE_YOU_START = re.compile(rf"^(?:{GREETING}[\s,!.]*)?{HOW_ARE_YOU}\b")
ADDRESS_BOT = (
    r"(?:you(?:'re| are| r)?|u(?: r)?|ur|youre|this (?:bot|chat|assistant|thing)|"
    r"your (?:bot|reply|replies|answers?|service)|neevu|nivu|neenu)"
)
INSULT = (
    r"(?:rude|rood|roode|ruud|rud|useless|usless|stupid|stupd|dumb|idiot\w*|bad|worst|annoying|irritating|"
    r"hopeless|pathetic|rubbish|unhelpful|not (?:helpful|useful|good)|no use|waste|nonsense|horrible|"
    r"terrible|bekar|bakwas)"
)
RUDE = re.compile(
    rf"\b{ADDRESS_BOT}\s+(?:(?:is|are|was|so|very|really|such an?|being|kind of|a bit|too|a|an)\s+)*{INSULT}\b"
    rf"|^(?:{INSULT}|shut up|stfu|waste of time)(?:\s+(?:bot|assistant))?$|\bshut up\b|ಅಸಭ್ಯ|ಪ್ರಯೋಜನವಿಲ್ಲ"
)
FRUSTRATED = re.compile(
    r"not listening|\byou (?:don'?t|do not|didn'?t|did not) (?:understand|get it|listen|answer)|"
    r"(?:not|never) answer(?:ing|ed)? (?:my|the) question|answer my question|\bi (?:already|just) (?:told|said|asked)|"
    r"same (?:question|thing) again|stop asking|why (?:do|are) you (?:keep )?(?:asking|repeating)|"
    r"you keep (?:asking|repeating)|this is (?:not working|frustrating|confusing)|\bfrustrat\w*|"
    r"artha aagilla|ಅರ್ಥ ಆಗಿಲ್ಲ"
)
PRAISE = r"(?:great|helpful|awesome|nice|good|amazing|super|cool|brilliant|excellent|wonderful|perfect|sweet)"
COMPLIMENT = re.compile(
    rf"(?:(?:you(?:'re| are| r)|u r|ur|this is|that'?s|that is|its|it's)\s+(?:so |very |really )?{PRAISE}"
    rf"(?:\s+(?:bot|job|work|website|service|assistant|help))?|{PRAISE} (?:bot|job|work|website|service|assistant)"
    rf"|well done|love (?:it|this)|thumbs up)(?:[\s,!.]*(?:thanks?|thank you))?{SOCIAL_TAIL}"
)


def social_kind(message: str) -> str | None:
    """Classify small talk: how-are-you, rudeness, frustration or a compliment."""
    answer = short_answer(message).replace("’", "'")
    if HOW_ARE_YOU_ONLY.fullmatch(answer):
        return "how_are_you"
    if RUDE.search(answer):
        return "apology"
    if FRUSTRATED.search(answer):
        return "frustration"
    if COMPLIMENT.fullmatch(answer):
        return "compliment"
    return None


def has_request(message: str) -> bool:
    return bool(
        PRODUCT_WORDS.search(message) or PRICE_INTENT.search(message) or business_info_intent(message)
    )


def social_reply(memory: SessionMemory, message: str, language: str, last: str = "") -> str | None:
    """Answer pure small talk warmly, then steer gently without changing the enquiry state."""
    kind = social_kind(message)
    if kind is None or (kind != "how_are_you" and has_request(message)):
        return None
    if kind in ("apology", "frustration"):
        # Someone unhappy gets an apology and what we can do, not another question.
        return text(language, kind) + " " + text(language, "capabilities")
    pending = memory.awaiting if memory.awaiting in VARIANTS["en"] else None
    steer = say(language, pending or "invite", last, memory.turn)
    return text(language, kind) + " " + steer


def social_prefix(message: str, language: str) -> str:
    """A short warm opener when small talk is mixed with a real request."""
    answer = short_answer(message).replace("’", "'")
    if HOW_ARE_YOU_START.search(answer):
        return text(language, "how_are_you_short") + " "
    if RUDE.search(answer) or FRUSTRATED.search(answer):
        return text(language, "apology_short") + " "
    return ""


def price_answer(language: str, business: dict | None) -> str:
    """Pricing help backed only by business.json: ranges if listed there, otherwise the free-visit policy."""
    ranges = (business or {}).get("price_ranges") or []
    if ranges:
        return text(language, "price_ranges").format(ranges="; ".join(str(r) for r in ranges))
    return text(language, "price")


# Generic closers that make replies sound robotic; the server adds the one real follow-up itself.
BOILERPLATE = re.compile(
    r"let me know if|feel free to (?:ask|reach out|contact)|if you (?:have|need) any (?:other |more |further )?"
    r"(?:questions|help|assistance)|i'?m here to help|hope (?:this|that) helps|is there anything else|"
    r"any further assistance",
    re.I,
)


def polish_answer(answer: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    return " ".join(s for s in sentences if not BOILERPLATE.search(s)).strip()


def design_suggestion(memory: SessionMemory) -> str:
    """Keep the helper compatible while deferring all design advice to the site visit."""
    return text(memory.state.language, "suggestion")


# Leadership roles a customer may ask about; without a listed CEO the owner is the answer.
HEAD_ROLE = (
    r"(?:ceo|boss|head|proprietor|propreitor|managing director|md|chairman|director|in[- ]?charge|"
    r"person in charge|malika|maalika)"
)
COMPANY = r"(?:smew|you|your company|the company|this company|your shop|the shop|your business)"
# Who/what the customer is asking about when they ask what the business does.
SUBJECT = r"(?:you|your (?:company|team|firm|shop|business|workshop)|smew|the company)"
SERVICE_VERB = (
    r"(?:do|make|build|offer|provide|fabricate|sell|work on|deal (?:in|with)|take up|handle|"
    r"speciali[sz]e in)"
)

BUSINESS_INFO_PATTERNS = {
    "ceo": [
        rf"who(?: is|'s) (?:the |your |smew's )?{HEAD_ROLE}(?: here)?(?: of {COMPANY})?",
        rf"(?:what is |what's )?(?:your |the )?{HEAD_ROLE}(?:'s)? name",
        rf"(?:nimma )?{HEAD_ROLE} (?:yaaru|ಯಾರು)",
        rf"who runs {COMPANY}|who is in charge(?: here)?",
    ],
    "owner": [
        rf"who(?: is|'s) (?:the |your )?owner(?: of {COMPANY})?",
        r"who owns (?:smew|this company|your company|the company|you)",
        r"(?:nimma )?owner (?:yaaru|ಯಾರು)",
        r"(?:ಕಂಪನಿಯ )?ಮಾಲೀಕರು ಯಾರು",
    ],
    "founder": [
        rf"who(?: is|'s) (?:the |your )?founder(?: of {COMPANY})?",
        r"who (?:founded|started) (?:smew|your company|the company|you)",
        r"(?:nimma )?founder (?:yaaru|ಯಾರು)",
        r"(?:ಕಂಪನಿಯ )?ಸ್ಥಾಪಕರು ಯಾರು",
    ],
    "services": [
        rf"what (?:all )?(?:do|does|can) {SUBJECT} {SERVICE_VERB}"
        r"(?: exactly| here| there| actually| again| for customers)?",
        rf"what (?:kinds?|types?|sorts?) of (?:work|services?|things|stuff|jobs|products|fabrication(?: work)?) "
        rf"(?:do|does|can) {SUBJECT} {SERVICE_VERB}",
        rf"(?:what|which) (?:services|work|products) (?:do|does|can) {SUBJECT} (?:offer|provide|do|make)",
        r"(?:what|which) services (?:are )?(?:available|offered)",
        r"what(?: is|'s) (?:your|smew's) (?:business|work|line of work|speciali[sz]ation|speciality|specialty)",
        r"what (?:are|r) (?:your|smew's) services",
        rf"tell me (?:about your services|what {SUBJECT} (?:do|does))",
        r"nimma (?:services|kelasa) (?:enu|yenu)",
        r"neevu (?:enu|yenu) madtira",
        r"ನೀವು (?:ಏನು|ಯಾವ ಕೆಲಸ) ಮಾಡುತ್ತೀರಿ",
        r"ನಿಮ್ಮ ಸೇವೆಗಳು ಯಾವುವು",
    ],
    "identity": [
        r"who are you",
        r"(?:what is|what's) smew",
        r"tell me about (?:smew|your company|the company)",
        r"neevu yaaru",
        r"ನೀವು ಯಾರು",
    ],
}
# Conversational lead-ins ("okay", "so", "hmm", "and") that do not change the question.
FILLER = re.compile(
    r"^(?:(?:ok(?:ay)?|okie|k|so|hmm+|hm+|and|well|also|then|alright|all right|right|cool|great|nice|"
    r"oh|ah|uh|um+|hey|hi|hello|please|pls|plz|can you|could you|can u)\b[\s,.!-]*)+"
)
TRAILING_FILLER = re.compile(r"(?:[\s,]+(?:please|pls|bro|sir|madam|then))+$")
# "you guys", "u", "ur" etc. all address the business.
ADDRESSEE = re.compile(r"\b(?:you guys|u guys|you people|you all|y'?all|ya'll|u)\b")


def business_text(message: str) -> str:
    """Normalise a customer question for FAQ matching (case, filler words, ways of saying 'you')."""
    answer = short_answer(message).replace("’", "'")
    answer = FILLER.sub("", answer)
    answer = TRAILING_FILLER.sub("", answer).rstrip(" .!,?")
    answer = ADDRESSEE.sub("you", answer)
    return re.sub(r"\bur\b", "your", answer)


BUSINESS_INFO_COPY = {
    "en": {
        "owner": "{owner} is the owner of {name}.",
        "founder": "{founder} founded {name}.",
        "ceo": "{ceo} is the CEO of {name}.",
        "identity": "I'm the customer assistant for {name}. I can help with questions about our fabrication work and callback enquiries.",
        "services": "We help with fabrication work, including {services}.",
        "unknown": "I don't have confirmed information about that. Prashanth can help clarify it.",
    },
    "kn": {
        "owner": "{name} ಸಂಸ್ಥೆಯ ಮಾಲೀಕರು {owner}.",
        "founder": "{name} ಸಂಸ್ಥೆಯನ್ನು {founder} ಸ್ಥಾಪಿಸಿದರು.",
        "ceo": "{name} ಸಂಸ್ಥೆಯ CEO {ceo}.",
        "identity": "ನಾನು {name} ಸಂಸ್ಥೆಯ ಗ್ರಾಹಕ ಸಹಾಯಕ. ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸದ ಪ್ರಶ್ನೆಗಳು ಮತ್ತು ಕರೆ ವಿನಂತಿಗಳ ಬಗ್ಗೆ ಸಹಾಯ ಮಾಡಬಹುದು.",
        "services": "{services} ಸೇರಿದಂತೆ ಫ್ಯಾಬ್ರಿಕೇಶನ್ ಕೆಲಸಗಳಲ್ಲಿ ಸಹಾಯ ಮಾಡುತ್ತೇವೆ.",
        "unknown": "ಅದರ ಬಗ್ಗೆ ಖಚಿತ ಮಾಹಿತಿ ನನ್ನ ಬಳಿ ಇಲ್ಲ. ಪ್ರಶಾಂತ್ ಅವರಿಂದ ತಿಳಿದುಕೊಳ್ಳಬಹುದು.",
    },
    "kanglish": {
        "owner": "{name} owner {owner} avaru.",
        "founder": "{name} start madidavaru {founder} avaru.",
        "ceo": "{name} CEO {ceo} avaru.",
        "identity": "Naanu {name} customer assistant. Fabrication kelasa bagge questions mattu callback enquiries ge help madabahudu.",
        "services": "{services} seridanthe fabrication kelasa madutteve.",
        "unknown": "Adara bagge confirmed information nanna hatra illa. Prashanth avaru clarify madabahudu.",
    },
}

# Translate only service names that actually exist in the trusted business facts.
SERVICE_LABELS = {
    "Main gates (MS and SS)": ("gates", "ಗೇಟ್‌ಗಳು", "gates"),
    "Window grills": ("window grills", "ಕಿಟಕಿ ಗ್ರಿಲ್‌ಗಳು", "window grills"),
    "Staircase railings": ("staircase railings", "ಮೆಟ್ಟಿಲಿನ ರೇಲಿಂಗ್‌ಗಳು", "staircase railings"),
    "Rolling shutters (manual and motorised)": ("rolling shutters", "ರೋಲಿಂಗ್ ಶಟರ್‌ಗಳು", "rolling shutters"),
    "Repairs and welding": ("repairs and welding", "ರಿಪೇರಿ ಮತ್ತು ವೆಲ್ಡಿಂಗ್", "repair mattu welding"),
}


def business_info_intent(message: str) -> str | None:
    """Recognise standalone FAQs; mixed questions/enquiries still reach the provider."""
    answer = business_text(message)
    return next(
        (
            intent
            for intent, patterns in BUSINESS_INFO_PATTERNS.items()
            if any(re.fullmatch(pattern, answer) for pattern in patterns)
        ),
        None,
    )


def business_info_reply(message: str, language: str, business: dict) -> str | None:
    """Answer common FAQs without changing facts, consent or the pending enquiry step."""
    intent = business_info_intent(message)
    if intent is None:
        return None
    copy = BUSINESS_INFO_COPY.get(language, BUSINESS_INFO_COPY["en"])
    name = business.get("name") or business.get("short_name")
    if not name:
        return copy["unknown"]
    if intent == "ceo" and not business.get("ceo"):
        # A family workshop has no CEO: the owner is the answer to CEO/boss/head questions.
        intent = "owner"
    if intent in ("owner", "founder", "ceo"):
        if not business.get(intent):
            return copy["unknown"]
        return copy[intent].format(**{intent: business[intent], "name": name})
    if intent == "identity":
        return copy["identity"].format(name=name)
    column = {"en": 0, "kn": 1, "kanglish": 2}.get(language, 0)
    services = business.get("services", [])
    labels = [words[column] for service, words in SERVICE_LABELS.items() if service in services]
    if not labels:
        labels = [str(service) for service in services[:5]]
    return copy["services"].format(services=", ".join(labels)) if labels else copy["unknown"]


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
    r"\b(?:pric\w*|cost\w*|estimat\w*|quot(?:e|ation)\w*|rates?|charges?|budget\w*|afford\w*|expensive|"
    r"cheap\w*|eshtu|bele)\b|\bhow much\b|ಬೆಲೆ|ವೆಚ್ಚ|ಅಂದಾಜು|ದರ|ಎಷ್ಟು",
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
OPT_IN = re.compile(
    r"\b(?:call\s+me|contact\s+me|call\s*back|ring\s+me|please\s+call|you\s+can\s+call|"
    r"take\s+my\s+number|share\s+my\s+number|call\s+madi|contact\s+madi)\b|ಕರೆ\s*ಮಾಡಿ",
    re.I,
)
OPT_OUT = re.compile(
    r"\b(?:don'?t|do\s+not|never|no\s+need\s+to)\b.{0,20}\b(?:call|contact)|\b(?:call|contact)\w*\s+beda\b|ಬೇಡ",
    re.I,
)


INFO_WORDS = (
    r"(?:services?|materials?|contact(?:\s+(?:details|info|number))?|hours|timings?|address|location|"
    r"phone(?:\s+number)?|whatsapp)"
)
# Bare topic requests such as the widget's chips ("Our services", "Contact and hours").
BARE_INFO = re.compile(
    rf"(?:(?:your|our|the|namma|nimma|yaava|which)\s+)?{INFO_WORDS}(?:\s+(?:used|offered|available|details))?"
    rf"(?:\s+(?:and|&|mattu)\s+{INFO_WORDS})?",
    re.I,
)
KN_INFO_CHIPS = {"ನಮ್ಮ ಸೇವೆಗಳು", "ಬಳಸುವ ಮೆಟೀರಿಯಲ್", "ಸಂಪರ್ಕ ಮತ್ತು ಸಮಯ"}
QUESTION = re.compile(
    r"\?|^(?:who|what|which|how|why|when|where|can|could|do|does|is|are|will|tell me|yaava|yelli|yavaga|hege|enu)\b"
    r"|ಎಲ್ಲಿ|ಯಾವ|ಏನು|ಹೇಗೆ|ಯಾವಾಗ",
    re.I,
)
INFO_TOPIC = re.compile(
    r"\b(?:hours?|open\w*|close\w*|timings?|sunday|weekends?|address|locat\w*|shop|workshop|showroom|"
    r"contact\w*|number|materials?|ms|ss|steel|rust|finish\w*|paint\w*|powder|"
    r"gst|invoice\w*|tax|warrant\w*|certif\w*|services?|offer\w*|whatsapp|phone|experience|"
    r"ceo|owner|founder|company|"
    r"repair\w*|deliver\w*|install\w*|visit\w*|gate\w*|grill\w*|railing\w*|window\w*|skylight\w*)\b"
    r"|ಮೆಟೀರಿಯಲ್|ಸಮಯ|ಬಣ್ಣ|ಜಿಎಸ್‌ಟಿ|ಸೇವೆ|ವಿಳಾಸ|ಸಂಪರ್ಕ|ಅಂಗಡಿ",
    re.I,
)

# "So what kind of stuff do you guys make?": asking what the business itself does.
ABOUT_BUSINESS = re.compile(
    rf"\b(?:what|which|kinds?|types?|sorts?)\b.{{0,40}}\b{SUBJECT}\b.{{0,25}}\b"
    rf"(?:{SERVICE_VERB}|does|speciali[sz]\w*)\b"
)


def business_question(message: str) -> bool:
    """Allow factual side questions without turning ordinary slot answers into model prose."""
    if business_info_intent(message):
        return True
    answer = short_answer(message)
    if answer in KN_INFO_CHIPS or BARE_INFO.fullmatch(answer):
        return True
    normalized = business_text(message)
    if not (QUESTION.search(message) or QUESTION.search(normalized)):
        return False
    # "Where ...?" asked of the assistant is about the workshop's location.
    return bool(
        re.match(r"\s*(?:where|yelli)\b", normalized)
        or INFO_TOPIC.search(message)
        or ABOUT_BUSINESS.search(normalized)
    )


# A new house or "all the work" is one project: the full fabrication package, not a single product.
HOUSE_PACKAGE = "Complete house fabrication (gates, grills, railings, etc.)"
NEW_BUILD = re.compile(
    r"\b(?:build\w*|construct\w*|new)\b.{0,20}\b(?:house|home|mane|villa|bungalow)\b|"
    r"\b(?:new construction|hosa mane)\b|ಹೊಸ ಮನೆ|ಮನೆ ಕಟ್ಟ",
    re.I,
)
FULL_PACKAGE = re.compile(
    r"\b(?:everything|all (?:the )?(?:work|works|of it|of them|fabrication(?: work)?|items|things)|"
    r"full (?:house|home|package|work)|whole (?:house|home|work)|complete (?:work|house|home|package|job|fabrication)|"
    r"entire (?:house|home|work)|sab(?: kuch)?|sabhi|ella(?:nu|vannu| kelasa| kelsa)?)\b|^all$|ಎಲ್ಲಾ|ಎಲ್ಲವೂ|ಎಲ್ಲ ಕೆಲಸ",
    re.I,
)


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
    new_build = bool(NEW_BUILD.search(message))
    if new_build:
        updates["purpose"] = "home"
        memory.asked["new_build"] = 1
    home = new_build or memory.state.purpose == "home" or patch.purpose == "home"
    wants_all = FULL_PACKAGE.search(answer) and (home or memory.awaiting == "service")
    if not memory.state.service and not PRODUCT_WORDS.search(message) and (new_build or wants_all):
        # The whole house's fabrication is measured and designed at the free site visit.
        updates.update(service=HOUSE_PACKAGE, size="To be measured during the site visit")
        memory.asked.update(size=1, design=1)
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
    if memory.awaiting != "consent":
        # Outside the consent question, only an explicit opt-back-in after a refusal changes consent.
        opted_in = (
            memory.state.contact_consent is False
            and (patch.shares_phone or OPT_IN.search(message))
            and not OPT_OUT.search(message)
        )
        updates["contact_consent"] = True if opted_in else None
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


FACT_FIELDS = ("service", "purpose", "material", "size", "design_preference", "location", "preferred_time")


def understood(patch: Extraction) -> bool:
    """Did this turn give us anything to act on?"""
    return bool(
        any(getattr(patch, key) is not None for key in FACT_FIELDS)
        or patch.is_ack
        or patch.asks_price
        or patch.shares_phone
        or patch.contact_consent is not None
    )


def reviewed_reply(
    memory: SessionMemory,
    patch: Extraction,
    plan: Plan,
    message: str,
    previous_awaiting: str | None,
    last: str = "",
    business: dict | None = None,
    answered: bool = False,
) -> str:
    language = memory.state.language
    parts = []
    if plan.mode not in ("out_of_area", "declined"):
        if patch.asks_price:
            parts.append(price_answer(language, business))
        elif plan.mode in ("service", "help") and not answered and not understood(patch):
            # Rather than repeating the bare question, say what we can help with.
            parts.append(text(language, "capabilities"))
        if "skylight" in message.casefold() and patch.service and patch.design_preference != "recommend":
            parts.append(text(language, "skylight_review"))
        package = memory.state.service == HOUSE_PACKAGE
        if package and not memory.asked.get("package_ack"):
            memory.asked["package_ack"] = 1
            parts.append(text(language, "package_new" if memory.asked.get("new_build") else "package"))
        elif package and FULL_PACKAGE.search(short_answer(message)) and not patch.asks_price:
            parts.append(text(language, "package_confirm"))
        elif plan.mode == "service" and patch.purpose == "home" and not memory.asked.get("house_ack"):
            # Acknowledge the house once; re-deriving it from later "home" mentions made it repeat.
            memory.asked["house_ack"] = 1
            parts.append(text(language, "house"))
        if package and plan.mode == "consent" and not memory.asked.get("visit_offer"):
            memory.asked["visit_offer"] = 1
            parts.append(text(language, "visit_offer"))
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
    # At most one question per reply: an answer that already asks something gets no extra question.
    if not any(part.rstrip().endswith("?") for part in parts):
        parts.append(say(language, plan.mode, last, memory.turn))
    return dedupe_sentences(" ".join(parts), last)


def dedupe_sentences(reply: str, last: str = "") -> str:
    """Drop repeated sentences and statements already made in the previous reply (questions are kept)."""
    seen = set(re.split(r"(?<=[.!?])\s+", last.strip())) if last else set()
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", reply.strip()):
        if sentence in kept or (sentence in seen and not sentence.endswith("?")):
            continue
        kept.append(sentence)
    return " ".join(kept) or reply


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
    if answer in accepted or (patch.shares_phone and not OPT_OUT.search(message)):
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
    elif memory.state.contact_consent is False and patch.contact_consent is True:
        # An explicit opt-back-in (see normalize_turn) resumes the callback flow after a refusal.
        memory.state.contact_consent = True
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
        declined_now = memory.awaiting == "consent"
        memory.awaiting = None
        if declined_now:
            return Plan("declined")
        # After a refusal, keep answering normally; an opt-back-in clears it in merge().
        return Plan("ack") if patch.is_ack else Plan("help")
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


def validated_reply(
    reply: str, memory: SessionMemory, plan: Plan, business: dict | None = None
) -> tuple[str, bool]:
    # Price ranges published in business.json may be quoted verbatim; any other number is still blocked.
    checked = reply
    for sanctioned in (business or {}).get("price_ranges") or []:
        checked = checked.replace(str(sanctioned), "")
    if (
        not reply.strip()
        or len(reply) > 1800
        or CURRENCY_RE.search(checked)
        or RATE_RE.search(checked)
        or PRICE_RE.search(checked)
        or PROMISE_RE.search(checked)
    ):
        return text(memory.state.language, "price") + " " + text(memory.state.language, plan.mode), False
    # Main owns reviewed transitions and questions; this guard checks factual model prose.
    return reply.strip(), True
