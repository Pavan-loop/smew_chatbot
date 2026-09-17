import httpx
import json
from app.core.config import settings
from collections.abc import AsyncIterator

async def complete(message: list[dict]) -> dict:
  async with httpx.AsyncClient(timeout=settings.llm_timout_seconds) as client:
    response = await client.post(
      f"{settings.openai_api_base}/chat/completions",
      headers={
        "Authorization": f"Bearer {settings.openai_api}",
        "Content-Type": "application/json",
      },
      json={
        "model": settings.chat_model,
        "messages": message,
        "max_tokens": 300,
      },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]

async def stream(message: list[dict]) -> AsyncIterator[str]:
  async with httpx.AsyncClient(timeout=settings.llm_timout_seconds) as client:
    async with client.stream(
      "POST",
      f"{settings.openai_api_base}/chat/completions",
      headers={
        "Authorization": f"Bearer {settings.openai_api}",
        "Content-Type": "application/json",
      },
      json={
        "model": settings.chat_model,
        "messages": message,
        "max_tokens": 300,
        "stream": True,
      },
    ) as response:
      response.raise_for_status()
      async for line in response.aiter_lines():
        if not line.startswith("data: "):
          continue
        data = line[6:]
        if data == "[DONE]":
          break
        chunk = json.loads(data)
        delta = chunk["choices"][0]["delta"]
        if content := delta.get("content"):
          yield content