"""Regression tests for the review fixes (rate-limit IPs, lead gating, info chips, opt-back-in, FAQs).

Runs the real FastAPI app with a scripted fake LLM provider. Can live in smew-bot/tests/.
"""

import json
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from app.brain import (
    BUSINESS_INFO_COPY,
    COPY,
    PRICE_INTENT,
    VARIANTS,
    Plan,
    business_info_intent,
    business_question,
    polish_answer,
    price_answer,
    social_kind,
    validated_reply,
)
from app.config import Settings
from app.main import create_app
from app.models import Extraction, SessionMemory
from app.providers import REPLY_PROMPT
from app.security import client_ip, redact_phones

pytestmark = pytest.mark.asyncio

ADMIN = "a" * 40
LLM_ANSWER = "Here is the answer from the business facts."
BASE = dict(
    service=None,
    purpose=None,
    material=None,
    size=None,
    design_preference=None,
    location=None,
    area_status=None,
    timeline=None,
    preferred_time=None,
    contact_consent=None,
    language="en",
    is_ack=False,
    asks_price=False,
    shares_phone=False,
)
FACTS = {
    "I need a main gate for my house": dict(service="main gate", purpose="home"),
    "about 12 x 6 feet": dict(size="12 x 6 feet"),
    "I have a design": dict(design_preference="own"),
    "Kuvempunagar, Mysuru": dict(location="Kuvempunagar, Mysuru", area_status="served"),
    "no thanks": dict(contact_consent=False),
    "evening after 6": dict(preferred_time="evening after 6"),
    # What the real extractor returned in the live new-house conversation.
    "yea i'm building a house": dict(purpose="home"),
    "i want a estimation on all work at home": dict(purpose="home", asks_price=True),
    "I need some fabrication for my home": dict(purpose="home"),
}
TO_CONSENT = [
    "I need a main gate for my house",
    "about 12 x 6 feet",
    "I have a design",
    "Kuvempunagar, Mysuru",
]


class FakeProvider:
    replies = 0
    answer = LLM_ANSWER
    seen: list[str] = []  # every message and history entry the "LLM" was sent

    async def extract(self, history, message, memory, business):
        FakeProvider.seen += [message] + [m["content"] for m in history]
        return Extraction(**(BASE | FACTS.get(message, {}))), {}

    async def reply(self, history, message, memory, move, business):
        FakeProvider.replies += 1
        FakeProvider.seen += [message] + [m["content"] for m in history]
        return FakeProvider.answer, {}


@asynccontextmanager
async def client(**overrides):
    settings = Settings(
        environment="test",
        database_path=Path(tempfile.mkdtemp()) / "db.sqlite3",
        worker_enabled=False,
        session_secret="s" * 40,
        admin_token=ADMIN,
        **overrides,
    )
    app = create_app(settings, provider=FakeProvider())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def new_session(c, ip="203.0.113.1"):
    r = await c.post("/api/session", headers={"x-real-ip": ip})
    assert r.status_code == 200, r.text
    return {"authorization": "Bearer " + r.json()["session_token"], "x-real-ip": ip}


async def chat(c, auth, message):
    r = await c.post("/api/chat", json={"message": message, "request_id": str(uuid.uuid4())}, headers=auth)
    assert r.status_code == 200, r.text
    events = [json.loads(line[6:]) for line in r.text.split("\n\n") if line.startswith("data: ")]
    text = " ".join(e["text"] for e in events if e["type"] in ("text", "error"))
    return text, any(e.get("action") == "show_lead_form" for e in events)


async def lead(c, auth, phone="9876543210"):
    body = {"request_id": str(uuid.uuid4()), "phone": phone, "consent": True}
    return await c.post("/api/lead", json=body, headers=auth)


# 1. Client IP and admin lockout -------------------------------------------------------------


def make_request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1)})


async def test_client_ip_resolution():
    assert client_ip(make_request({"X-Real-IP": "198.51.100.7"}), "x-real-ip") == "198.51.100.7"
    assert client_ip(make_request({"X-Real-IP": "not-an-ip"}), "x-real-ip") == "10.0.0.1"
    xff = {"X-Forwarded-For": "198.51.100.9, 100.64.0.2"}
    assert client_ip(make_request(xff), "x-real-ip") == "10.0.0.1"
    assert client_ip(make_request(xff), "x-real-ip", trust_forwarded_for=True) == "198.51.100.9"
    assert client_ip(make_request({"X-Real-IP": "198.51.100.7"}), "") == "10.0.0.1"


