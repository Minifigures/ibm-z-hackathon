"""RAG-based disease parameter lookup.

User types a free-form disease name. We embed the query with IBM Granite
Embedding (via watsonx.ai), retrieve the top passages from the curated
corpus in `data/disease_corpus.json`, ask Llama 3.3 70B to extract median
epidemiological parameters from peer-reviewed literature, and validate the
response against the same range constraints used by /simulate. Out-of-range
outputs are rejected (hard mode). Successful lookups are cached in-process.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from . import watsonx_client

DATA_DIR = Path(__file__).parent / "data"
CORPUS_PATH = DATA_DIR / "disease_corpus.json"
COUNTRIES_PATH = DATA_DIR / "countries.json"
TOP_K = 3
MAX_CACHE_SIZE = 256


class DiseaseParams(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    r0: float = Field(..., ge=0.5, le=8.0)
    incubation_days: float = Field(..., ge=0.5, le=30.0)
    infectious_days: float = Field(..., ge=1.0, le=30.0)
    cfr_pct: float = Field(..., ge=0.01, le=50.0)
    sources: list[str] = Field(default_factory=list, max_length=6)
    confidence: str = Field("medium", pattern=r"^(high|medium|low)$")
    notes: str = Field("", max_length=320)
    likely_origin_iso3: str | None = Field(default=None)
    likely_origin_reason: str = Field("", max_length=200)


_cache: dict[str, dict[str, Any]] = {}
_corpus: list[dict[str, Any]] | None = None
_corpus_embeddings: np.ndarray | None = None
_valid_iso3: set[str] | None = None


def _load_corpus() -> list[dict[str, Any]]:
    global _corpus
    if _corpus is None:
        _corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return _corpus


def _load_valid_iso3() -> set[str]:
    global _valid_iso3
    if _valid_iso3 is None:
        countries = json.loads(COUNTRIES_PATH.read_text(encoding="utf-8"))
        _valid_iso3 = {c["iso3"] for c in countries}
    return _valid_iso3


def _embed(texts: list[str]) -> list[list[float]] | None:
    emb = watsonx_client.get_embedding_model()
    if emb is None:
        return None
    try:
        return emb.embed_documents(texts=texts)
    except Exception:  # noqa: BLE001
        return None


def _ensure_corpus_embeddings() -> np.ndarray | None:
    global _corpus_embeddings
    if _corpus_embeddings is not None:
        return _corpus_embeddings
    corpus = _load_corpus()
    vectors = _embed([entry["text"] for entry in corpus])
    if vectors is None:
        return None
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / np.where(norms == 0, 1.0, norms)
    _corpus_embeddings = arr
    return _corpus_embeddings


def _retrieve(query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
    matrix = _ensure_corpus_embeddings()
    if matrix is None:
        return []
    qvecs = _embed([query])
    if not qvecs:
        return []
    qv = np.asarray(qvecs[0], dtype=np.float32)
    n = float(np.linalg.norm(qv))
    if n == 0.0:
        return []
    qv = qv / n
    sims = matrix @ qv
    order = np.argsort(-sims)[:top_k]
    corpus = _load_corpus()
    return [{**corpus[int(i)], "score": float(sims[int(i)])} for i in order]


SYSTEM_PROMPT_TEMPLATE = (
    "You are an epidemiology parameter extractor. Given a disease query and "
    "reference passages, return ONE JSON object with median values from "
    "peer-reviewed literature.\n\n"
    "Required schema:\n"
    "{{\n"
    '  "label": "<canonical disease name>",\n'
    '  "r0": <basic reproduction number, float in [0.5, 8.0]>,\n'
    '  "incubation_days": <median incubation in days, float in [0.5, 30]>,\n'
    '  "infectious_days": <median infectious period in days, float in [1, 30]>,\n'
    '  "cfr_pct": <case fatality rate %, float in [0.01, 50]>,\n'
    '  "sources": [<short citation strings, max 6>],\n'
    '  "confidence": "high"|"medium"|"low",\n'
    '  "notes": "<one-sentence caveat, max 320 chars>",\n'
    '  "likely_origin_iso3": "<ISO3 code from the allowed list, or null>",\n'
    '  "likely_origin_reason": "<short reason, max 200 chars>"\n'
    "}}\n\n"
    "Allowed ISO3 codes for likely_origin_iso3:\n{iso3_list}\n\n"
    "Origin selection rules (read carefully):\n"
    "- Pick the country where this pathogen first emerged or where the largest "
    "documented outbreaks have historically originated.\n"
    "- The likely_origin_iso3 value MUST be from the allowed list above. "
    "If the true origin country is NOT in the allowed list (e.g. the actual "
    "origin is South Sudan, Burkina Faso, Iceland, etc.), DO NOT return null. "
    "Instead, pick the geographically nearest neighbouring country that IS in "
    "the allowed list. Examples: a Senegalese-origin disease should fall back "
    "to SEN (in list); a Burkinabe-origin disease should fall back to GHA or "
    "CIV; a Rwandan-origin disease should fall back to UGA; a Zambian-origin "
    "disease should fall back to AGO or COD.\n"
    "- Only return null if the disease has no meaningful geographic origin "
    "(e.g. seasonal influenza is global).\n"
    "- likely_origin_reason should briefly state where the pathogen actually "
    "originated AND why you picked the country code you returned (especially "
    "if it was a geographic fallback).\n\n"
    "Other rules:\n"
    "- Use median or central estimates, not extremes.\n"
    "- Prefer values from the supplied reference passages when relevant.\n"
    "- If the disease query is genuinely unknown or nonsensical, return "
    '{{"error": "<short reason>"}}.\n'
    "- Output ONLY the JSON object. No prose, no markdown, no code fences."
)


def _system_prompt() -> str:
    iso3_list = ", ".join(sorted(_load_valid_iso3()))
    return SYSTEM_PROMPT_TEMPLATE.format(iso3_list=iso3_list)


def _build_user_prompt(query: str, retrieved: list[dict[str, Any]]) -> str:
    parts = [f"Disease query: {query}", "", "Reference passages:"]
    if retrieved:
        for i, r in enumerate(retrieved, start=1):
            parts.append(f"[{i}] ({r.get('source', 'n/a')}) {r.get('text', '')}")
    else:
        parts.append("(no relevant passages retrieved; use training-data knowledge)")
    return "\n".join(parts)


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    match = _JSON_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _extract_text(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(response or "")


def _normalize_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def lookup(name: str) -> dict[str, Any]:
    """Resolve a free-form disease name to validated simulator parameters."""
    key = _normalize_key(name)
    if not key:
        return {"status": "rejected", "message": "Empty disease name."}

    if key in _cache:
        return {**_cache[key], "cached": True}

    if not watsonx_client.is_configured():
        return {
            "status": "unconfigured",
            "message": "watsonx.ai credentials not set. Use a preset instead.",
        }

    chat = watsonx_client.get_chat_model()
    if chat is None:
        return {
            "status": "unconfigured",
            "message": "watsonx.ai SDK unavailable or auth failed.",
        }

    retrieved = _retrieve(name)
    user_prompt = _build_user_prompt(name, retrieved)

    try:
        response = chat.chat(
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            params={"max_tokens": 600, "temperature": 0.1},
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "rejected", "message": f"Model call failed: {exc}"}

    raw_text = _extract_text(response)
    parsed = _extract_json(raw_text)
    if parsed is None:
        return {"status": "rejected", "message": "Model returned no parseable JSON.", "raw": raw_text[:500]}

    if "error" in parsed:
        return {"status": "rejected", "message": str(parsed["error"]), "raw": raw_text[:500]}

    try:
        params = DiseaseParams(**parsed)
    except ValidationError as exc:
        return {
            "status": "rejected",
            "message": "Model output failed validation (hard mode).",
            "errors": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
            "raw": raw_text[:500],
        }

    # Soft-validate origin against the modelled-country list. If the LLM
    # picks something we don't model, drop the field instead of rejecting
    # the whole lookup.
    if params.likely_origin_iso3:
        candidate = params.likely_origin_iso3.strip().upper()
        if candidate in _load_valid_iso3():
            params.likely_origin_iso3 = candidate
        else:
            params.likely_origin_iso3 = None
            params.likely_origin_reason = ""

    result = {
        "status": "ok",
        "params": params.model_dump(),
        "retrieved": [
            {
                "source": r.get("source"),
                "score": r.get("score"),
                "snippet": (r.get("text") or "")[:160],
                "disease": r.get("disease"),
            }
            for r in retrieved
        ],
    }

    if len(_cache) >= MAX_CACHE_SIZE:
        _cache.pop(next(iter(_cache)))
    _cache[key] = result
    return {**result, "cached": False}


def clear_cache() -> None:
    """Test helper. Resets in-process state so cases are independent."""
    global _corpus_embeddings
    _cache.clear()
    _corpus_embeddings = None
