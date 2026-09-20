"""Everything that happens *before* the reply is streamed. Shared by the API and scratch.py."""

from dataclasses import dataclass

from app.core.conversation import (
    ConversationState, Plan, Session, clean_history, find_phone, get_session, make_plan,
)
from app.core.leads import save_lead
from app.llm.extractor import extract_state
from app.prompt.system import SYSTEM_PROMPT, build_turn_block


@dataclass
class TurnContext:
    messages: list[dict]
    history: list[dict]
    state: ConversationState
    plan: Plan
    session: Session
    turn: int
    extractor_usage: dict


async def prepare_turn(
    message: str,
    history: list[dict],
    visitor_id: str,
    lead_captured: bool = False,
    form_shown: bool = False,
) -> TurnContext:
    history = clean_history(history)
    session = get_session(visitor_id)
    turn = 1 + sum(1 for m in history if m["role"] == "user")

    state, usage = await extract_state(history, message)

    # Customer typed their number straight into the chat: capture it right away.
    phone_saved_now = False
    phone = find_phone(message)
    if phone and not lead_captured and not session.phone_saved:
        notes = state.summary()
        notes = f"{notes} | Said: {message[:200]}" if notes else f"Said: {message[:200]}"
        await save_lead(phone=phone, name=None, service=state.service, notes=notes, visitor_id=visitor_id)
        session.phone_saved = True
        phone_saved_now = True

    plan = make_plan(
        state,
        turn=turn,
        session=session,
        lead_captured=lead_captured or session.phone_saved,
        form_shown_flag=form_shown,
        phone_saved_now=phone_saved_now,
    )
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT + build_turn_block(state, plan)}]
        + history
        + [{"role": "user", "content": message}]
    )
    return TurnContext(messages, history, state, plan, session, turn, usage)
