"""IBM watsonx.ai Granite provider for the /explain endpoint.

This module is env-gated: when WATSONX_APIKEY and WATSONX_PROJECT_ID are unset
the explain pipeline silently falls through to the next provider in the chain.
When set, the module exchanges the API key for an IBM Cloud IAM bearer token
and posts to the watsonx.ai text-generation endpoint. The IAM token is cached
in memory until five minutes before its declared expiry.

Environment variables
- WATSONX_APIKEY        IBM Cloud API key (https://cloud.ibm.com/iam/apikeys)
- WATSONX_PROJECT_ID    watsonx.ai project id (Manage > General > Project ID)
- WATSONX_URL           Defaults to https://us-south.ml.cloud.ibm.com
- WATSONX_MODEL_ID      Defaults to ibm/granite-3-3-8b-instruct
- WATSONX_API_VERSION   Defaults to 2023-05-29
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
DEFAULT_MODEL = "ibm/granite-3-3-8b-instruct"
DEFAULT_API_VERSION = "2023-05-29"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
TOKEN_REFRESH_BUFFER_SECONDS = 300


class WatsonxNotConfigured(RuntimeError):
    """Raised when the required environment variables are missing."""


class WatsonxRequestError(RuntimeError):
    """Raised when the watsonx.ai HTTP call fails for any reason."""


@dataclass
class _Token:
    value: str
    expires_at: float  # epoch seconds


_token_cache: _Token | None = None


def is_configured() -> bool:
    return bool(os.environ.get("WATSONX_APIKEY", "").strip()) and bool(
        os.environ.get("WATSONX_PROJECT_ID", "").strip()
    )


def _http_post_json(url: str, body: bytes, headers: dict[str, str], timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise WatsonxRequestError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise WatsonxRequestError(f"URL error: {exc.reason}") from exc


def _get_iam_token() -> str:
    global _token_cache
    now = time.time()
    if _token_cache and _token_cache.expires_at > now + TOKEN_REFRESH_BUFFER_SECONDS:
        return _token_cache.value

    api_key = os.environ.get("WATSONX_APIKEY", "").strip()
    if not api_key:
        raise WatsonxNotConfigured("WATSONX_APIKEY not set")

    body = urllib.parse.urlencode(
        {"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key}
    ).encode("utf-8")
    payload = _http_post_json(
        IAM_TOKEN_URL,
        body=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    token = payload.get("access_token")
    expires_in = float(payload.get("expires_in", 3600))
    if not token:
        raise WatsonxRequestError("IAM response missing access_token")
    _token_cache = _Token(value=token, expires_at=now + expires_in)
    return token


def reset_token_cache() -> None:
    """Used by tests; not part of the public API."""
    global _token_cache
    _token_cache = None


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
    """Run a single watsonx.ai text-generation call and return the completion.

    Raises WatsonxNotConfigured when env vars are missing so the explain chain
    can fall through cleanly. Raises WatsonxRequestError for transport / API
    failures so the caller can decide whether to log + fall through.
    """
    if not is_configured():
        raise WatsonxNotConfigured("WATSONX_APIKEY or WATSONX_PROJECT_ID missing")

    base_url = os.environ.get("WATSONX_URL", DEFAULT_URL).rstrip("/")
    model_id = os.environ.get("WATSONX_MODEL_ID", DEFAULT_MODEL)
    project_id = os.environ["WATSONX_PROJECT_ID"].strip()
    api_version = os.environ.get("WATSONX_API_VERSION", DEFAULT_API_VERSION)

    token = _get_iam_token()
    full_prompt = f"{system_prompt.strip()}\n\n{user_prompt.strip()}"
    body = json.dumps(
        {
            "input": full_prompt,
            "model_id": model_id,
            "project_id": project_id,
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": max_tokens,
                "min_new_tokens": 30,
                "repetition_penalty": 1.05,
                "stop_sequences": ["\n\nUser:", "\n\nSystem:"],
            },
        }
    ).encode("utf-8")
    payload = _http_post_json(
        f"{base_url}/ml/v1/text/generation?version={api_version}",
        body=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    results = payload.get("results") or []
    if not results:
        raise WatsonxRequestError(f"watsonx response missing results: {payload}")
    text = results[0].get("generated_text") or ""
    return text.strip()
