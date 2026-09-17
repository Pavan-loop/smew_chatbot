import asyncio
from app.llm.openai_client import stream
from app.prompt.system import SYSTEM_PROMPT

async def main():
  message = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "nivu collapsible gate fabricate madtira?"},
  ]
  async for chunk in stream(message):
    print(chunk, end="", flush=True)
  print()  

asyncio.run(main())