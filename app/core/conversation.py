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
# Order = the order we ask in. Each slot is asked at most once (service twice).
SLOT_ORDER = ["service", "size", "material", "location", "timeline"]
MAX_ASKS = {"service": 2, "size": 1, "material": 1, "location": 1, "timeline": 1}

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
    material: str | None = None         # MS / SS (only if the customer stated it)
    size: str | None = None
    location: str | None = None
    timeline: str | None = None
    has_design_reference: bool = False
    asked_price: bool = False           # latest message asks price/cost/rate
    wants_visit: bool = False
    agreed_to_quote: bool = False
    is_ack: bool = False                # latest message is just "ok/thanks"

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationState":
        material = (_s(d.get("material")) or "").upper()
        purpose = (_s(d.get("purpose")) or "").lower()
        return cls(
            service=_s(d.get("service")),
            purpose=purpose if purpose in ("home", "commercial") else None,
            material=material if material in ("MS", "SS") else None,
            size=_s(d.get("size")),
            location=_s(d.get("location")),
            timeline=_s(d.get("timeline")),
            has_design_reference=d.get("has_design_reference") is True,
            asked_price=d.get("asked_price") is True,
            wants_visit=d.get("wants_visit") is True,
            agreed_to_quote=d.get("agreed_to_quote") is True,
            is_ack=d.get("is_ack") is True,
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
        return sum(bool(getattr(self, s)) for s in SLOT_ORDER)

    def missing(self) -> list[str]:
        out = []
        for slot in SLOT_ORDER:
            if getattr(self, slot):
                continue
            if slot == "material" and self.is_repair:
                continue  # MS vs SS is irrelevant for a repair job
            out.append(slot)
        return out

    def known_lines(self) -> list[str]:
        rows = [
            ("Wants", self.service), ("For", self.purpose),
            ("Material preference", self.material), ("Size", self.size),
            ("Location", self.location), ("Timeline", self.timeline),
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
    mode: str = "normal"       # normal | ack | out_of_area | phone_saved
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
    """Decide what the bot does this turn. Pure rules, no LLM."""
    if phone_saved_now:
        return Plan(mode="phone_saved", reason="customer typed their number")
    if state.out_of_area:
        return Plan(mode="out_of_area", reason=f"location '{state.location}' not served")
    if state.is_ack:
        return Plan(mode="ack", reason="pure acknowledgement")
    if lead_captured:
        return Plan(reason="lead already captured, just help")

    # Frontend told us a form was already shown but we have no memory of it
    # (e.g. server restarted): treat it as shown one turn ago.
    if form_shown_flag and session.form_shows == 0:
        session.form_shows, session.last_form_turn = 1, turn - 1

    has_intent_signal = (
        state.asked_price or state.wants_visit or state.agreed_to_quote
        or bool(state.size) or bool(state.timeline)
    )
    # "how much?" with no idea what they want is not a lead yet: ask what first.
    hot = bool(state.service or state.wants_visit) and has_intent_signal
    warm = bool(state.service) and state.filled() >= 3 and turn >= 3

    can_show = session.form_shows < 2 and (
        session.form_shows == 0 or turn - session.last_form_turn >= 4
    )
    if can_show and (hot or warm):
        return Plan(show_form=True, reason="hot: buying signal" if hot else "warm: engaged, enough detail")

    for slot in state.missing():
        if session.asked.get(slot, 0) < MAX_ASKS[slot]:
            session.asked[slot] = session.asked.get(slot, 0) + 1
            return Plan(ask=slot, reason=f"missing '{slot}'")
    return Plan(reason="nothing left to ask")


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
