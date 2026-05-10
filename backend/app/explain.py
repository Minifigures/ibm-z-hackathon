"""LLM explainer for simulation outputs.

Calls IBM watsonx.ai (via the shared `watsonx_client`) when credentials are
present, falls back to a deterministic templated explanation otherwise so
the demo never breaks. The prompt is designed to be auditable: the model is
given the equation labels and the numeric outputs and is asked to translate
them into 1 to 2 short paragraphs of plain English.
"""

from __future__ import annotations

from typing import Any

from . import watsonx_client

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


def explain(simulation: dict[str, Any], focus_iso3: str | None = None) -> dict[str, str]:
    if not watsonx_client.is_configured():
        return {"text": _template_fallback(simulation, focus_iso3), "source": "template"}

    chat = watsonx_client.get_chat_model()
    if chat is None:
        return {"text": _template_fallback(simulation, focus_iso3), "source": "template"}

    user_text = (
        "Explain the simulator output below for a public-health audience. Reference "
        "the gravity mobility model and the SEIR transmission step where relevant. "
        "Stay under 130 words.\n\n"
        + _format_context(simulation, focus_iso3)
    )

    try:
        response = chat.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            params={"max_tokens": 400, "temperature": 0.3},
        )
        text = _extract_text(response).strip()
        return {"text": text, "source": "watsonx"}
    except Exception as exc:  # noqa: BLE001 - graceful degradation for the demo
        return {
            "text": _template_fallback(simulation, focus_iso3),
            "source": "template",
            "error": str(exc),
        }
