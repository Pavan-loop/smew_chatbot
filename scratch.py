"""
Replay scripted customer conversations through the REAL pipeline (real OpenAI calls)
and print what the bot understood, what it decided, and what it said.

    uv run python scratch.py            # all scenarios
    uv run python scratch.py 2          # just scenario #2
"""
import asyncio
import sys
import uuid

from app.core.turn import prepare_turn
from app.llm.openai_client import stream

SCENARIOS = [
    ("browsing -> price -> number",
     ["hi", "do you make SS railings?", "how much for 12 feet?", "ok 98864 64819"]),
    ("vague, then engaged",
     ["I need a gate", "main gate for my house", "not sure about size", "MS is fine, I'm in Vijayanagar", "ok thanks"]),
    ("kanglish",
     ["namaste, grill madtira?", "window ge grill beku, 4x5 ft", "yestu aagutte?"]),
    ("out of area",
     ["do you do gates in Bangalore?"]),
]


async def run(name: str, script: list[str]) -> None:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    vid, history = str(uuid.uuid4()), []
    for msg in script:
        ctx = await prepare_turn(msg, history, vid)
        print(f"\nCUSTOMER: {msg}")
        print(f"  known : {ctx.state.summary() or '-'}")
        print(f"  plan  : mode={ctx.plan.mode} ask={ctx.plan.ask} form={ctx.plan.show_form}  ({ctx.plan.reason})")
        reply = "".join([c async for c in stream(ctx.messages) if isinstance(c, str)])
        print(f"  BOT   : {reply}")
        if ctx.plan.show_form:
            print("  [LEAD FORM POPS UP]")
            ctx.session.form_shows += 1
            ctx.session.last_form_turn = ctx.turn
        history += [{"role": "user", "content": msg}, {"role": "assistant", "content": reply}]


async def main() -> None:
    pick = int(sys.argv[1]) - 1 if len(sys.argv) > 1 else None
    for i, (name, script) in enumerate(SCENARIOS):
        if pick is None or pick == i:
            await run(name, script)

asyncio.run(main())
