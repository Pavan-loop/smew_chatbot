"""
Conversation brain for the SMEW bot.

The LLM is good at *talking* but bad at *deciding* (when to show the lead form,
which question to ask next). So those decisions live here, in plain Python:

    extractor (LLM, JSON)  ->  ConversationState   what the customer has told us
    make_plan (Python)     ->  Plan                show the form? ask which question?
    system prompt          ->  tells the reply LLM exactly what to do this turn
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# ── what we try to learn about every enquiry ────────────────────────────────
# Order = the order we ask in: service -> size -> design -> location.
# material/timeline are opportunistic only (see MATERIALS/etc. in the system
# prompt) - not part of the hard gate below.
SLOT_ORDER = ["service", "size", "design", "location"]
_SLOT_ATTR = {"service": "service", "size": "size", "design": "design_preference", "location": "location"}
MAX_ASKS = {"service": 2, "size": 1, "design": 1}  # location is handled separately - see LOCATION_* below

# location is a hard gate: nothing downstream (site-visit talk, consent, the
# lead form) may proceed while it's still unknown, and unlike size/design a
# customer who dodges the question (not the same as "I don't know") gets
# re-asked - paced by turn count so the bot doesn't nag every single turn.
LOCATION_MAX_ASKS = 3
LOCATION_REASK_GAP = 2  # min turns between re-asks

NOT_SERVED = (
    "bangalore", "bengaluru", "chikmagalur", "chikkamagaluru",
    "mangalore", "mangaluru", "hassan",
)
REPAIR_WORDS = ("repair", "welding", "weld", "fix")

_NULLISH = {"", "null", "none", "unknown", "n/a", "na", "not specified", "not sure"}


def _s(v: Any, limit: int = 120) -> str | None:
    """Coerce an LLM value into a clean short string or None."""
    if v is None or isinstance(v, (dict, list, bool)):
        return None
    text = str(v).strip()
    if text.lower() in _NULLISH:
        return None
    return text[:limit]


@dataclass
class ConversationState:
    service: str | None = None
    purpose: str | None = None          # home / commercial
    material: str | None = None         # MS / SS (only if the customer stated it, opportunistic)
    size: str | None = None
    design_preference: str | None = None  # "own" (has a photo/reference) or "recommend"
    location: str | None = None
    timeline: str | None = None         # opportunistic only, not part of the hard gate
    has_design_reference: bool = False
    asked_price: bool = False           # latest message asks price/cost/rate
    wants_visit: bool = False
    agreed_to_quote: bool = False
    is_ack: bool = False                # latest message is just "ok/thanks"
    contact_consent: bool | None = None  # None = not answered yet, once asked
    preferred_time: str | None = None    # good time to call, once consent is given

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationState":
        material = (_s(d.get("material")) or "").upper()
        purpose = (_s(d.get("purpose")) or "").lower()
        design_pref = (_s(d.get("design_preference")) or "").lower()
        has_design_reference = d.get("has_design_reference") is True
        if design_pref not in ("own", "recommend"):
            # a mentioned photo/reference implies "own" even if not phrased that way
            design_pref = "own" if has_design_reference else None
        consent = d.get("contact_consent")
        return cls(
            service=_s(d.get("service")),
            purpose=purpose if purpose in ("home", "commercial") else None,
            material=material if material in ("MS", "SS") else None,
            size=_s(d.get("size")),
            design_preference=design_pref,
            location=_s(d.get("location")),
            timeline=_s(d.get("timeline")),
            has_design_reference=has_design_reference,
            asked_price=d.get("asked_price") is True,
            wants_visit=d.get("wants_visit") is True,
            agreed_to_quote=d.get("agreed_to_quote") is True,
            is_ack=d.get("is_ack") is True,
            contact_consent=consent if isinstance(consent, bool) else None,
            preferred_time=_s(d.get("preferred_time")),
        )

    # ── derived ──
    @property
    def out_of_area(self) -> bool:
        loc = (self.location or "").lower()
        return any(city in loc for city in NOT_SERVED)

    @property
    def is_repair(self) -> bool:
        svc = (self.service or "").lower()
        return any(w in svc for w in REPAIR_WORDS)

    def filled(self) -> int:
        return sum(bool(getattr(self, attr)) for attr in _SLOT_ATTR.values())

    def missing(self) -> list[str]:
        return [slot for slot in SLOT_ORDER if not getattr(self, _SLOT_ATTR[slot])]

    def known_lines(self) -> list[str]:
        rows = [
            ("Wants", self.service), ("For", self.purpose),
            ("Material preference", self.material), ("Size", self.size),
            ("Design", self.design_preference), ("Location", self.location),
            ("Timeline", self.timeline), ("Best time to call", self.preferred_time),
        ]
        lines = [f"{k}: {v}" for k, v in rows if v]
        if self.has_design_reference:
            lines.append("Has a photo/design reference")
        return lines

    def summary(self) -> str:
        """One-liner for the Telegram alert / lead notes."""
        return "; ".join(self.known_lines())

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# ── per-visitor memory (form shown? which questions asked?) ─────────────────
@dataclass
class Session:
    form_shows: int = 0
    last_form_turn: int = -99
    asked: dict[str, int] = field(default_factory=dict)
    asked_turn: dict[str, int] = field(default_factory=dict)  # last turn each slot was asked (pacing)
    consent_asked: bool = False
    consent_declined: bool = False
    time_asked: bool = False
    phone_saved: bool = False
    touched: float = field(default_factory=time.time)


_SESSIONS: dict[str, Session] = {}
_SESSION_TTL = 2 * 60 * 60
_SESSION_CAP = 5000


def get_session(visitor_id: str) -> Session:
    now = time.time()
    if len(_SESSIONS) > _SESSION_CAP:
        for vid in [v for v, s in _SESSIONS.items() if now - s.touched > _SESSION_TTL]:
            _SESSIONS.pop(vid, None)
        if len(_SESSIONS) > _SESSION_CAP:  # still too big: drop oldest half
            for vid, _ in sorted(_SESSIONS.items(), key=lambda kv: kv[1].touched)[: _SESSION_CAP // 2]:
                _SESSIONS.pop(vid, None)
    s = _SESSIONS.get(visitor_id)
    if s is None or now - s.touched > _SESSION_TTL:
        s = _SESSIONS[visitor_id] = Session()
    s.touched = now
    return s


# ── the decision ────────────────────────────────────────────────────────────
@dataclass
class Plan:
    # normal | ack | out_of_area | phone_saved | ask_consent | consent_declined | ask_preferred_time
    mode: str = "normal"
    show_form: bool = False
    ask: str | None = None     # slot to ask about this turn
    reason: str = ""           # why (shown in the debug dashboard)


def make_plan(
    state: ConversationState,
    *,
    turn: int,
    session: Session,
    lead_captured: bool,
    form_shown_flag: bool = False,
    phone_saved_now: bool = False,
) -> Plan:
    """
    Decide what the bot does this turn. Pure rules, no LLM.

    Strictly sequential: service -> size -> design -> location, then a
    permission check, then "what's a good time to call", and only then the
    lead form. A customer who types their own phone number mid-chat still
    short-circuits straight to phone_saved (see turn.py) - this gate is only
    for the bot-initiated path.
    """
    if phone_saved_now:
        return Plan(mode="phone_saved", reason="customer typed their number")
    if state.out_of_area:
        return Plan(mode="out_of_area", reason=f"location '{state.location}' not served")
    if state.is_ack and not (state.wants_visit or state.agreed_to_quote):
        return Plan(mode="ack", reason="pure acknowledgement")
    if lead_captured:
        return Plan(reason="lead already captured, just help")
    if session.consent_declined:
        return Plan(reason="customer declined to share contact, just help")

    # Frontend told us a form was already shown but we have no memory of it
    # (e.g. server restarted): treat it as shown one turn ago.
    if form_shown_flag and session.form_shows == 0:
        session.form_shows, session.last_form_turn = 1, turn - 1

    # ── Step 1: the four info slots, in order ──
    for slot in SLOT_ORDER:
        if getattr(state, _SLOT_ATTR[slot]):
            continue

        if slot == "location":
            # hard gate: no promises, no site-visit talk, no lead until this
            # is answered - paced re-asks instead of a one-shot budget, so a
            # dodge doesn't get silently skipped like it used to.
            asked = session.asked.get("location", 0)
            last_turn = session.asked_turn.get("location", -99)
            if asked >= LOCATION_MAX_ASKS:
                return Plan(reason="location still unknown after repeated asks")
            if asked > 0 and turn - last_turn < LOCATION_REASK_GAP:
                return Plan(reason="waiting before re-asking location")
            session.asked["location"] = asked + 1
            session.asked_turn["location"] = turn
            return Plan(ask="location", reason="missing 'location' (hard gate)")

        cap = MAX_ASKS[slot]
        if session.asked.get(slot, 0) < cap:
            session.asked[slot] = session.asked.get(slot, 0) + 1
            return Plan(ask=slot, reason=f"missing '{slot}'")
        # asked as many times as we will: don't push (e.g. size/design "not sure"), move on

    # ── Step 2: ask permission before offering the contact form ──
    if state.contact_consent is None:
        if not session.consent_asked:
            session.consent_asked = True
            return Plan(mode="ask_consent", reason="info complete, asking permission to get contact")
        return Plan(reason="waiting on consent answer")

    if state.contact_consent is False:
        session.consent_declined = True
        return Plan(mode="consent_declined", reason="customer declined to share contact")

    # ── Step 3: consent given - ask for a good time to call ──
    if not state.preferred_time:
        if not session.time_asked:
            session.time_asked = True
            return Plan(mode="ask_preferred_time", reason="consent given, asking preferred time")
        return Plan(reason="waiting on preferred time answer")

    # ── Step 4: everything in place - trigger the lead ──
    can_show = session.form_shows < 2 and (
        session.form_shows == 0 or turn - session.last_form_turn >= 4
    )
    if can_show:
        return Plan(show_form=True, reason="consent + preferred time in hand, showing form")
    return Plan(reason="form already shown, nothing new to do")


# ── small helpers ───────────────────────────────────────────────────────────
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?0?([6-9]\d{4}[\s-]?\d{5})(?!\d)")


def find_phone(text: str) -> str | None:
    """Indian mobile number typed in chat -> 10 digits, else None."""
    m = _PHONE_RE.search(text)
    return re.sub(r"\D", "", m.group(1)) if m else None


def clean_history(history: list[dict], keep: int = 20) -> list[dict]:
    """
    History comes from the browser, so it is untrusted: only user/assistant
    roles (no injected 'system' messages), string content, capped length.
    """
    out = []
    for m in history[-keep:]:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content[:1000]})
    return out
