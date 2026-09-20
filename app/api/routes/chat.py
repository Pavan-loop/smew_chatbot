import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.store import (
    MessageRecord, TurnRecord, ErrorRecord, store,
    INPUT_COST_PER_M, OUTPUT_COST_PER_M
)
from app.llm.openai_client import stream, ToolCallEvent
from app.llm.tools import TOOLS
from app.prompt.system import SYSTEM_PROMPT

router = APIRouter()

# gpt-4o-mini: ~4 chars per token (rough estimate for streaming where
# the API does not return usage in every chunk)
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[dict] = Field(default_factory=list)
    lead_captured: bool = False


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def event_stream(
    message: str,
    history: list[dict],
    visitor_id: str,
    lead_captured: bool,
) -> AsyncIterator[str]:
    yield sse({"type": "visitor", "visitor_id": visitor_id})

    lead_note = (
        "\n\nNOTE: This Customer has already submitted their contact details "
        "this session do not call capture_lead under any circumstances"
        if lead_captured else ""
    )
    recent = history[-20:]
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT + lead_note}]
        + recent
        + [{"role": "user", "content": message}]
    )

    # ── build message records for the dashboard ──
    msg_records = [
        MessageRecord(
            index=i,
            role=m["role"],
            content_preview=m["content"][:200].replace("\n", " "),
            full_content=m["content"],
            char_len=len(m["content"]),
        )
        for i, m in enumerate(messages)
    ]

    # estimate input tokens from total chars sent
    tokens_in_est = sum(_estimate_tokens(m["content"]) for m in messages)

    turn_id = str(uuid.uuid4())[:8]
    t_start = time.time()

    reply_parts: list[str] = []
    tool_fired: str | None = None
    tool_args: dict = {}
    error_msg: str | None = None

    try:
        async for chunk in stream(
            messages, tools=TOOLS if not lead_captured else None
        ):
            if isinstance(chunk, ToolCallEvent):
                tool_fired = chunk.name
                tool_args = chunk.arguments
                yield sse({
                    "type": "action",
                    "action": "show_lead_form",
                    "service": chunk.arguments.get("service"),
                    "notes": chunk.arguments.get("notes"),
                })
            else:
                reply_parts.append(chunk)
                yield sse({"type": "text", "text": chunk})

    except Exception as exc:
        error_msg = str(exc)
        store.record_error(
            ts=time.time(),
            visitor_id=visitor_id,
            user_message=message,
            error=error_msg,
        )
        yield sse({"type": "error", "text": "Something went wrong. Call us at 9986464819."})

    finally:
        yield sse({"type": "done"})

    # ── record the completed turn ──
    duration_ms = round((time.time() - t_start) * 1000, 1)
    full_reply = "".join(reply_parts)
    tokens_out_est = _estimate_tokens(full_reply) if full_reply else 0
    cost = (
        (tokens_in_est  / 1_000_000) * INPUT_COST_PER_M +
        (tokens_out_est / 1_000_000) * OUTPUT_COST_PER_M
    )

    store.record_turn(
        id=turn_id,
        ts=time.time(),
        visitor_id=visitor_id,
        user_message=message,
        lead_captured_flag=lead_captured,
        tools_active=not lead_captured,
        history_turns=len(recent),
        messages_sent=msg_records,
        reply=full_reply,
        tool_fired=tool_fired,
        tool_args=tool_args,
        tokens_in=tokens_in_est,
        tokens_out=tokens_out_est,
        cost_usd=round(cost, 6),
        duration_ms=duration_ms,
        error=error_msg,
    )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    x_visitor_id: str | None = Header(default=None),
) -> StreamingResponse:
    visitor_id = x_visitor_id or str(uuid.uuid4())
    return StreamingResponse(
        event_stream(body.message, body.history, visitor_id, body.lead_captured),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )