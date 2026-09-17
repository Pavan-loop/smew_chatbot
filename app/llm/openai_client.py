import httpx
import json
from app.core.config import settings
from collections.abc import AsyncIterator
from dataclasses import dataclass

@dataclass
class ToolCallEvent:
  name: str
  arguments: dict

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

async def stream(
    message: list[dict],
    tools: list[dict] | None = None
    ) -> AsyncIterator[str | ToolCallEvent]:
  payload = {
    "model": settings.chat_model,
    "messages": message,
    "max_tokens": 300,
    "stream": True,
  }
  if tools:
    payload["tools"] = tools

  tool_name: str | None = None
  tool_arg_raw: str = ""

  async with httpx.AsyncClient(timeout=settings.llm_timout_seconds) as client:
    async with client.stream(
      "POST",
      f"{settings.openai_api_base}/chat/completions",
      headers={
        "Authorization": f"Bearer {settings.openai_api}",
        "Content-Type": "application/json",
      },
      json=payload,
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
        finish_reason = chunk["choices"][0].get("finish_reason")
        if content := delta.get("content"):
          yield content

        if tool_call := delta.get("tool_calls"):
          tc = tool_call[0]
          if tc.get("function", {}).get("name"):
            tool_name = tc["function"]["name"]
          if arg_chunk := tc.get("function", {}).get("arguments"):
            tool_arg_raw += arg_chunk

        if finish_reason == "tool_calls" and tool_name:
          yield ToolCallEvent(
            name=tool_name,
            arguments=json.loads(tool_arg_raw) if tool_arg_raw else {}
          )

        