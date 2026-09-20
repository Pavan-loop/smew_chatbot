"""
In-memory analytics store.
Lives in RAM — clears on restart. That is intentional for a debug tool.
Thread-safe enough for single-worker FastAPI (asyncio, not threads).
"""

from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# ── cost constants (gpt-4o-mini, per 1M tokens) ──
INPUT_COST_PER_M  = 0.150   # USD
OUTPUT_COST_PER_M = 0.600   # USD


def _now() -> float:
    return time.time()


@dataclass
class MessageRecord:
    index: int
    role: str
    content_preview: str    # first 200 chars
    full_content: str       # full text for inspector
    char_len: int


@dataclass
class TurnRecord:
    id: str
    ts: float
    visitor_id: str
    user_message: str
    lead_captured_flag: bool
    tools_active: bool
    history_turns: int
    messages_sent: list[MessageRecord]
    reply: str
    tool_fired: str | None
    tool_args: dict
    tokens_in: int
    tokens_out: int
    cost_usd: float
    duration_ms: float
    error: str | None
    state: dict = field(default_factory=dict)   # extractor output + plan (for debugging)

    @property
    def ts_iso(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")


@dataclass
class LeadRecord:
    id: str
    ts: float
    visitor_id: str
    phone: str
    name: str | None
    service: str | None
    notes: str | None
    telegram_sent: bool

    @property
    def ts_iso(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")


@dataclass
class ErrorRecord:
    ts: float
    visitor_id: str
    user_message: str
    error: str

    @property
    def ts_iso(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")


class AnalyticsStore:
    def __init__(self, maxlen: int = 200):
        self.turns:  deque[TurnRecord]  = deque(maxlen=maxlen)
        self.leads:  list[LeadRecord]   = []
        self.errors: deque[ErrorRecord] = deque(maxlen=50)
        self._start = _now()
        self._turn_counter = 0

    # ── write ──────────────────────────────────────────────────

    def record_turn(self, **kwargs) -> None:
        self._turn_counter += 1
        self.turns.append(TurnRecord(**kwargs))

    def record_lead(self, **kwargs) -> None:
        self.leads.append(LeadRecord(**kwargs))

    def record_error(self, **kwargs) -> None:
        self.errors.append(ErrorRecord(**kwargs))

    # ── read ───────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        turns = list(self.turns)
        total_in  = sum(t.tokens_in  for t in turns)
        total_out = sum(t.tokens_out for t in turns)
        total_cost = sum(t.cost_usd for t in turns)
        tool_fires = sum(1 for t in turns if t.tool_fired)
        errors     = len(self.errors)
        uptime_s   = int(_now() - self._start)
        return {
            "uptime_seconds":  uptime_s,
            "total_turns":     len(turns),
            "total_leads":     len(self.leads),
            "total_errors":    errors,
            "tool_fires":      tool_fires,
            "tokens_in":       total_in,
            "tokens_out":      total_out,
            "cost_usd":        round(total_cost, 6),
            "cost_inr":        round(total_cost * 84, 4),
        }

    def turns_json(self) -> list[dict]:
        return [
            {
                "id":               t.id,
                "ts":               t.ts_iso,
                "visitor_id":       t.visitor_id[:8],
                "user_message":     t.user_message,
                "reply":            t.reply[:300],
                "tool_fired":       t.tool_fired,
                "tool_args":        t.tool_args,
                "history_turns":    t.history_turns,
                "lead_captured_flag": t.lead_captured_flag,
                "tools_active":     t.tools_active,
                "tokens_in":        t.tokens_in,
                "tokens_out":       t.tokens_out,
                "cost_usd":         t.cost_usd,
                "duration_ms":      t.duration_ms,
                "error":            t.error,
                "state":            t.state,
                "messages_sent":    [
                    {
                        "index":   m.index,
                        "role":    m.role,
                        "preview": m.content_preview,
                        "full":    m.full_content,
                        "chars":   m.char_len,
                    }
                    for m in t.messages_sent
                ],
            }
            for t in reversed(self.turns)
        ]

    def leads_json(self) -> list[dict]:
        return [
            {
                "id":           l.id,
                "ts":           l.ts_iso,
                "visitor_id":   l.visitor_id[:8],
                "phone":        l.phone,
                "name":         l.name,
                "service":      l.service,
                "notes":        l.notes,
                "telegram_sent": l.telegram_sent,
            }
            for l in reversed(self.leads)
        ]

    def errors_json(self) -> list[dict]:
        return [
            {
                "ts":           e.ts_iso,
                "visitor_id":   e.visitor_id[:8],
                "user_message": e.user_message,
                "error":        e.error,
            }
            for e in reversed(self.errors)
        ]


# single global instance
store = AnalyticsStore()