import asyncio
from app.llm.openai_client import stream, ToolCallEvent
from app.llm.tools import TOOLS
from app.prompt.system import SYSTEM_PROMPT

async def main():
  message = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "do you make SS railings?"},
  ]
  async for chunk in stream(message, tools=TOOLS):
    if isinstance(chunk, ToolCallEvent):
      print(f"\n TOOL CALLED: {chunk.name} with args: {chunk.arguments}\n")
    else:
      print(chunk, end="", flush=True)
  print()  

asyncio.run(main())