async def test_rate_limits_are_per_visitor_not_per_proxy():
    async with client() as c:
        for _ in range(10):
            assert (await c.post("/api/session", headers={"x-real-ip": "203.0.113.1"})).status_code == 200
        assert (await c.post("/api/session", headers={"x-real-ip": "203.0.113.1"})).status_code == 429
        # Same proxy socket peer, different visitor: unaffected.
        assert (await c.post("/api/session", headers={"x-real-ip": "203.0.113.2"})).status_code == 200


async def test_failed_admin_attempts_cannot_lock_out_valid_token():
    async with client() as c:
        codes = [
            (
                await c.get("/api/admin/summary", headers={"authorization": "Bearer wrong", "x-real-ip": ip})
            ).status_code
            for ip in ["203.0.113.66"] * 15
        ]
        assert codes[0] == 401 and codes[-1] == 429
        for ip in ("203.0.113.66", "203.0.113.5"):
            ok = await c.get(
                "/api/admin/summary", headers={"authorization": "Bearer " + ADMIN, "x-real-ip": ip}
            )
            assert ok.status_code == 200


# 2. Lead gating ------------------------------------------------------------------------------


async def test_lead_requires_form_step_and_is_limited():
    async with client() as c:
        auth = await new_session(c)
        r = await lead(c, auth)
        assert r.status_code == 409 and "callback form" in r.json()["detail"]
        for message in TO_CONSENT:
            await chat(c, auth, message)
        await chat(c, auth, "yes")  # consent
        _, form = await chat(c, auth, "evening after 6")
        assert form
        assert (await lead(c, auth)).status_code == 200
        assert (await lead(c, auth, "9876543211")).status_code == 200
        assert (await lead(c, auth, "9876543212")).status_code == 200
        assert (await lead(c, auth, "9876543213")).status_code == 429  # per-session daily limit


# 3. Info chips -------------------------------------------------------------------------------

INFO_MESSAGES = [
    "Our services",
    "Materials used",
    "Contact and hours",
    "ನಮ್ಮ ಸೇವೆಗಳು",
    "ಬಳಸುವ ಮೆಟೀರಿಯಲ್",
    "ಸಂಪರ್ಕ ಮತ್ತು ಸಮಯ",
    "Namma services",
    "Yaava material",
    "Contact mattu timings",
    "Where is your shop?",
    "What is your address?",
    "Where are you located?",
    "Are you open on Sunday?",
]


@pytest.mark.parametrize("message", INFO_MESSAGES)
async def test_info_requests_get_an_answer_then_the_flow_question(message):
    async with client() as c:
        auth = await new_session(c)
        text, _ = await chat(c, auth, message)
        assert text.startswith(LLM_ANSWER), text


@pytest.mark.parametrize(
    "message",
    ["about 12 x 6 feet", "Kuvempunagar, Mysuru", "yes", "no", "I have a design", "MS", "evening after 6"],
)
async def test_slot_answers_are_not_business_questions(message):
    assert not business_question(message)


# 4. Decline is not sticky ------------------------------------------------------------------


async def test_decline_then_questions_and_opt_back_in():
    async with client() as c:
        auth = await new_session(c)
        for message in TO_CONSENT:
            await chat(c, auth, message)
        text, _ = await chat(c, auth, "no thanks")
        assert text.startswith("No problem at all")
        text, _ = await chat(c, auth, "What materials do you use for gates?")
        assert text == LLM_ANSWER
        text, _ = await chat(c, auth, "Please don't call me, I'll WhatsApp later")
        assert "convenient time" not in text
        text, _ = await chat(c, auth, "Actually yes, please call me")
        assert "convenient time" in text
        _, form = await chat(c, auth, "evening after 6")
        assert form
        assert (await lead(c, auth)).status_code == 200


# 5. Company FAQs (live conversation on patch 3) ---------------------------------------------

OWNER_ANSWER = "Prashanth S is the owner of Shree Manjunatha Engineering Works."
SERVICES_ANSWER = "We help with fabrication work, including"


async def test_live_conversation_ceo_and_services():
    async with client() as c:
        auth = await new_session(c)
        text, _ = await chat(c, auth, "Hey")
        assert text == COPY["en"]["greeting"]
        text, _ = await chat(c, auth, "who is the ceo")
        assert text == OWNER_ANSWER  # the owner is the answer; no "no confirmed CEO" contradiction
        # Previously fell through to the enquiry flow ("What would you like made or repaired...?").
        text, _ = await chat(c, auth, "okay what do you guys do?")
        assert text.startswith(SERVICES_ANSWER), text
        assert COPY["en"]["service"] not in text
        # An earlier FAQ answer must not suppress the next one.
        text, _ = await chat(c, auth, "what do you do?")
        assert SERVICES_ANSWER in text, text


