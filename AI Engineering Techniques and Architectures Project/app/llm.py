"""Optional LLM provider (any OpenAI-compatible chat-completions endpoint: Groq, OpenRouter, Ollama, ...).

The app works WITHOUT a key (deterministic planner + extractive synthesis). When LLM_API_KEY is set the LLM is used for
(1) intent classification when the rule-based classifier is unsure and (2) grounded answer synthesis.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

import settings


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self._transport = transport  # injectable for tests

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def complete(self, messages: list[dict[str, str]], max_tokens: int = 700, temperature: float = 0.1, json_mode: bool = False) -> str:
        if not self.configured:
            raise LLMError("LLM_API_KEY is not set")
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "seed": settings.SEED}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_S, transport=self._transport) as client:
                r = await client.post(f"{self.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e

    async def complete_json(self, messages: list[dict[str, str]], **kw) -> dict:
        text = await self.complete(messages, json_mode=True, **kw)
        m = re.search(r"\{.*\}", text, re.S)
        try:
            return json.loads(m.group(0) if m else text)
        except ValueError as e:
            raise LLMError(f"invalid JSON from model: {text[:120]}") from e
