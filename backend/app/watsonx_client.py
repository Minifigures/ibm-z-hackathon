"""Shared watsonx.ai client setup.

Lazy singletons so /explain and /disease-params reuse one chat-model and one
embedding-model client across requests instead of re-authenticating each
call. `is_configured()` lets callers degrade gracefully when WATSONX_APIKEY
or WATSONX_PROJECT_ID is unset (templated explanations, 503 from /disease-params).
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
CHAT_MODEL_ID = "meta-llama/llama-3-3-70b-instruct"
EMBEDDING_MODEL_ID = "ibm/granite-embedding-278m-multilingual"

_chat_model: Any = None
_embedding_model: Any = None


def is_configured() -> bool:
    return bool(
        os.environ.get("WATSONX_APIKEY", "").strip()
        and os.environ.get("WATSONX_PROJECT_ID", "").strip()
    )


def _credentials() -> Any:
    from ibm_watsonx_ai import Credentials

    url = os.environ.get("WATSONX_URL", "").strip() or DEFAULT_URL
    return Credentials(url=url, api_key=os.environ["WATSONX_APIKEY"])


def get_chat_model() -> Any | None:
    global _chat_model
    if not is_configured():
        return None
    if _chat_model is not None:
        return _chat_model
    try:
        from ibm_watsonx_ai.foundation_models import ModelInference
        _chat_model = ModelInference(
            model_id=CHAT_MODEL_ID,
            credentials=_credentials(),
            project_id=os.environ["WATSONX_PROJECT_ID"],
        )
    except Exception:  # noqa: BLE001 - includes ImportError + auth failures
        return None
    return _chat_model


def get_embedding_model() -> Any | None:
    global _embedding_model
    if not is_configured():
        return None
    if _embedding_model is not None:
        return _embedding_model
    try:
        from ibm_watsonx_ai.foundation_models import Embeddings
        _embedding_model = Embeddings(
            model_id=EMBEDDING_MODEL_ID,
            credentials=_credentials(),
            project_id=os.environ["WATSONX_PROJECT_ID"],
        )
    except Exception:  # noqa: BLE001
        return None
    return _embedding_model


def reset() -> None:
    """Clear cached singletons. Used by tests between cases."""
    global _chat_model, _embedding_model
    _chat_model = None
    _embedding_model = None
