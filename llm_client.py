from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional


def has_openai_key() -> bool:
    """Check if any LLM API key is configured."""
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))


def call_openai_text(
    prompt: str,
    system: str = "",
    model: str = "",
    temperature: float = 0.3,
    max_output_tokens: int = 0,
) -> Optional[str]:
    """Call an OpenAI-compatible chat API and return the raw text response."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if not api_key:
        return None

    if not model:
        model = "gpt-4.1-mini" if os.environ.get("OPENAI_API_KEY") else "deepseek-chat"

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try openai SDK first
    try:
        from openai import OpenAI

        base_url = None
        if not os.environ.get("OPENAI_API_KEY") and os.environ.get("DEEPSEEK_API_KEY"):
            base_url = "https://api.deepseek.com/v1"

        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        extra: dict = {}
        if max_output_tokens > 0:
            extra["max_tokens"] = max_output_tokens

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            timeout=60.0,
            **extra,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        pass

    # Fallback: raw HTTP
    try:
        return _call_deepseek_http_text(api_key, messages, temperature, max_output_tokens)
    except Exception:
        return None


def call_openai_json(
    prompt: str,
    system: str = "",
    model: str = "",
    temperature: float = 0.3,
    max_output_tokens: int = 0,
) -> Optional[Dict[str, Any]]:
    """Call an OpenAI-compatible chat API and return parsed JSON."""
    text = call_openai_text(
        prompt, system=system, model=model, temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    if text is None:
        return None
    return _parse_json(text)


def _call_deepseek_http_text(
    api_key: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_output_tokens: int = 0,
) -> Optional[str]:
    import urllib.request

    payload: dict = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    if max_output_tokens > 0:
        payload["max_tokens"] = max_output_tokens
    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return (data["choices"][0]["message"]["content"] or "").strip()


def _call_deepseek_http(
    api_key: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_output_tokens: int = 0,
) -> Optional[Dict[str, Any]]:
    text = _call_deepseek_http_text(api_key, messages, temperature, max_output_tokens)
    if text is None:
        return None
    return _parse_json(text)


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from text that may contain markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` fence
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
