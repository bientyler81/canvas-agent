"""Minimal OpenRouter chat-completions client (OpenAI-compatible, with tool calling)."""

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def chat(messages: list[dict], api_key: str, model: str, tools: list[dict] | None = None,
         max_tokens: int = 800, timeout: float = 45) -> dict:
    """Return the assistant message dict from one completion."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
    if tools:
        body["tools"] = tools
    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "X-Title": "Canvas Text Agent"},
        json=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]
