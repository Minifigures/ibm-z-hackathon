"""LLM explainer for simulation outputs.

Provider chain (highest priority first):
1. IBM watsonx.ai Granite     (gated on WATSONX_APIKEY + WATSONX_PROJECT_ID)
2. Anthropic Claude            (gated on ANTHROPIC_API_KEY)
3. Deterministic templated paragraph (always available)

Each provider may fail gracefully; on failure the chain falls through to the
next entry so the demo never breaks. The response always includes a `source`
field so the UI can render a provenance pill.
"""

from __future__ import annotations

import os
from typing import Any

from . import watsonx

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


def _try_watsonx(simulation: dict[str, Any], focus_iso3: str | None) -> dict[str, str] | None:
    if not watsonx.is_configured():
        return None
    try:
        text = watsonx.generate(SYSTEM_PROMPT, _user_prompt(simulation, focus_iso3))
    except watsonx.WatsonxNotConfigured:
        return None
    except watsonx.WatsonxRequestError as exc:
        return {
            "text": _template_fallback(simulation, focus_iso3),
            "source": "template",
            "error": f"watsonx: {exc}",
        }
    return {"text": text, "source": "watsonx"}


def _try_anthropic(simulation: dict[str, Any], focus_iso3: str | None) -> dict[str, str] | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=EXPLAINER_MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(simulation, focus_iso3)}],
        )
        text = "".join(part.text for part in msg.content if getattr(part, "type", None) == "text")
        return {"text": text.strip(), "source": "anthropic"}
    except Exception as exc:  # noqa: BLE001 - graceful degradation for the demo
        return {
            "text": _template_fallback(simulation, focus_iso3),
            "source": "template",
            "error": str(exc),
        }


def explain(simulation: dict[str, Any], focus_iso3: str | None = None) -> dict[str, str]:
    for provider in (_try_watsonx, _try_anthropic):
        result = provider(simulation, focus_iso3)
        # Ignore template-with-error fallbacks here so the chain can keep going
        # and let a working downstream provider win.
        if result and result.get("source") != "template":
            return result
    return {"text": _template_fallback(simulation, focus_iso3), "source": "template"}
