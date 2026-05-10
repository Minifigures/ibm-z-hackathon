"""LLM explainer for simulation outputs.

Provider chain (highest priority first):
1. IBM watsonx.ai Granite     (gated on WATSONX_APIKEY + WATSONX_PROJECT_ID)
2. Anthropic Claude            (gated on ANTHROPIC_API_KEY)
3. Deterministic templated paragraph (always available)

Each provider raises on failure; explain() catches the error, logs a warning,
records it in error_chain, and continues to the next provider. The templated
paragraph is computed exactly once at the bottom when no live provider
succeeded, so the demo never breaks but a stage-side credential outage is
visible to anyone who inspects the response payload.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from . import watsonx

log = logging.getLogger(__name__)

EXPLAINER_MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = (
    "You are a public-health analyst assistant. Translate disease-spread "
    "simulator outputs into a tight, defensible 1-2 paragraph explanation "
    "for a non-expert. Always ground claims in the supplied numbers: cite "
    "expected cases, intervention effects, and route exposure. Never invent "
    "data. Avoid alarmism. Be precise about uncertainty (use the 50% / 95% "
    "intervals supplied). Keep it under 130 words."
)


def _format_context(simulation: dict[str, Any], focus_iso3: str | None) -> str:
    p = simulation["params_used"]
    lines = [
        f"Disease: {p['disease_id']}",
        f"Origin: {p['start_iso3']}",
        f"R0 (median): {p['r0_median']:.2f}",
        f"Incubation (median): {p['incubation_days_median']:.1f} days",
        f"Infectious period (median): {p['infectious_days_median']:.1f} days",
        f"Intervention multiplier on transmission: {p['intervention_multiplier']:.2f}",
        f"Travel restriction: {p['travel_restriction'] * 100:.0f}%",
        f"CFR: {p['cfr_pct']:.2f}%",
        f"Horizon: {simulation['horizon_days']} days",
        f"Monte Carlo runs: {simulation['calibration']['monte_carlo_runs']}",
        "",
        "Top imported regions (median expected imported cases at horizon):",
    ]
    for row in simulation["top_imports"][:5]:
        lines.append(f"  - {row['name']} ({row['iso3']}): {row['expected_cases']:.0f} cases ({row['per_100k']:.1f}/100k)")

    if focus_iso3:
        match = next((r for r in simulation["regions"] if r["iso3"] == focus_iso3), None)
        if match:
            q = match["quantiles"]
            lines += [
                "",
                f"Focus region: {match['name']} ({match['iso3']})",
                f"  Population: {match['population']:,}",
                f"  Cumulative cases at horizon (median): {match['cumulative_p50_final']:.0f}",
                f"  95% interval at horizon: [{q['p2_5'][-1]:.0f}, {q['p97_5'][-1]:.0f}]",
                f"  Active prevalence at horizon (median /100k): {match['prevalence_p50_per_100k']:.1f}",
            ]
    return "\n".join(lines)


def _template_fallback(simulation: dict[str, Any], focus_iso3: str | None) -> str:
    p = simulation["params_used"]
    if focus_iso3:
        region = next((r for r in simulation["regions"] if r["iso3"] == focus_iso3), None)
    else:
        region = None

    if region:
        q = region["quantiles"]
        return (
            f"At an R0 of {p['r0_median']:.1f} seeded in {p['start_iso3']}, the model projects "
            f"a median cumulative case count of {region['cumulative_p50_final']:.0f} in {region['name']} "
            f"by day {simulation['horizon_days']}, with a 95% interval of "
            f"{q['p2_5'][-1]:.0f} to {q['p97_5'][-1]:.0f}. "
            f"This is driven primarily by air-route exposure between {p['start_iso3']} and {region['iso3']}; "
            f"the current intervention multiplier of {p['intervention_multiplier']:.2f} and travel "
            f"restriction of {p['travel_restriction'] * 100:.0f}% are already included. "
            f"Tighter measures would compound non-linearly via the SEIR transmission term."
        )

    top = simulation["top_imports"][:3]
    names = ", ".join(t["name"] for t in top)
    return (
        f"With R0 around {p['r0_median']:.1f} and the current sliders, the highest-risk import "
        f"regions over the next {simulation['horizon_days']} days are {names}. The Monte Carlo "
        f"ensemble of {simulation['calibration']['monte_carlo_runs']} runs places the median "
        f"cumulative case count at {top[0]['expected_cases']:.0f} in {top[0]['name']} alone, "
        f"weighted by the gravity-air mobility from {p['start_iso3']}. Strengthening the "
        f"travel-restriction or mask sliders would damp these projections roughly proportionally."
    )


def _user_prompt(simulation: dict[str, Any], focus_iso3: str | None) -> str:
    return (
        "Explain the simulator output below for a public-health audience. Reference "
        "the gravity mobility model and the SEIR transmission step where relevant. "
        "Stay under 130 words.\n\n"
        + _format_context(simulation, focus_iso3)
    )


class _ProviderUnavailable(RuntimeError):
    """Raised by a provider that is not configured (env vars missing).

    Distinct from a transient call failure so explain() can decide whether
    to surface the skip in the error_chain (we hide unconfigured providers
    to keep the chain visible only to credential / network problems)."""


def _call_watsonx(simulation: dict[str, Any], focus_iso3: str | None) -> str:
    if not watsonx.is_configured():
        raise _ProviderUnavailable("watsonx env vars missing")
    try:
        return watsonx.generate(SYSTEM_PROMPT, _user_prompt(simulation, focus_iso3))
    except watsonx.WatsonxNotConfigured as exc:
        raise _ProviderUnavailable(str(exc)) from exc


def _call_anthropic(simulation: dict[str, Any], focus_iso3: str | None) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise _ProviderUnavailable("ANTHROPIC_API_KEY missing")
    try:
        import anthropic
    except ImportError as exc:
        raise _ProviderUnavailable("anthropic SDK not installed") from exc

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=EXPLAINER_MODEL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(simulation, focus_iso3)}],
    )
    text = "".join(part.text for part in msg.content if getattr(part, "type", None) == "text")
    return text.strip()


_PROVIDERS = (
    ("watsonx", _call_watsonx),
    ("anthropic", _call_anthropic),
)


def explain(simulation: dict[str, Any], focus_iso3: str | None = None) -> dict[str, Any]:
    """Walk the provider chain. Return the first successful provider's output;
    on full fall-through return the templated paragraph plus an error_chain
    enumerating each provider's failure (configured-but-failed only). The
    error_chain key is omitted entirely on the happy path."""
    error_chain: list[dict[str, str]] = []
    for name, call in _PROVIDERS:
        try:
            text = call(simulation, focus_iso3)
        except _ProviderUnavailable:
            # Provider is intentionally skipped because credentials are absent;
            # do not surface this as an error to the user.
            continue
        except Exception as exc:  # noqa: BLE001 - we want all transport failures to fall through
            log.warning("%s explain provider failed: %s", name, exc)
            error_chain.append({"provider": name, "error": str(exc)})
            continue
        result: dict[str, Any] = {"text": text, "source": name}
        if error_chain:
            result["error_chain"] = error_chain
        return result

    fallback: dict[str, Any] = {
        "text": _template_fallback(simulation, focus_iso3),
        "source": "template",
    }
    if error_chain:
        fallback["error_chain"] = error_chain
    return fallback
