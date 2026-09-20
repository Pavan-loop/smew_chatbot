import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.store import (
    MessageRecord, store, INPUT_COST_PER_M, OUTPUT_COST_PER_M
)
from app.core.turn import prepare_turn
from app.llm.openai_client import stream

router = APIRouter()

# gpt-4o-mini: ~4 chars per token (rough estimate for streaming where
# the API does not return usage in every chunk)
CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[dict] = Field(default_factory=list, max_length=60)
    lead_captured: bool = False   # customer already submitted the form
    form_shown: bool = False      # optional: frontend already showed the form


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def event_stream(
    message: str,
    history: list[dict],
    visitor_id: str,
    lead_captured: bool,
    form_shown: bool,
) -> AsyncIterator[str]:
    yield sse({"type": "visitor", "visitor_id": visitor_id})

    turn_id = str(uuid.uuid4())[:8]
    t_start = time.time()
    reply_parts: list[str] = []
    error_msg: str | None = None
    ctx = None
    shown_form = False

    try:
        # extractor call + planning happen before the first token
        ctx = await prepare_turn(message, history, visitor_id, lead_captured, form_shown)

        async for chunk in stream(ctx.messages):
            if isinstance(chunk, str):
                reply_parts.append(chunk)
                yield sse({"type": "text", "text": chunk})

        # The form pops AFTER the bot has spoken, so the customer never sees a bare form.
        if ctx.plan.show_form:
            shown_form = True
            ctx.session.form_shows += 1
            ctx.session.last_form_turn = ctx.turn
            yield sse({
                "type": "action",
                "action": "show_lead_form",
                "service": ctx.state.service,
                "notes": ctx.state.summary() or None,
            })

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

    # ── record the completed turn for the debug dashboard ──
    duration_ms = round((time.time() - t_start) * 1000, 1)
    full_reply = "".join(reply_parts)
    msgs = ctx.messages if ctx else []
    ex_usage = ctx.extractor_usage if ctx else {}
    tokens_in = sum(_estimate_tokens(m["content"]) for m in msgs) + ex_usage.get("prompt_tokens", 0)
    tokens_out = (_estimate_tokens(full_reply) if full_reply else 0) + ex_usage.get("completion_tokens", 0)
    cost = (tokens_in / 1_000_000) * INPUT_COST_PER_M + (tokens_out / 1_000_000) * OUTPUT_COST_PER_M

    store.record_turn(
        id=turn_id,
        ts=time.time(),
        visitor_id=visitor_id,
        user_message=message,
        lead_captured_flag=lead_captured,
        tools_active=bool(ctx and ctx.plan.show_form),
        history_turns=len(ctx.history) if ctx else 0,
        messages_sent=[
            MessageRecord(
                index=i, role=m["role"],
                content_preview=m["content"][:200].replace("\n", " "),
                full_content=m["content"], char_len=len(m["content"]),
            )
            for i, m in enumerate(msgs)
        ],
        reply=full_reply,
        tool_fired="show_lead_form" if shown_form else None,
        tool_args={"service": ctx.state.service, "notes": ctx.state.summary()} if shown_form else {},
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=round(cost, 6),
        duration_ms=duration_ms,
        error=error_msg,
        state={
            **(ctx.state.to_dict() if ctx else {}),
            "_plan": {"mode": ctx.plan.mode, "ask": ctx.plan.ask,
                      "show_form": ctx.plan.show_form, "why": ctx.plan.reason} if ctx else {},
        },
    )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    x_visitor_id: str | None = Header(default=None),
) -> StreamingResponse:
    visitor_id = x_visitor_id or str(uuid.uuid4())
    return StreamingResponse(
        event_stream(body.message, body.history, visitor_id, body.lead_captured, body.form_shown),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
