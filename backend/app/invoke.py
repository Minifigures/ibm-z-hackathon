"""Invoke endpoint provider for the /explain chain.

Environment variables
- INVOKE_BASE_URL   e.g. https://invoke.cloud.marsi.eu
- INVOKE_API_KEY    optional bearer token for hosted endpoints that require auth
- INVOKE_MODEL      optional model id; defaults to openai/gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_MODEL = "openai/gpt-4o-mini"


class InvokeNotConfigured(RuntimeError):
    """Raised when INVOKE_BASE_URL is not set."""


class InvokeRequestError(RuntimeError):
    """Raised when Invoke chat-completions request fails."""


def is_configured() -> bool:
    return bool(os.environ.get("INVOKE_BASE_URL", "").strip())


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
    if not is_configured():
        raise InvokeNotConfigured("INVOKE_BASE_URL missing")

    base_url = os.environ["INVOKE_BASE_URL"].strip().rstrip("/")
    model_id = os.environ.get("INVOKE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    api_key = os.environ.get("INVOKE_API_KEY", "").strip()

    payload = json.dumps(
        {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise InvokeRequestError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise InvokeRequestError(f"URL error: {exc.reason}") from exc

    choices = body.get("choices") or []
    if not choices:
        raise InvokeRequestError(f"Invoke response missing choices: {body}")
    message = choices[0].get("message") or {}
    text = message.get("content") or ""
    if not text:
        raise InvokeRequestError(f"Invoke response missing assistant content: {body}")
    return text.strip()