@pytest.mark.parametrize(
    "message",
    [
        "okay what do you guys do?",
        "what do you guys do?",
        "Ok, what do u guys do",
        "so what does your company do?",
        "hmm and what kind of work do you people do?",
        "what all do you make?",
        "What services do you offer?",
    ],
)
async def test_services_questions_with_filler_and_you_guys(message):
    assert business_info_intent(message) == "services"
    assert business_question(message)


@pytest.mark.parametrize(
    "message",
    ["who is the ceo", "Who's the boss?", "who is the head", "who is the proprietor?", "who runs smew"],
)
async def test_leadership_questions_answer_with_owner(message):
    async with client() as c:
        auth = await new_session(c)
        text, _ = await chat(c, auth, message)
        assert text == OWNER_ANSWER
        assert "CEO" not in text


async def test_general_what_do_you_make_question_reaches_answer_path():
    # Not a canned FAQ, but still a question about the business: answer first, then the flow question.
    async with client() as c:
        auth = await new_session(c)
        before = FakeProvider.replies
        text, _ = await chat(c, auth, "okay, what kind of gates do you guys make?")
        assert text.startswith(LLM_ANSWER), text
        assert FakeProvider.replies == before + 1


async def test_ceo_prompt_and_copy_do_not_contradict_owner():
    assert "answer with the listed owner" in REPLY_PROMPT
    assert "confirmed CEO name" not in REPLY_PROMPT
    assert all("ceo_unknown" not in copy for copy in BUSINESS_INFO_COPY.values())


# 6. Polite, friendly and helpful (live conversation) ------------------------------------------

BARE_SERVICE_QUESTION = COPY["en"]["service"]


def last_question(reply: str) -> str:
    questions = [s for s in re.split(r"(?<=[.!?])\s+", reply) if s.endswith("?")]
    return questions[-1] if questions else ""


async def test_live_conversation_is_polite_and_helpful():
    async with client() as c:
        auth = await new_session(c)
        replies = []
        for message in [
            "hey",
            "how are you",
            "you are rood",
            "okay tell me about your pricing range",
            "where are you located",
            "who is the ceo",
        ]:
            replies.append((await chat(c, auth, message))[0])
        hey, how, rude, pricing, where, ceo = replies
        assert hey == COPY["en"]["greeting"]
        assert "doing well" in how and how != BARE_SERVICE_QUESTION
        assert rude.startswith("Sorry") and BARE_SERVICE_QUESTION not in rude
        assert "depend" in pricing and "site visit" in pricing and pricing != BARE_SERVICE_QUESTION
        assert where.startswith(LLM_ANSWER)
        assert ceo == OWNER_ANSWER
        for previous, current in zip(replies, replies[1:]):
            assert previous != current
            assert not last_question(current) or last_question(previous) != last_question(current)


@pytest.mark.parametrize(
    "message, kind",
    [
        ("how are you", "how_are_you"),
        ("Hi, how are you doing today?", "how_are_you"),
        ("how r u", "how_are_you"),
        ("hegiddira", "how_are_you"),
        ("you are rood", "apology"),
        ("you are so rude", "apology"),
        ("this bot is useless", "apology"),
        ("u r stupid", "apology"),
        ("you're not listening", "frustration"),
        ("I already told you", "frustration"),
        ("great job", "compliment"),
        ("you are very helpful, thanks", "compliment"),
        ("I need a gate", None),
        ("my old gate is bad", None),
        ("about 12 x 6 feet", None),
        ("yes", None),
    ],
)
async def test_small_talk_classification(message, kind):
    assert social_kind(message) == kind


async def test_kanglish_small_talk_and_mixed_rudeness():
    async with client() as c:
        auth = await new_session(c)
        r = await c.post(
            "/api/chat",
            json={"message": "hegiddira", "request_id": str(uuid.uuid4()), "language": "kanglish"},
            headers=auth,
        )
        assert COPY["kanglish"]["how_are_you"] in r.text
        text, _ = await chat(c, auth, "you are rude, how much for a gate?")
        assert text.startswith("Sorry about that!") and "depend" in text


@pytest.mark.parametrize(
    "message", ["okay tell me about your pricing range", "what's the budget?", "how much", "your rates?"]
)
async def test_pricing_questions_are_recognised(message):
    assert PRICE_INTENT.search(message)


async def test_price_answers_use_only_business_json_ranges():
    memory, plan = SessionMemory(), Plan("service")
    business = {"price_ranges": ["MS gates: Rs 450-600 per sq ft"]}
    assert "Rs 450-600 per sq ft" in price_answer("en", business)
    assert price_answer("en", {}) == COPY["en"]["price"]
    ok = "MS gates: Rs 450-600 per sq ft, depending on design."
    assert validated_reply(ok, memory, plan, business) == (ok, True)
    assert not validated_reply("SS gates cost Rs 900 per sq ft.", memory, plan, business)[1]
    assert not validated_reply(ok, memory, plan, {})[1]  # not sanctioned without business.json ranges


