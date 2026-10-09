"""Regression tests for the review fixes (rate-limit IPs, lead gating, info chips, opt-back-in, FAQs).

Runs the real FastAPI app with a scripted fake LLM provider. Can live in smew-bot/tests/.
"""

import json
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from app.brain import BUSINESS_INFO_COPY, COPY, business_info_intent, business_question
from app.config import Settings
from app.main import create_app
from app.models import Extraction
from app.providers import REPLY_PROMPT
from app.security import client_ip

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
}
TO_CONSENT = [
    "I need a main gate for my house",
    "about 12 x 6 feet",
    "I have a design",
    "Kuvempunagar, Mysuru",
]


class FakeProvider:
    replies = 0

    async def extract(self, history, message, memory, business):
        return Extraction(**(BASE | FACTS.get(message, {}))), {}

    async def reply(self, history, message, memory, move, business):
        FakeProvider.replies += 1
        return LLM_ANSWER, {}


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
        assert text.startswith(SERVICES_ANSWER), text


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