async def test_model_boilerplate_is_removed_and_unclear_messages_get_help():
    assert polish_answer("We're in Kuppalur. Let me know if you need any further assistance!") == (
        "We're in Kuppalur."
    )
    async with client() as c:
        auth = await new_session(c)
        FakeProvider.answer = (
            "Our workshop is in Kuppalur, Mysuru. Let me know if you need any further assistance!"
        )
        try:
            text, _ = await chat(c, auth, "where are you located")
        finally:
            FakeProvider.answer = LLM_ANSWER
        assert text.startswith("Our workshop is in Kuppalur, Mysuru.") and "Let me know" not in text
        text, _ = await chat(c, auth, "asdfgh")
        assert COPY["en"]["capabilities"] in text
        questions = [last_question(text)]
        for message in ["qwerty", "Where is your shop?", "hmm", "What is your address?"]:
            questions.append(last_question((await chat(c, auth, message))[0]))
        assert all(a != b for a, b in zip(questions, questions[1:])), questions


# 7. Phone numbers typed in chat are redacted ---------------------------------------------------


async def test_phone_numbers_are_masked_before_storage_and_llm():
    assert redact_phones("call me on +91 98765 43210") == ("call me on +XX XXXXX XXX10", True)
    assert redact_phones("is 9986464819 yours?", ("9986464819",)) == ("is 9986464819 yours?", False)
    FakeProvider.seen = []
    async with client() as c:
        auth = await new_session(c)
        for message in TO_CONSENT:
            await chat(c, auth, message)
        text, _ = await chat(c, auth, "sure, my number is 98765 43210")
        assert "convenient time" in text  # typed number still counts as consent / opt-in
        stored = (await c.get("/api/session", headers=auth)).json()["messages"]
        assert any("XXXXX XXX10" in m["content"] for m in stored)
        assert not any("43210" in m["content"] for m in stored)
        _, form = await chat(c, auth, "evening after 6")
        assert form and (await lead(c, auth, "9876543210")).status_code == 200  # lead form unaffected
    assert not any("43210" in m for m in FakeProvider.seen)


async def test_capacity_defaults():
    settings = Settings(environment="test")
    assert settings.max_daily_chat_requests == 2000 and settings.max_concurrent_chats == 10


# 8. New house / "everything" is a full fabrication package --------------------------------------


def sentences(reply: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", reply.strip()) if s]


SERVICE_QUESTIONS = [COPY["en"]["service"], *VARIANTS["en"]["service"]]


async def test_live_new_house_conversation():
    async with client() as c:
        auth = await new_session(c)
        house, _ = await chat(c, auth, "yea i'm building a house")
        estimate, _ = await chat(c, auth, "i want a estimation on all work at home")
        everything, _ = await chat(c, auth, "everything")
        replies = [house, estimate, everything]
        assert house.startswith("Congratulations on the new house!")
        for previous, reply in zip([""] + replies, replies):
            parts = sentences(reply)
            assert len(parts) == len(set(parts)), reply  # no sentence twice
            stale = [p for p in parts if p in sentences(previous) and not p.endswith("?")]
            assert not stale, reply  # no acknowledgement carried over from the previous reply
            assert sum(p.endswith("?") for p in parts) <= 1, reply
            assert not any(q in reply for q in SERVICE_QUESTIONS), reply  # never "pick one item"
        assert "depend" in estimate and COPY["en"]["house"] not in estimate
        assert COPY["en"]["capabilities"] not in everything and "area" in everything
        # The flow continues: location, then the free visit offer with the contact question.
        text, _ = await chat(c, auth, "Kuvempunagar, Mysuru")
        assert COPY["en"]["visit_offer"] in text and text.endswith("?")


@pytest.mark.parametrize(
    "answer",
    [
        "everything",
        "all work",
        "all fabrication work",
        "full house",
        "complete work",
        "whole house",
        "all of it",
        "sab",
        "ella",
        "ಎಲ್ಲಾ",
    ],
)
async def test_everything_is_a_valid_product_answer(answer):
    async with client() as c:
        auth = await new_session(c)
        first, _ = await chat(c, auth, "I need some fabrication for my home")
        assert any(q in first for q in SERVICE_QUESTIONS)  # product not known yet
        text, _ = await chat(c, auth, answer)
        assert COPY["en"]["capabilities"] not in text
        assert not any(q in text for q in SERVICE_QUESTIONS), text  # accepted: flow moved on
        # Size/design are left to the site visit, so the location answer leads to the visit offer.
        text, _ = await chat(c, auth, "Kuvempunagar, Mysuru")
        assert COPY["en"]["visit_offer"] in text
