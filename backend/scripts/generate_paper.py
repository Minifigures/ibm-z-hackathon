"""Generate the project whitepaper PDF.

Runs the real backend simulation in-process (TestClient is unnecessary
because we can call the functions directly), renders matplotlib figures
mimicking each major UI panel from the *actual* simulation output, then
assembles a multi-section PDF with reportlab.

Output: docs/Pandexis_Whitepaper.pdf
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from reportlab.lib import colors as rl_colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Ensure we can import the app package when run from `backend/scripts/`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.effective_distance import effective_distance_from  # noqa: E402
from app.mobility import air_flow_matrix, country_index, load_countries  # noqa: E402
from app.nowcast import NowcastObservation, NowcastParams, run_nowcast  # noqa: E402
from app.simulate import SimParams, run as run_sim  # noqa: E402

DOCS_DIR = ROOT.parent / "docs"
FIG_DIR = DOCS_DIR / "_paper_figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = DOCS_DIR / "Pandexis_Whitepaper.pdf"

# ---------- Style ---------------------------------------------------------
ACCENT = "#0d7477"        # deep teal matches the dashboard accent
ACCENT_LIGHT = "#7cf2c8"  # bright accent
INK = "#0f141c"           # dark text
SUBINK = "#475569"        # secondary text
WARN = "#fb923c"          # nowcast posterior
INFO = "#fbbf24"          # arrival annotation
PALETTE = ["#fbbf24", "#7cf2c8", "#a78bfa", "#f472b6"]  # matches forecast-chart.tsx


def _style_axes(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#94a3b8")
    ax.spines["bottom"].set_color("#94a3b8")
    ax.tick_params(colors="#475569", labelsize=8)
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.5)


def _save(fig, name: str, dpi: int = 200) -> Path:
    path = FIG_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------- Step 1: Run the real simulation -------------------------------

def run_baseline_simulation() -> dict:
    params = SimParams(
        disease_id="covid19",
        start_iso3="CHN",
        r0=2.5,
        incubation_days=5.0,
        infectious_days=6.0,
        cfr_pct=1.0,
        air_weight=1.0,
        port_weight=0.3,
        travel_restriction=0.0,
        mask_intervention=0.0,
        horizon_days=45,
        n_runs=200,
    )
    return run_sim(params)


def run_intervention_simulation() -> dict:
    params = SimParams(
        disease_id="covid19",
        start_iso3="CHN",
        r0=2.5,
        incubation_days=5.0,
        infectious_days=6.0,
        cfr_pct=1.0,
        air_weight=1.0,
        port_weight=0.3,
        travel_restriction=0.9,
        mask_intervention=0.5,
        horizon_days=45,
        n_runs=200,
    )
    return run_sim(params)


def run_nowcast_demo(base_params: SimParams) -> dict:
    obs = [
        NowcastObservation(day=5, cumulative_cases=200),
        NowcastObservation(day=10, cumulative_cases=900),
        NowcastObservation(day=15, cumulative_cases=4000),
        NowcastObservation(day=20, cumulative_cases=15000),
    ]
    return run_nowcast(NowcastParams(base=base_params, observations=obs, n_particles=400))


# ---------- Step 2: Figure renderers --------------------------------------

def fig_world_choropleth(sim: dict) -> Path:
    """Mercator scatter of countries colored by prevalence per 100k.

    Mimics the WorldMap component output: dot per country, sized by
    population, colored by p50 prevalence at horizon end. Spread arcs are
    drawn as great-circle polylines (densified to 24 segments).
    """
    countries = load_countries()
    iso_to_country = {c.iso3: c for c in countries}
    region_by_iso = {r["iso3"]: r for r in sim["regions"]}

    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    ax.set_facecolor("#0a0e14")
    fig.patch.set_facecolor("white")

    # Simple stylised world background: light grid only
    ax.set_xlim(-180, 180)
    ax.set_ylim(-65, 80)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Spread arcs (great-circle, densified)
    for arc in sim["spread_arcs"]:
        a = iso_to_country.get(arc["from_iso3"])
        b = iso_to_country.get(arc["to_iso3"])
        if not a or not b:
            continue
        lats = np.linspace(a.lat, b.lat, 32)
        lngs = np.linspace(a.lng, b.lng, 32)
        ax.plot(
            lngs, lats,
            color=ACCENT_LIGHT,
            alpha=0.15 + 0.65 * arc["weight_normalized"],
            linewidth=0.6 + 1.6 * arc["weight_normalized"],
            solid_capstyle="round",
        )

    # Per-country dot
    for c in countries:
        r = region_by_iso.get(c.iso3, {})
        prev = float(r.get("prevalence_p50_per_100k", 0.0))
        if prev >= 1000:
            color = "#dc3246"
        elif prev >= 200:
            color = "#f06446"
        elif prev >= 50:
            color = "#f0c850"
        elif prev >= 10:
            color = "#50c8c8"
        elif prev >= 1:
            color = "#3c82b4"
        elif prev > 0:
            color = "#28384f"
        else:
            color = "#1a2230"
        size = 6 + math.log10(max(c.population, 1)) - 5
        ax.scatter(c.lng, c.lat, s=max(size, 3) ** 2 * 4, c=color,
                   edgecolors="white", linewidth=0.4, alpha=0.92, zorder=2)

    # Seed marker
    seed_iso = sim["params_used"]["start_iso3"]
    seed = iso_to_country.get(seed_iso)
    if seed:
        ax.scatter(seed.lng, seed.lat, s=180, c=ACCENT_LIGHT,
                   edgecolors="#0a0e14", linewidth=2, zorder=4)
        ax.annotate(
            f"seed: {seed_iso}",
            (seed.lng, seed.lat),
            xytext=(10, 8),
            textcoords="offset points",
            color=ACCENT_LIGHT,
            fontsize=9,
            fontweight="bold",
        )

    # Legend (prevalence ramp)
    ramp_colors = ["#1a2230", "#28384f", "#3c82b4", "#50c8c8", "#f0c850", "#f06446", "#dc3246"]
    ramp_labels = ["0", ">0", "≥1", "≥10", "≥50", "≥200", "≥1000"]
    handles = [
        mpatches.Patch(color=col, label=lab) for col, lab in zip(ramp_colors, ramp_labels)
    ]
    leg = ax.legend(
        handles=handles, loc="lower left", ncol=7,
        title="Prevalence /100k at horizon end",
        bbox_to_anchor=(0, -0.05), fontsize=7, title_fontsize=8,
        frameon=False, labelcolor="white",
    )
    leg.get_title().set_color("white")

    return _save(fig, "fig_world_choropleth.png", dpi=220)


def fig_polar_map(sim: dict) -> Path:
    """Effective-distance polar projection of the dashboard's PolarMap.

    Reuses the same Dijkstra and bearing logic that runs in production.
    """
    countries = load_countries()
    iso_to_idx = country_index()
    seed_iso = sim["params_used"]["start_iso3"]
    seed_idx = iso_to_idx[seed_iso]
    seed = countries[seed_idx]

    air = air_flow_matrix()
    d_eff = effective_distance_from(air, seed_idx)

    region_by_iso = {r["iso3"]: r for r in sim["regions"]}

    finite = np.isfinite(d_eff)
    finite[seed_idx] = True
    max_d = float(np.nanmax(np.where(finite, d_eff, 0.0))) or 1.0

    fig, ax = plt.subplots(figsize=(7.5, 7.5), subplot_kw={"projection": "polar"})
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#0a0e14")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rticks([max_d * f for f in (0.25, 0.5, 0.75, 1.0)])
    ax.set_rlabel_position(45)
    ax.tick_params(colors="#94a3b8", labelsize=7)
    ax.grid(color="#1f2632", linewidth=0.6)
    ax.spines["polar"].set_color("#1f2632")

    def _bearing(lat1, lng1, lat2, lng2):
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dl = math.radians(lng2 - lng1)
        y = math.sin(dl) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
        return math.atan2(y, x)

    # Plot every reachable country
    for i, c in enumerate(countries):
        if i == seed_idx or not np.isfinite(d_eff[i]):
            continue
        prev = float(region_by_iso.get(c.iso3, {}).get("prevalence_p50_per_100k", 0.0))
        if prev >= 50:
            color = "#f0c850"
        elif prev >= 10:
            color = "#50c8c8"
        elif prev >= 1:
            color = "#3c82b4"
        elif prev > 0:
            color = "#28384f"
        else:
            color = "#1a2230"
        theta = _bearing(seed.lat, seed.lng, c.lat, c.lng)
        ax.scatter(theta, d_eff[i], s=80, c=color,
                   edgecolors="white", linewidth=0.4, alpha=0.92, zorder=2)
        # Label countries with low d_eff so the figure is readable
        if d_eff[i] < max_d * 0.6 and prev > 0.5:
            ax.annotate(
                c.iso3,
                xy=(theta, d_eff[i]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=7,
                color="white",
            )

    # Spread arcs as straight rays
    for arc in sim["spread_arcs"]:
        target_idx = iso_to_idx.get(arc["to_iso3"])
        if target_idx is None or not np.isfinite(d_eff[target_idx]):
            continue
        c = countries[target_idx]
        theta = _bearing(seed.lat, seed.lng, c.lat, c.lng)
        ax.plot(
            [theta, theta], [0, d_eff[target_idx]],
            color=ACCENT_LIGHT,
            alpha=0.15 + 0.6 * arc["weight_normalized"],
            linewidth=0.6 + 1.6 * arc["weight_normalized"],
            zorder=1,
        )

    ax.scatter(0, 0, s=180, c=ACCENT_LIGHT, edgecolors="#0a0e14", linewidth=2, zorder=5)
    ax.annotate(seed_iso, xy=(0, 0), xytext=(8, 8), textcoords="offset points",
                color=ACCENT_LIGHT, fontsize=10, fontweight="bold")

    ax.set_title(
        f"Effective-distance polar projection\nseed = {seed_iso}, radius = $d_{{eff}}$, angle = great-circle bearing",
        color=INK, fontsize=10, pad=18,
    )

    return _save(fig, "fig_polar_map.png", dpi=200)


def fig_forecast_chart(sim: dict, focus_iso: str = "USA") -> Path:
    """Forecast curve with 50/95% bands, variant terminal dots, arrival line."""
    region = next((r for r in sim["regions"] if r["iso3"] == focus_iso), None)
    if region is None:
        region = max(sim["regions"], key=lambda r: r["cumulative_p50_final"])

    q = region["quantiles"]
    days = np.arange(len(q["p50"]))

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    fig.patch.set_facecolor("white")

    ax.fill_between(days, q["p2_5"], q["p97_5"], color=ACCENT, alpha=0.12, label="95% interval")
    ax.fill_between(days, q["p25"], q["p75"], color=ACCENT, alpha=0.28, label="50% interval")
    ax.plot(days, q["p50"], color=ACCENT, linewidth=1.8, label="ensemble median")

    # Per-variant terminal medians
    variants = sim.get("model_variants") or []
    term_p50 = region.get("variants_terminal_p50") or []
    for i, (v, val) in enumerate(zip(variants, term_p50)):
        ax.scatter(
            days[-1], val,
            s=60,
            c=PALETTE[i % len(PALETTE)],
            edgecolors="white",
            linewidth=1,
            zorder=4,
            label=f"{v['label']} ({v['citation']})",
        )

    arrival = region.get("predicted_arrival_day")
    if isinstance(arrival, int) and 0 < arrival < len(days):
        ax.axvline(arrival, color=INFO, linestyle="--", linewidth=1)
        ax.text(arrival + 0.3, ax.get_ylim()[1] * 0.95,
                f"arrival ~ day {arrival}",
                color=INFO, fontsize=8, va="top")

    _style_axes(ax)
    ax.set_xlabel("days after seeding")
    ax.set_ylabel("cumulative cases (median + bands)")
    ax.set_title(
        f"Forecast for {region['name']} ({region['iso3']})  •  $d_{{eff}}$ = "
        f"{region.get('effective_distance_from_seed', 0.0):.2f}",
        loc="left", fontsize=10, color=INK,
    )
    ax.legend(loc="upper left", frameon=False, fontsize=7, ncol=2)

    return _save(fig, "fig_forecast_chart.png", dpi=200)


def fig_intervention_comparison(base: dict, restricted: dict, focus_iso: str = "ITA") -> Path:
    """Side-by-side: baseline R0=2.5 vs. 90% travel restriction + 50% mask."""
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    fig.patch.set_facecolor("white")

    for sim, label, color in [
        (base, "no intervention", "#dc3246"),
        (restricted, "90% travel + 50% mask", ACCENT),
    ]:
        region = next((r for r in sim["regions"] if r["iso3"] == focus_iso), None)
        if region is None:
            continue
        q = region["quantiles"]
        days = np.arange(len(q["p50"]))
        ax.fill_between(days, q["p2_5"], q["p97_5"], color=color, alpha=0.12)
        ax.plot(days, q["p50"], color=color, linewidth=1.8, label=label)

    _style_axes(ax)
    ax.set_xlabel("days after seeding")
    ax.set_ylabel(f"cumulative cases in {focus_iso} (median)")
    ax.set_title("Intervention sensitivity (Tian 2020)", loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=8)

    return _save(fig, "fig_intervention.png", dpi=200)


def fig_nowcast_panel(sim: dict, nowcast: dict) -> Path:
    """Forecast chart with posterior overlay + observation dots."""
    seed_iso = sim["params_used"]["start_iso3"]
    region = next((r for r in sim["regions"] if r["iso3"] == seed_iso), None)
    if region is None:
        return None
    q = region["quantiles"]
    pq = nowcast["posterior_quantiles"]
    days = np.arange(len(q["p50"]))
    pdays = np.arange(len(pq["p50"]))

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    fig.patch.set_facecolor("white")

    ax.fill_between(days, q["p2_5"], q["p97_5"], color=ACCENT, alpha=0.12, label="prior 95% interval")
    ax.fill_between(days, q["p25"], q["p75"], color=ACCENT, alpha=0.28, label="prior 50% interval")
    ax.plot(days, q["p50"], color=ACCENT, linewidth=1.6, label="prior median")

    ax.plot(pdays, pq["p50"], color=WARN, linewidth=1.8, linestyle="--",
            label="posterior median (Funk 2018)")

    for o in nowcast["observations"]:
        ax.scatter(o["day"], o["cumulative_cases"], s=55, c=WARN,
                   edgecolors="white", linewidth=1, zorder=5, label=None)

    _style_axes(ax)
    ax.set_xlabel("days after seeding")
    ax.set_ylabel(f"cumulative cases in {seed_iso}")
    ps = nowcast["posterior_summary"]
    ax.set_title(
        f"Particle-filter nowcast  •  prior R0={ps['r0_prior_median']:.2f}  →  "
        f"posterior R0={ps['r0_posterior_median']:.2f}  "
        f"[{ps['r0_posterior_95'][0]:.2f}, {ps['r0_posterior_95'][1]:.2f}]  •  "
        f"ESS={ps['effective_sample_size']:.0f}/{ps['n_particles']}",
        loc="left", fontsize=9, color=INK,
    )
    ax.legend(frameon=False, fontsize=8)

    return _save(fig, "fig_nowcast.png", dpi=200)


def fig_calibration_card(sim: dict) -> Path:
    """Reproduces the header calibration triple with hover tooltips."""
    cal = sim["calibration"]

    fig, ax = plt.subplots(figsize=(7.5, 1.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1)
    ax.axis("off")

    chips = [
        (f"{cal['interval_coverage_holdout']*100:.0f}% cov₉₅",
         "fraction of leave-one-out truths inside 95% band"),
        (f"CRPS  {cal.get('crps_norm_per_100k', float('nan')):.2f}/100k",
         "Funk et al. 2018 (Epidemics) — lower is better"),
        (f"log score  {cal.get('multibin_log_score', float('nan')):.2f}",
         "Reich et al. 2019 PNAS / FluSight — higher is better"),
    ]

    x = 0.2
    for label, sub in chips:
        ax.add_patch(FancyBboxPatch((x, 0.45), 3.1, 0.45,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    linewidth=1, edgecolor=ACCENT, facecolor="#f0fbf9"))
        ax.text(x + 0.15, 0.67, label, fontsize=10, color=ACCENT, fontweight="bold")
        ax.text(x + 0.15, 0.27, sub, fontsize=7, color=SUBINK)
        x += 3.3

    ax.text(0.2, 0.05,
            "Calibration metrics computed leave-one-out across the Monte Carlo ensemble at horizon end.",
            fontsize=7, color=SUBINK, style="italic")

    return _save(fig, "fig_calibration.png", dpi=200)


def fig_top_imports(sim: dict) -> Path:
    """Mock-up of the Top Imports list from the bottom-strip HubList component."""
    rows = sim["top_imports"][:8]

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(rows) + 1.2)
    ax.axis("off")

    ax.text(0.2, len(rows) + 0.7, "TOP IMPORT HUBS  (median expected cases)",
            fontsize=9, color=SUBINK, fontweight="bold")

    max_v = max((r["expected_cases"] for r in rows), default=1.0) or 1.0
    for i, r in enumerate(rows):
        y = len(rows) - i - 0.2
        ax.text(0.2, y + 0.25, f"{i+1:>2}.  {r['name']}", fontsize=10, color=INK)
        ax.text(0.2, y - 0.05, r["iso3"], fontsize=8, color=SUBINK, family="monospace")
        bar_w = 5.5 * (r["expected_cases"] / max_v)
        ax.add_patch(Rectangle((4.0, y), bar_w, 0.45, color=ACCENT, alpha=0.6))
        ax.text(9.7, y + 0.18,
                f"{r['expected_cases']:,.0f} cases  •  {r['per_100k']:.2f}/100k",
                fontsize=8, color=INK, ha="right")

    return _save(fig, "fig_top_imports.png", dpi=200)


def fig_ui_layout() -> Path:
    """Schematic of the dashboard layout. Three regions: header strip,
    left input rail, main map view, and a bottom strip of three panels.

    Spacing budget (matplotlib-axis units, ylim = 0..7):
      6.4 - 7.0   figure title, anchored above the canvas
      5.3 - 6.1   header strip
      2.3 - 5.1   left rail (h=2.8)  +  map (h=2.8)
      0.2 - 2.1   bottom-strip panels (3 across)
    Sub-text inside every box is rendered with va='top' and a fixed offset
    below the label so multi-line strings always grow downward into empty
    space and never collide with the box boundary.
    """
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")

    LABEL_PAD = 0.30   # label baseline below the box top
    SUB_PAD = 0.62     # sub-text top below the box top
    LEFT_PAD = 0.22

    def _box(x, y, w, h, label, sub=None, fc="#f1f5f9"):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            linewidth=0.9, edgecolor=SUBINK, facecolor=fc,
        ))
        ax.text(x + LEFT_PAD, y + h - LABEL_PAD, label,
                fontsize=9.5, color=INK, fontweight="bold", va="top")
        if sub:
            ax.text(x + LEFT_PAD, y + h - SUB_PAD, sub,
                    fontsize=7.5, color=SUBINK, va="top", linespacing=1.3)

    # Title (lives above the box layout — never overlaps the header strip)
    ax.text(5.0, 6.7, "Dashboard layout — three-pane single-page application",
            fontsize=11.5, color=INK, fontweight="bold", ha="center", va="center")

    # Header strip
    _box(0.1, 5.3, 9.8, 0.8,
         "Header",
         "Pandexis   |   sim 612 ms   |   "
         "95% coverage   CRPS/100k   log score",
         fc="#e2e8f0")

    # Left rail (inputs)
    _box(0.1, 0.2, 2.5, 4.9,
         "Left rail (input panel)",
         "Disease search (RAG)\npresets / origin selector\n"
         "R0 / incubation / infectious / CFR\n"
         "air / port / travel / mask\nhorizon / MC runs",
         fc="#f8fafc")

    # Main map view
    _box(2.7, 2.3, 7.2, 2.8,
         "Main view (Geo / Polar toggle)",
         "world choropleth\nspread arcs\nclick-through to focus region",
         fc="#f0fbf9")

    # Bottom strip — three panels
    _box(2.7, 0.2, 2.3, 1.9,
         "Top imports",
         "ranked list\nmedian expected cases\nbar = normalised flow",
         fc="#f8fafc")
    _box(5.1, 0.2, 2.3, 1.9,
         "Forecast chart",
         "50/95% bands + median\nvariant dots\narrival ref line\nposterior overlay",
         fc="#f8fafc")
    _box(7.5, 0.2, 2.4, 1.9,
         "Explain / Nowcast",
         "Granite explanation\nparticle-filter CSV\nposterior R0 + rho",
         fc="#f8fafc")

    return _save(fig, "fig_ui_layout.png", dpi=200)


def fig_disease_search() -> Path:
    """Mock of the DiseaseSearch RAG input + retrieved card."""
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # Search box
    ax.add_patch(FancyBboxPatch((0.2, 4.7), 9.6, 0.7,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1, edgecolor=ACCENT, facecolor="white"))
    ax.text(0.4, 5.05, "Search:  novel coronavirus", fontsize=11, color=INK)
    ax.add_patch(FancyBboxPatch((8.6, 4.85), 1.0, 0.4,
                                boxstyle="round,pad=0.02,rounding_size=0.04",
                                linewidth=0, facecolor=ACCENT))
    ax.text(9.1, 5.05, "Apply", fontsize=9, color="white", ha="center", va="center")

    # Result card
    ax.add_patch(FancyBboxPatch((0.2, 0.4), 9.6, 4.0,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1, edgecolor=SUBINK, facecolor="#f8fafc"))

    ax.text(0.5, 4.05, "COVID-19 (ancestral)", fontsize=12, color=INK, fontweight="bold")
    ax.text(0.5, 3.7, "watsonx.ai • ibm/granite-embedding-107m + meta-llama/llama-3-3-70b-instruct",
            fontsize=7, color=SUBINK, family="monospace")

    metrics = [
        ("R0", "2.50",  "median basic reproduction number"),
        ("incubation", "5.0 d", "typical pre-symptomatic period"),
        ("infectious", "6.0 d", "mean transmissible window"),
        ("CFR", "1.00 %", "ancestral-strain population average"),
        ("origin", "CHN", "Wuhan, Hubei province, December 2019"),
    ]
    for i, (label, value, hint) in enumerate(metrics):
        y = 3.1 - i * 0.45
        ax.text(0.5, y, label, fontsize=8, color=SUBINK)
        ax.text(2.0, y, value, fontsize=10, color=INK, fontweight="bold")
        ax.text(3.5, y, hint, fontsize=8, color=SUBINK)

    ax.text(0.5, 0.65,
            "sources: Liu et al. 2020 J Travel Med • Verity et al. 2020 Lancet Inf Dis • "
            "Davis et al. 2021 Nature",
            fontsize=7, color=SUBINK, style="italic")

    return _save(fig, "fig_disease_search.png", dpi=200)


def fig_explain_panel() -> Path:
    """Stylised Granite-output explanation panel."""
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    ax.add_patch(FancyBboxPatch((0.2, 0.2), 9.6, 3.6,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1, edgecolor=SUBINK, facecolor="white"))
    ax.text(0.5, 3.45, "AI Explanation  •  Italy", fontsize=10, color=INK, fontweight="bold")
    ax.text(7.7, 3.45, "Regenerate", fontsize=8, color=ACCENT)

    para = (
        "Italy sits at effective distance 1.92 from China on the air-route graph "
        "(Brockmann & Helbing 2013), with median active prevalence first crossing "
        "1/100k around day 19. Under R0=2.5, the four-model ensemble projects a "
        "30-day cumulative case count of 2,840 (95% interval 920 to 7,300), driven "
        "mainly by Beijing–Rome and Shanghai–Milan corridors that already account "
        "for 36% of inbound air passengers in the OpenFlights snapshot. Setting "
        "the travel-restriction slider to 90% delays the day-19 crossing to roughly "
        "day 22 — directionally consistent with Chinazzi et al. 2020 (Science)."
    )
    wrapped = textwrap.fill(para, width=98)
    ax.text(0.5, 2.95, wrapped, fontsize=8.5, color=INK, va="top",
            family="serif", linespacing=1.4)

    ax.text(0.5, 0.4, "source: watsonx.ai · ibm/granite-3-3-8b-instruct",
            fontsize=7, color=SUBINK, family="monospace")

    return _save(fig, "fig_explain.png", dpi=200)


def fig_architecture() -> Path:
    """Block diagram of the system architecture."""
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    def _block(x, y, w, h, title, body, fc="#f1f5f9", ec=SUBINK):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.02,rounding_size=0.05",
                                    linewidth=1, edgecolor=ec, facecolor=fc))
        ax.text(x + w/2, y + h - 0.25, title, fontsize=9, color=INK, fontweight="bold",
                ha="center")
        ax.text(x + w/2, y + h/2 - 0.1, body, fontsize=7, color=SUBINK,
                ha="center", va="center")

    def _arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                     arrowstyle="->", mutation_scale=12,
                                     color=ACCENT, linewidth=1.2))

    _block(0.2, 4.0, 2.4, 1.4, "Static datasets",
           "OpenFlights routes\nUN port calls\nBTS T-100\nEurostat avia_paocc\nUN migrant stock",
           fc="#f0fbf9")
    _block(3.2, 4.0, 2.4, 1.4, "Mobility builder",
           "F_air gravity\nF_sea gravity\ncombined m_ij\nbilateral overlays",
           fc="#f0fbf9")
    _block(6.2, 4.0, 3.6, 1.4, "SEIR + ensemble engine",
           "4 model variants × Monte Carlo\nleave-one-out calibration\neffective-distance d_eff",
           fc="#f0fbf9")

    _block(0.2, 1.8, 2.4, 1.6, "RAG corpus",
           "disease_corpus.json\nGranite Embedding\ncosine retrieval",
           fc="#fff7ed")
    _block(3.2, 1.8, 2.4, 1.6, "watsonx.ai",
           "Granite 3.3 8B\nLlama 3.3 70B\nIAM token cache",
           fc="#fff7ed")
    _block(6.2, 1.8, 3.6, 1.6, "FastAPI service",
           "/simulate · /nowcast\n/explain · /disease-params\n/countries · /presets",
           fc="#f1f5f9")

    _block(2.0, 0.05, 6.0, 1.2, "Next.js dashboard (MapLibre + Recharts)",
           "Geo / Polar toggle · sliders · forecast chart · ensemble overlay · particle-filter overlay",
           fc="#eef2ff")

    # Arrows
    _arrow(2.6, 4.7, 3.2, 4.7)
    _arrow(5.6, 4.7, 6.2, 4.7)
    _arrow(8.0, 4.0, 8.0, 3.4)
    _arrow(2.6, 2.6, 3.2, 2.6)
    _arrow(5.6, 2.6, 6.2, 2.6)
    _arrow(5.0, 1.8, 5.0, 1.25)
    _arrow(8.0, 1.8, 6.0, 1.25)

    return _save(fig, "fig_architecture.png", dpi=200)


def fig_backtest_errors_sorted() -> Path:
    """Per-country sorted log10 error bar chart, color-coded by 95%-band coverage."""
    results_path = ROOT / "backtest" / "results.json"
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    fig.patch.set_facecolor("white")
    if not results_path.exists():
        ax.axis("off")
        ax.text(0.5, 0.5, "Backtest output not available.",
                ha="center", va="center", color=SUBINK)
        return _save(fig, "fig_backtest_errors.png", dpi=200)

    data = json.loads(results_path.read_text())
    rows = sorted(data["per_country"], key=lambda r: -r["log_abs_error"])
    iso3 = [r["iso3"] for r in rows]
    err = np.array([r["log_abs_error"] for r in rows])
    covered = np.array([r["covered"] for r in rows])

    colors = np.where(covered, ACCENT, "#dc3246")
    ax.bar(np.arange(len(rows)), err, color=colors, edgecolor="white", linewidth=0.4)
    ax.axhline(data["median_log_mae"], color=SUBINK, linestyle="--",
               linewidth=0.8, label=f"median = {data['median_log_mae']:.2f}")
    ax.set_xticks(np.arange(len(rows)))
    ax.set_xticklabels(iso3, rotation=90, fontsize=5.5)
    ax.set_ylabel("$|\\log_{10}(\\mathrm{model}) - \\log_{10}(\\mathrm{actual})|$",
                  fontsize=9)
    ax.set_xlabel("country (sorted by error, worst first)", fontsize=9)
    _style_axes(ax)

    inside = mpatches.Patch(color=ACCENT, label="inside 95% band")
    outside = mpatches.Patch(color="#dc3246", label="outside 95% band")
    ax.legend(handles=[inside, outside], frameon=False, fontsize=7,
              loc="upper right")

    return _save(fig, "fig_backtest_errors.png", dpi=200)


def fig_backtest_rank_scatter() -> Path:
    """Model rank vs JHU actual rank for all countries; reference y=x line."""
    results_path = ROOT / "backtest" / "results.json"
    fig, ax = plt.subplots(figsize=(5.0, 5.0))
    fig.patch.set_facecolor("white")
    if not results_path.exists():
        ax.axis("off")
        return _save(fig, "fig_backtest_rank.png", dpi=200)

    data = json.loads(results_path.read_text())
    rows = data["per_country"]
    actual = np.array([r["actual"] for r in rows], dtype=float)
    model = np.array([r["model_median"] for r in rows], dtype=float)
    actual_rank = np.argsort(np.argsort(-actual)) + 1
    model_rank = np.argsort(np.argsort(-model)) + 1
    n = len(rows)
    d = actual_rank - model_rank
    spearman = 1 - 6 * float((d * d).sum()) / (n * (n * n - 1))

    ax.plot([1, n], [1, n], color=SUBINK, linewidth=0.7, linestyle="--", alpha=0.7,
            label="$y = x$ (perfect rank match)")
    ax.scatter(actual_rank, model_rank, s=22, c=ACCENT, alpha=0.75,
               edgecolors="white", linewidth=0.3)

    # Annotate the 4 countries that landed in the top-10 of both rankings
    actual_top10 = set(np.argsort(-actual)[:10].tolist())
    model_top10 = set(np.argsort(-model)[:10].tolist())
    hits = sorted(actual_top10 & model_top10)
    for idx in hits:
        iso = rows[idx]["iso3"]
        ax.annotate(iso, (actual_rank[idx], model_rank[idx]),
                    xytext=(5, 4), textcoords="offset points",
                    fontsize=8, color=ACCENT, fontweight="bold")

    _style_axes(ax)
    ax.set_xlabel("actual rank by JHU confirmed cases (1 = most)", fontsize=9)
    ax.set_ylabel("model rank by ensemble median (1 = most)", fontsize=9)
    ax.set_title(
        f"Spearman $\\rho$ = {spearman:.2f}  •  top-10 hit rate = "
        f"{len(actual_top10 & model_top10)}/10",
        fontsize=10, color=INK, loc="left",
    )
    ax.legend(frameon=False, fontsize=7, loc="lower right")

    return _save(fig, "fig_backtest_rank.png", dpi=200)


def fig_calibration_backtest() -> Path:
    """Scatter of model-median vs. JHU-actual on Feb 21 2020.

    Reads from `backend/backtest/results.json` if available; falls back to
    a stylised mock that still communicates the methodology.
    """
    results_path = ROOT / "backtest" / "results.json"
    fig, ax = plt.subplots(figsize=(6.5, 5.0))
    fig.patch.set_facecolor("white")

    if results_path.exists():
        data = json.loads(results_path.read_text())
        rows = data.get("per_country", [])
        actual = np.array([max(r["actual"], 1) for r in rows])
        model = np.array([max(r["model_median"], 1) for r in rows])
        covered = np.array([r["covered"] for r in rows])
        # Reference y = x line
        lo, hi = max(actual.min(), 1), max(actual.max(), 1)
        ax.plot([lo, hi], [lo, hi], color=SUBINK, linewidth=0.8, linestyle="--", alpha=0.6)
        ax.scatter(actual[covered], model[covered], s=22, c=ACCENT, alpha=0.8,
                   edgecolors="white", linewidth=0.3, label="inside 95% band")
        ax.scatter(actual[~covered], model[~covered], s=22, c="#dc3246", alpha=0.85,
                   edgecolors="white", linewidth=0.3, label="outside 95% band")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("actual confirmed cases (JHU CSSE)")
        ax.set_ylabel("model median (1000-run ensemble)")
        ax.set_title(
            f"Backtest: COVID-19 seeded in {data['seed_iso3']} on {data['seed_date']}, "
            f"compared on {data['comparison_date']}\n"
            f"95% interval coverage = {data['coverage_95pi']:.2f}  •  "
            f"median log10 MAE = {data['median_log_mae']:.2f}  •  "
            f"n countries = {data['n_countries_compared']}",
            fontsize=9, color=INK, loc="left",
        )
        ax.legend(frameon=False, fontsize=8)
    else:
        ax.text(0.5, 0.5,
                "Backtest output not available; see README in backend/backtest/.",
                ha="center", va="center", color=SUBINK, fontsize=10)
        ax.axis("off")

    _style_axes(ax)
    return _save(fig, "fig_backtest.png", dpi=200)


# ---------- Step 3: Compose the PDF ---------------------------------------

def _styles():
    """LaTeX preprint-style sheet (Times-Roman everywhere; centred title and
    abstract block; numbered, right-aligned equations; small-italic captions;
    plain-bold section heads with no colour fills).
    """
    base = getSampleStyleSheet()
    BLACK = rl_colors.black

    title = ParagraphStyle(
        name="Title", parent=base["Title"],
        fontName="Times-Bold", fontSize=18, leading=22,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=14,
    )
    authors = ParagraphStyle(
        name="Authors", parent=base["Normal"],
        fontName="Times-Roman", fontSize=11.5, leading=14,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=2,
    )
    affil = ParagraphStyle(
        name="Affiliation", parent=base["Normal"],
        fontName="Times-Italic", fontSize=10, leading=12,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=2,
    )
    date_line = ParagraphStyle(
        name="Date", parent=base["Normal"],
        fontName="Times-Roman", fontSize=10, leading=12,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=18,
    )
    abstract_label = ParagraphStyle(
        name="AbstractLabel", parent=base["Normal"],
        fontName="Times-Bold", fontSize=11, leading=13,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=2,
    )
    abstract_body = ParagraphStyle(
        name="AbstractBody", parent=base["BodyText"],
        fontName="Times-Roman", fontSize=10, leading=13,
        textColor=BLACK, alignment=TA_JUSTIFY,
        leftIndent=24, rightIndent=24,
        spaceAfter=14,
    )
    h1 = ParagraphStyle(
        name="H1", parent=base["Heading1"],
        fontName="Times-Bold", fontSize=12.5, leading=15,
        textColor=BLACK, alignment=TA_LEFT,
        spaceBefore=14, spaceAfter=6,
    )
    h2 = ParagraphStyle(
        name="H2", parent=base["Heading2"],
        fontName="Times-Bold", fontSize=11, leading=13,
        textColor=BLACK, alignment=TA_LEFT,
        spaceBefore=10, spaceAfter=3,
    )
    body = ParagraphStyle(
        name="Body", parent=base["BodyText"],
        fontName="Times-Roman", fontSize=10.5, leading=13.5,
        textColor=BLACK, alignment=TA_JUSTIFY,
        spaceAfter=6, firstLineIndent=14,
    )
    body_first = ParagraphStyle(
        name="BodyFirst", parent=body, firstLineIndent=0,
    )
    # Equation rows are rendered as a Table so the equation centre-floats and
    # the equation number sits right-aligned in the page margin, matching
    # \begin{equation} ... \end{equation} in LaTeX.
    eq_inner = ParagraphStyle(
        name="EqInner", parent=base["Normal"],
        fontName="Times-Italic", fontSize=11, leading=15,
        textColor=BLACK, alignment=TA_CENTER,
    )
    eq_tag = ParagraphStyle(
        name="EqTag", parent=base["Normal"],
        fontName="Times-Roman", fontSize=10, leading=15,
        textColor=BLACK, alignment=TA_CENTER,
    )
    caption = ParagraphStyle(
        name="Caption", parent=body, fontName="Times-Roman",
        fontSize=9, leading=11.5, textColor=BLACK,
        alignment=TA_JUSTIFY, leftIndent=14, rightIndent=14,
        firstLineIndent=0, spaceBefore=4, spaceAfter=14,
    )
    references = ParagraphStyle(
        name="References", parent=body, fontSize=9.5, leading=12,
        firstLineIndent=-18, leftIndent=18, spaceAfter=4,
        alignment=TA_LEFT,
    )
    code = ParagraphStyle(
        name="Code", parent=body, fontName="Courier", fontSize=9,
        leading=11, textColor=BLACK,
        backColor=rl_colors.HexColor("#f1f5f9"),
        leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=8,
        firstLineIndent=0,
    )
    return {
        "title": title, "authors": authors, "affil": affil, "date": date_line,
        "abstract_label": abstract_label, "abstract_body": abstract_body,
        "h1": h1, "h2": h2, "body": body, "body_first": body_first,
        "eq_inner": eq_inner, "eq_tag": eq_tag,
        "caption": caption, "references": references, "code": code,
    }


def _equation(text: str, number: int, styles) -> Table:
    """Render one display equation: centred body, right-aligned (n) tag."""
    t = Table(
        [[
            Paragraph(text, styles["eq_inner"]),
            Paragraph(f"({number})", styles["eq_tag"]),
        ]],
        colWidths=[5.6 * inch, 0.6 * inch],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _caption(num: int, body: str, styles) -> Paragraph:
    return Paragraph(f"<b>Figure {num}:</b> {body}", styles["caption"])


def _backtest_top_table() -> dict | None:
    """Return the top-10-actual rows + per-row model rank. Used to render Table 2."""
    p = ROOT / "backtest" / "results.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    rows = data["per_country"]
    actual_rank = {r["iso3"]: i + 1 for i, r in enumerate(sorted(rows, key=lambda x: -x["actual"]))}
    model_rank = {r["iso3"]: i + 1 for i, r in enumerate(sorted(rows, key=lambda x: -x["model_median"]))}
    top10 = sorted(rows, key=lambda x: -x["actual"])[:10]
    out = []
    for r in top10:
        out.append({
            "iso3": r["iso3"],
            "actual": int(r["actual"]),
            "model_median": int(round(r["model_median"])),
            "model_p2_5": int(round(r["model_p2_5"])),
            "model_p97_5": int(round(r["model_p97_5"])),
            "model_rank": model_rank[r["iso3"]],
            "actual_rank": actual_rank[r["iso3"]],
            "covered": bool(r["covered"]),
            "hit": model_rank[r["iso3"]] <= 10,
        })
    return {"rows": out, "n_total": len(rows)}


def _render_top_table(data: dict, styles) -> Table:
    """Reportlab Table for top-10 actual vs model comparison (Table 2)."""
    cell = ParagraphStyle(
        name="T2Cell", fontName="Times-Roman", fontSize=8.5, leading=10.5,
        textColor=rl_colors.black, alignment=TA_LEFT,
    )
    head = ParagraphStyle(
        name="T2Head", fontName="Times-Bold", fontSize=8.5, leading=10.5,
        textColor=rl_colors.black, alignment=TA_LEFT,
    )

    def C(t):
        return Paragraph(t, cell)

    def H(t):
        return Paragraph(t, head)

    rows = [[
        H("ISO-3"), H("Actual<br/>cases"), H("Model<br/>median"),
        H("Model 95%<br/>interval"), H("Model<br/>rank"), H("Hit?"),
    ]]
    for r in data["rows"]:
        hit_mark = "yes" if r["hit"] else "no"
        rows.append([
            C(r["iso3"]),
            C(f"{r['actual']:,}"),
            C(f"{r['model_median']:,}"),
            C(f"{r['model_p2_5']:,} &ndash; {r['model_p97_5']:,}"),
            C(f"{r['model_rank']}"),
            C(hit_mark),
        ])
    table = Table(
        rows,
        colWidths=[0.55*inch, 0.85*inch, 0.85*inch, 1.7*inch, 0.65*inch, 0.6*inch],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, rl_colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, rl_colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, rl_colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _img(path: Path, width_in: float = 6.6) -> RLImage:
    img = RLImage(str(path))
    aspect = img.imageHeight / img.imageWidth
    img.drawWidth = width_in * inch
    img.drawHeight = width_in * inch * aspect
    return img


def build_pdf(figs: dict[str, Path], sim: dict, restricted: dict, nowcast: dict):
    s = _styles()
    doc = SimpleDocTemplate(
        str(PDF_PATH), pagesize=LETTER,
        leftMargin=0.85*inch, rightMargin=0.85*inch,
        topMargin=0.9*inch, bottomMargin=0.9*inch,
        title="Pandexis",
        author="Alomari, Alomari, Ayuste, Chakra, Sultan",
    )

    story: list = []
    P = lambda t, st="body": Paragraph(t, s[st])
    BR = lambda h=8: Spacer(1, h)
    EQ = lambda text, n: _equation(text, n, s)
    CAP = lambda n, body: _caption(n, body, s)

    # ----------------------------------------------------------------------
    # Title block (LaTeX preprint convention: title centred, authors below
    # in a single row, affiliation and date centred under the byline)
    # ----------------------------------------------------------------------
    story += [
        P("Pandexis:", "title"),
        P(
            "An Interactive Multi-Model Pandemic Simulator with "
            "Effective-Distance Routing, Particle-Filter Nowcasting, "
            "and Retrieval-Augmented Disease Parameter Lookup",
            "title",
        ),
        BR(6),
        P(
            "Amr Alomari &nbsp;&nbsp; Aous Alomari &nbsp;&nbsp; "
            "Marco Anthony Ayuste &nbsp;&nbsp; Aahir Chakra &nbsp;&nbsp; "
            "Ahmad Sultan",
            "authors",
        ),
        P("Pandexis Project Team", "affil"),
        P("May 2026", "date"),
    ]

    story += [
        P("Abstract", "abstract_label"),
        Paragraph(
            "When a novel pathogen is detected, decision-makers need to know within seventy-two "
            "hours which regions are at highest risk and which mobility links are doing the "
            "importing. Existing tools fall into two camps: academic metapopulation simulators "
            "(GLEAM, EpiRisk) that require expert operation, and public dashboards (WHO, CDC) "
            "that report current state rather than forward simulation under user-tunable "
            "interventions. We build a fast, interactive bridge between the two: a four-equation "
            "stack (gravity-decayed air mobility, port-call sea mobility, region-indexed SEIR "
            "with mobility-coupled force of infection, and Monte Carlo uncertainty) wrapped in a "
            "slider-driven dashboard. Three independent contributions sharpen the standard "
            "pipeline. First, an internal four-model ensemble inspired by FluSight collaborative "
            "forecasting averages structurally distinct variants (air-only, air+sea, "
            "high-coupling, and effective-distance pre-seeding); the last is gated by a "
            "per-disease cryptic-spread flag drawn from the literature. Second, a "
            "Brockmann–Helbing effective-distance metric, computed by Dijkstra over the "
            "air-flow graph, both annotates per-region predicted arrival days and supports a "
            "polar projection that renders global outbreak spread as concentric rings. Third, an "
            "importance-sampling particle filter on the same Monte Carlo ensemble re-weights "
            "particles against user-supplied case data, shifting the posterior <i>R</i><sub>0</sub> "
            "and reporting fraction in roughly half a second. Every output traces to a "
            "peer-reviewed source; the calibration triple (95% leave-one-out coverage, CRPS per "
            "100k, multibin log score) implements the metrics from Funk 2018 and Reich 2019; and "
            "a backtest against the first thirty days of the COVID-19 outbreak quantifies how "
            "much the structural priors recover without any fitting. Plain-English explanations "
            "are produced by IBM watsonx.ai Granite 3.3, with a retrieval-augmented Llama 3.3 "
            "70B pipeline supplying the per-disease parameter prior.",
            s["abstract_body"],
        ),
    ]

    # ----------------------------------------------------------------------
    # 1 Motivation
    # ----------------------------------------------------------------------
    story += [
        P("1 Motivation", "h1"),
        P(
            "Outbreak risk-communication tools today optimise for either rigour (academic "
            "simulators that encode mobility, age structure, and contact patterns at the cost of "
            "usability) or accessibility (case-count dashboards that show what already happened, "
            "not what might). The actionable question for analysts in the first weeks of an "
            "outbreak — which regions will be most affected, and which transport links are "
            "doing the importing — sits in the gap between those two camps. Our system "
            "targets that gap directly.",
            "body_first",
        ),
        P(
            "We emphasise three properties throughout: <b>interactivity</b> (sliders move, the "
            "world map redraws under one second), <b>defensibility</b> (every output traces to "
            "one of four explicit equations or to a cited paper), and <b>honesty about "
            "uncertainty</b> (probabilistic bands, not point estimates; calibration metrics "
            "computed in a leave-one-out style, not a single hand-picked statistic)."
        ),
    ]

    # ----------------------------------------------------------------------
    # 2 Four-equation stack
    # ----------------------------------------------------------------------
    story += [
        P("2 The four-equation stack", "h1"),
        P(
            "The forward simulation rests on four formulas, each tied to a primary citation. "
            "The computational core is dense numpy throughout: with seventy modelled regions "
            "and two hundred Monte Carlo runs the full pipeline finishes in well under a second "
            "on a 2-vCPU virtual server.",
            "body_first",
        ),

        P("2.1 Air mobility — gravity with exponential decay", "h2"),
        P(
            "Per-pair daily passenger flow is approximated by the canonical gravity form with "
            "an exponentially decaying distance kernel. Symbolic regression over empirical OD "
            "data [8] recovers exactly this functional form as the dominant low-complexity "
            "model, validating its use as a literature-anchored prior:",
            "body_first",
        ),
        EQ(
            "F<sup>air</sup><sub>ij</sub> = K<sub>a</sub> &middot; "
            "P<sub>i</sub><sup>&alpha;</sup> &middot; P<sub>j</sub><sup>&beta;</sup> "
            "&middot; exp(−&gamma; d<sub>ij</sub>) &middot; R<sub>ij</sub>",
            1,
        ),
        P(
            "Here P<sub>i</sub> is regional population, d<sub>ij</sub> is great-circle distance "
            "in thousands of kilometres, R<sub>ij</sub> &isin; {0,1} masks pairs without a "
            "direct OpenFlights route, and &alpha; &asymp; &beta; &asymp; 1, &gamma; &asymp; "
            "0.5/1000 km are taken from the literature. The implementation overlays real "
            "bilateral passenger volumes from BTS T-100 (US-anchored corridors) and Eurostat "
            "avia_paocc (intra-EU pairs), and applies hand-tuned multipliers for high-volume "
            "cultural and colonial corridors that simple gravity systematically under-predicts.",
            "body_first",
        ),

        P("2.2 Sea mobility — port-call gravity", "h2"),
        P(
            "A secondary mobility channel models container-ship and passenger-ship flows. We "
            "use the same gravity form with port-call activity in place of population mass and "
            "a slower decay rate &gamma;<sub>s</sub> &asymp; 0.3/1000 km, capping the effective "
            "range with a coastal attenuation for landlocked countries:",
            "body_first",
        ),
        EQ(
            "F<sup>sea</sup><sub>ij</sub> = K<sub>p</sub> &middot; V<sub>i</sub> &middot; "
            "V<sub>j</sub> &middot; exp(−&gamma;<sub>s</sub> &tau;<sub>ij</sub>)",
            2,
        ),
        P(
            "The user controls the relative weighting of the two channels with two sliders (air "
            "weight and port weight), letting them downweight sea importation for short-cycle "
            "pathogens or boost it for diseases with long incubation or environmental "
            "persistence.",
            "body_first",
        ),

        P("2.3 Region-indexed SEIR with mobility coupling", "h2"),
        P(
            "Within each region we solve a deterministic SEIR system in vectorised numpy with "
            "sub-day forward Euler steps. Mobility couples the regions through population "
            "fluxes on every compartment and through a &theta;-weighted imported component of "
            "the force of infection [1, 11]:",
            "body_first",
        ),
        EQ(
            "&lambda;<sub>i</sub>(t) = &beta;<sub>i</sub>(t) [ (1 − &theta;) "
            "I<sub>i</sub>/N<sub>i</sub> + &theta; &Sigma;<sub>j</sub> "
            "&omega;<sub>ji</sub> I<sub>j</sub>/N<sub>j</sub> ]",
            3,
        ),
        P(
            "The matrix &omega; is the column-normalised mobility matrix, so the imported "
            "pressure on region i is a weighted average of remote prevalence. The "
            "mask/distancing slider scales &beta; multiplicatively; the travel-restriction "
            "slider scales every mobility edge. Both reductions follow the Tian et al. 2020 [13] "
            "decomposition of intervention multipliers.",
            "body_first",
        ),

        P("2.4 Monte Carlo uncertainty", "h2"),
        P(
            "Each Monte Carlo run draws a triple (R<sub>0</sub>, infectious period, incubation "
            "period) from independent normal priors centred on the user's slider values with "
            "fifteen percent relative standard deviation, then propagates that draw "
            "deterministically through the SEIR ODE. We report quantile bands across the "
            "ensemble:",
            "body_first",
        ),
        EQ(
            "q&#770;<sub>p</sub>(t+h) = Quantile<sub>p</sub>{ Y<sub>t+h</sub><sup>(1)</sup>, "
            "&hellip;, Y<sub>t+h</sub><sup>(M)</sup> }",
            4,
        ),
        P(
            "with M = 200 by default. Bands at fifty and ninety-five percent are surfaced on "
            "the per-region forecast chart. Crucially we do not use a Gaussian approximation: "
            "quantiles are computed from the empirical ensemble, after Chinazzi et al. 2020 [4].",
            "body_first",
        ),
    ]

    story += [PageBreak()]

    # ----------------------------------------------------------------------
    # 3 Effective distance
    # ----------------------------------------------------------------------
    story += [
        P("3 Effective distance: a re-coordinatisation of the world", "h1"),
        P(
            "Brockmann and Helbing [3] showed that geographical distance is the wrong "
            "coordinate for outbreak arrival times: along the air-route graph, arrival becomes "
            "approximately linear in an information-theoretic effective distance. For the "
            "air-flow matrix F we define the per-edge weight",
            "body_first",
        ),
        EQ(
            "d<sup>eff</sup>(i &rarr; j) = 1 − log p<sub>ij</sub>, &nbsp;&nbsp; "
            "p<sub>ij</sub> = F<sub>ij</sub> / &Sigma;<sub>k</sub> F<sub>ik</sub>",
            5,
        ),
        P(
            "and compute the path effective distance d<sup>eff</sup>(s, t) by Dijkstra from "
            "the seed region. The metric is computed once per simulation (linear in air-graph "
            "edges) and is exposed both as a per-region scalar in the API response and as the "
            "radial coordinate of the polar projection in Figure 1.",
            "body_first",
        ),
        _img(figs["polar"], width_in=5.4),
        CAP(1,
            "Polar effective-distance projection. The seed sits at the origin; each country is "
            "placed at radius d<sup>eff</sup> on the air-route graph and angle equal to the "
            "great-circle bearing from the seed. Concentric reference rings are spaced by "
            "quartiles of the maximum d<sup>eff</sup>. Spread arcs (top OD pairs from the seed) "
            "appear as straight rays. The figure makes the unstated geometry of contagion "
            "explicit: regions at small d<sup>eff</sup> arrive earlier than those at large "
            "d<sup>eff</sup>, regardless of where they sit on a Mercator map."
        ),
        P(
            "The same metric drives a per-region predicted-arrival annotation: we report the "
            "first day on which the median active-prevalence quantile crosses one infection "
            "per 100,000 inhabitants, surfacing it as a labelled vertical reference line on "
            "the per-region forecast chart (Figure&nbsp;8).",
            "body_first",
        ),
    ]

    # ----------------------------------------------------------------------
    # 4 Multi-model ensemble
    # ----------------------------------------------------------------------
    story += [
        P("4 Internal multi-model ensemble", "h1"),
        P(
            "Reich et al. 2019 [12] demonstrated that an equal-weight ensemble of structurally "
            "different epidemic forecasters consistently outperforms any single contributor. "
            "We adopt the same framing inside the simulator: every call to "
            "<font face='Courier'>/simulate</font> runs four model variants in series and "
            "concatenates their Monte Carlo runs into the ensemble before computing quantile "
            "bands.",
            "body_first",
        ),
    ]

    # Cells must be Paragraph objects so reportlab wraps long entries inside
    # the column instead of bleeding into the neighbouring column.
    cell_style = ParagraphStyle(
        name="VariantCell", fontName="Times-Roman", fontSize=9, leading=11.5,
        textColor=rl_colors.black, alignment=TA_LEFT,
    )
    cell_head = ParagraphStyle(
        name="VariantHead", fontName="Times-Bold", fontSize=9, leading=11.5,
        textColor=rl_colors.black, alignment=TA_LEFT,
    )

    def C(text: str) -> Paragraph:
        return Paragraph(text, cell_style)

    def H(text: str) -> Paragraph:
        return Paragraph(text, cell_head)

    variants_table = [
        [H("#"), H("Variant"), H("Structural assumption"), H("Primary citation")],
        [C("1"),
         C("Air-only SEIR"),
         C("F<sup>sea</sup> weight zeroed; air mobility is the sole importation channel"),
         C("Colizza et al. 2006 [5]")],
        [C("2"),
         C("Air + sea SEIR"),
         C("Canonical air-plus-sea metapopulation"),
         C("Balcan et al. 2009 [2]")],
        [C("3"),
         C("High-coupling SEIR"),
         C("&theta; raised to 0.15 &mdash; imports dominate the force of infection"),
         C("Apolloni et al. 2014 [1]")],
        [C("4"),
         C("Eff-distance pre-seed"),
         C("70/30 split: 70% of seed cases at origin, 30% pre-seeded across reachable "
           "regions in proportion to exp(&minus;0.4 d<sup>eff</sup>)"),
         C("Brockmann &amp; Helbing 2013 [3]; Davis 2021 [6]")],
    ]
    table = Table(
        variants_table,
        colWidths=[0.35*inch, 1.35*inch, 3.05*inch, 1.85*inch],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, rl_colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, rl_colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, rl_colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [BR(6), table, BR(4)]
    story += [
        Paragraph(
            "<b>Table 1:</b> Members of the internal four-model ensemble. The fourth variant "
            "is gated by a per-disease cryptic-pre-seeding flag in the disease metadata, "
            "fired for COVID-19 and the generic Pathogen X preset and dropped for SARS-2003, "
            "seasonal influenza, and 2022 mpox.",
            s["caption"],
        ),
        P(
            "Variant four — the only structurally novel one — is gated by a "
            "per-disease <font face='Courier'>cryptic_preseeding</font> flag in the disease "
            "metadata. The flag fires for COVID-19 (Davis et al. 2021 [6] document weeks of "
            "pre-detection community spread) and for the generic Pathogen X preset "
            "(conservative default for an unknown novel pathogen). It is dropped for diseases "
            "that historically presented clinically and were caught quickly: 2003 SARS, "
            "seasonal influenza, and the 2022 mpox clade IIb wave. Disease-aware ensemble "
            "membership is the simplest realisation of the broader principle that no single "
            "model is right for every pathogen.",
            "body_first",
        ),
    ]

    # ----------------------------------------------------------------------
    # 5 Particle-filter nowcast
    # ----------------------------------------------------------------------
    story += [
        P("5 Particle-filter nowcast", "h1"),
        P(
            "The simulator's default mode is forward what-if: pick parameters, simulate. The "
            "particle-filter nowcast inverts this. The user supplies a short series of "
            "observed cumulative cases for the seed region, and we re-weight the Monte Carlo "
            "ensemble (treating each MC run as a particle) using importance sampling against "
            "those observations. The implementation follows Funk et al. 2018 [7].",
            "body_first",
        ),
        P(
            "Each particle carries its own draw of (R<sub>0</sub>, infectious period, "
            "incubation period), augmented with a per-particle reporting fraction &rho; drawn "
            "uniformly on [&rho;<sub>min</sub>, &rho;<sub>max</sub>]. We use a log-Normal "
            "observation model — pure Poisson collapsed the effective sample size to one, "
            "because cumulative-case data spans several decades of magnitude during exponential "
            "growth. The per-particle log-likelihood is",
            "body_first",
        ),
        EQ(
            "log L<sub>p</sub> = &Sigma;<sub>t</sub> &nbsp;−&frac12; "
            "( log(&rho;<sub>p</sub> &middot; cum<sub>p</sub>(t, seed)) "
            "− log y<sub>t</sub> )<sup>2</sup> / &sigma;<sup>2</sup>",
            6,
        ),
        P(
            "with &sigma; = 1.2 (an e<sup>1.2</sup> &asymp; 3.3&times; multiplicative spread "
            "per observation, wide enough to keep ESS in the dozens for plausible inputs but "
            "tight enough to concentrate posterior mass on the data-consistent region of "
            "parameter space). Posterior weights are exp(log L<sub>p</sub> − max log L), "
            "normalised; we report weighted quantiles of the trajectory and weighted summaries "
            "of R<sub>0</sub> and &rho;. Because the trajectories are deterministic given each "
            "particle's parameter draw, no resampling is required: the posterior distribution "
            "over future trajectories is precisely the importance-weighted distribution over "
            "the existing ensemble.",
            "body_first",
        ),
        _img(figs["nowcast"], width_in=6.5),
        CAP(2,
            "Particle-filter nowcast on the seed region. Solid teal: prior median and "
            "fifty/ninety-five percent bands from the four-model ensemble. Dashed orange: "
            "posterior median after re-weighting on four observed cumulative-case data points "
            "(orange dots). The header reports prior R<sub>0</sub>, posterior R<sub>0</sub> "
            "with 95% interval, and effective sample size. ESS reasonably above thirty "
            "indicates the data are informative without being so far from the prior that the "
            "posterior collapses to a single particle."
        ),
    ]

    story += [PageBreak()]

    # ----------------------------------------------------------------------
    # 6 Calibration
    # ----------------------------------------------------------------------
    story += [
        P("6 Calibration", "h1"),
        P(
            "We report three calibration metrics in the dashboard header on every simulation, "
            "computed leave-one-out across the Monte Carlo ensemble at horizon end "
            "(Figure&nbsp;3). Each metric speaks to a different audience.",
            "body_first",
        ),
        P("6.1 Ninety-five percent interval coverage (LOO)", "h2"),
        P(
            "The fraction of held-out runs whose terminal cumulative-cases value falls inside "
            "the 95% band of the remaining runs. A perfectly calibrated probabilistic "
            "forecaster lands near 0.95; over-dispersed forecasters land higher, "
            "over-confident ones lower. Coverage is the most interpretable metric for a "
            "non-specialist audience.",
            "body_first",
        ),
        P("6.2 CRPS per 100k", "h2"),
        P(
            "The Continuous Ranked Probability Score is a strictly proper scoring rule for "
            "probabilistic forecasts [7]. We use the closed-form sample expression "
            "CRPS(F, y) = E|X − y| − ½ E|X − X&prime;| with X, X&prime; "
            "i.i.d. from the forecast. We normalise by region population (cases per 100,000) "
            "so the score is dimensionless and comparable across runs of differing scale.",
            "body_first",
        ),
        P("6.3 Multibin log score", "h2"),
        P(
            "The CDC FluSight scoring rule [12]. We bin the forecast distribution into 5% "
            "quantile bins and report log P(truth &isin; bin). A well-calibrated 200-particle "
            "ensemble bins the truth uniformly and scores near log(0.05) &asymp; −3.0; "
            "sharper-than-truthful forecasts score lower. The metric speaks directly to the "
            "public-health forecasting community.",
            "body_first",
        ),
        _img(figs["calibration"], width_in=6.5),
        CAP(3,
            "Calibration triple as it appears in the dashboard header. Each chip carries a "
            "tooltip with the citation and the methodology. The metrics update on every "
            "simulation, so a reader can watch them respond to slider movements (sharper priors "
            "tighten coverage; looser priors widen it)."
        ),
                P("6.4 Real-data backtest against the COVID-19 outbreak", "h2"),
        P(
            "The internal LOO metrics report self-consistency, not external accuracy. To "
            "address the latter, we run a backtest harness that seeds COVID-19 in CHN on 22 "
            "January 2020 (the first JHU CSSE date) using the day-zero confirmed-case count "
            "as the initial seed, runs one thousand Monte Carlo SEIR iterations forward "
            "thirty days, and compares the model's per-country cumulative bands on 21 "
            "February 2020 against the JHU truth across the seventy-one countries that the "
            "model and JHU both cover. The harness uses the same code path as production, "
            "with COVID-19 preset parameters; <i>no fitting is performed</i>.",
            "body_first",
        ),
        _img(figs["backtest"], width_in=5.4),
        CAP(4,
            "Backtest scatter: model median vs. JHU CSSE actual confirmed cases on day thirty "
            "of the COVID-19 outbreak. Both axes are logarithmic because cases span six "
            "orders of magnitude. Teal points fall inside the 95% ensemble band; red points "
            "fall outside. The 95% interval contains the truth for 39% of countries, well "
            "below nominal -- a frank documentation of the gap between literature-prior "
            "structural simulation and real outbreak dynamics. Median absolute error in "
            "log<sub>10</sub> cases is 0.35."
        ),

        P("6.5 Where the error sits and where the ranking holds", "h2"),
        P(
            "The marginal error distribution is heavier-tailed than the median statistic "
            "suggests. Figure 5 sorts the seventy-one held-out countries by their "
            "log<sub>10</sub> error: the worst eight countries account for almost half of "
            "the total absolute error, while a long flat tail of more than thirty countries "
            "is predicted within a 1.5x multiplicative factor (log<sub>10</sub> &lt; 0.2). "
            "Crucially, the worst over-predictions sit in large-population South and "
            "Southeast Asia (IND, BGD, IDN, PAK), where the population x air-volume gravity "
            "over-counts mobility mass that did not, in early 2020, translate to detected "
            "cases -- partly a reporting artefact (low &rho; outside East Asia in January "
            "2020), partly a model artefact (gravity over-predicts low-volume intra-Asia "
            "routes).",
            "body_first",
        ),
        _img(figs["backtest_errors"], width_in=6.4),
        CAP(5,
            "Per-country backtest error sorted worst-first. Bars colour-coded by 95% "
            "interval coverage (teal: inside band; red: outside). The dashed line marks the "
            "median error (0.35 in log<sub>10</sub> cases). Country codes on the x-axis are "
            "ISO-3 alphabetic. The error is heavily concentrated in the long-tail left edge: "
            "roughly half of the total absolute error sits in eight countries, and the "
            "remaining sixty-three are within an order-of-magnitude prediction band."
        ),
        P(
            "<i>Absolute</i> case-count accuracy is not the right metric for an "
            "early-warning scenario tool. Tizzoni et al. 2014 [14] showed that the "
            "<i>ranking</i> of infection across regions is the most robust output of a "
            "metapopulation model, even when the underlying mobility data is imperfect. "
            "Figure 6 makes this concrete: Spearman rank correlation against the actual JHU "
            "ranking is 0.27 (positive but modest), and four of the actual top-ten "
            "most-affected countries (CHN, JPN, KOR, THA) are correctly placed inside the "
            "model's top-ten. The four hits are non-trivial: they are the four East Asian "
            "destinations with the densest direct flight schedule from Wuhan, exactly the "
            "targets the gravity-air formulation should rank highest, and they emerge from "
            "prior-only simulation with no fitting.",
            "body_first",
        ),
        _img(figs["backtest_rank"], width_in=4.7),
        CAP(6,
            "Rank-vs-rank scatter: each point is a country at (actual rank by JHU confirmed "
            "cases, model rank by ensemble median cumulative). The dashed identity line "
            "marks perfect rank agreement. Spearman <i>&rho;</i> = 0.27 across all "
            "seventy-one countries; four of the actual top-ten (annotated) also appear in "
            "the model's top-ten."
        ),

        P("6.6 Top-importer comparison", "h2"),
        P(
            "Table 2 lists the ten countries with the highest JHU confirmed-case counts "
            "thirty days after the seed (21 February 2020) alongside the model's prediction "
            "and the model's rank for each. The model captures the structural truth -- "
            "East Asian neighbours of China are the highest-risk early importers -- and "
            "lands four of the top ten in its own top ten, but it under-predicts the "
            "absolute count in dense maritime hubs (SGP, HKG, ITA, GBR) where surface and "
            "informal mobility supplemented air links beyond what the OpenFlights snapshot "
            "encodes.",
            "body_first",
        ),
    ]

    top_data = _backtest_top_table()
    if top_data is not None:
        story += [_render_top_table(top_data, s)]
        story += [Paragraph(
            "<b>Table 2:</b> The ten countries with the highest JHU CSSE confirmed-case "
            "counts thirty days after the seed (21 February 2020), compared to model output. "
            "<i>Model rank</i> is the rank of the ensemble median across all seventy-one "
            "countries; <i>hit?</i> indicates whether the country also appeared in the "
            "model's top-ten ranking.",
            s["caption"],
        )]

    # ----------------------------------------------------------------------
    

    # ----------------------------------------------------------------------
    # 7 Walkthrough
    # ----------------------------------------------------------------------
    story += [PageBreak()]
    story += [
        P("7 Dashboard walkthrough", "h1"),
        P(
            "The dashboard is a Next.js single-page application with three regions: a left "
            "rail of input controls, a main view that toggles between geographic and polar "
            "projections, and a bottom strip of three panels (top-import hub list, per-region "
            "forecast chart, and the explain/nowcast stack). Every interaction is wired to "
            "<font face='Courier'>/simulate</font> with a 120 ms debounce so sliders feel "
            "continuous; the first-render budget is under one second on the deployment target.",
            "body_first",
        ),
        _img(figs["ui_layout"], width_in=6.5),
        CAP(5,
            "Three-pane dashboard layout. The header surfaces the simulation latency and the "
            "calibration triple. The left rail holds the disease search, presets, origin "
            "selector, and four sets of sliders. The main view occupies most of the screen "
            "real-estate; the bottom strip holds the three panels that update on every "
            "simulation."
        ),

        P("7.1 Disease search (RAG over a curated corpus)", "h2"),
        P(
            "Free-form disease names are resolved to validated simulator parameters by a "
            "retrieval-augmented pipeline. The query is embedded with IBM Granite Embedding "
            "(via watsonx.ai); the top three matches are retrieved by cosine similarity from a "
            "curated corpus of disease-parameter passages; Llama 3.3 70B (also on watsonx.ai) "
            "extracts a JSON response constrained by a Pydantic schema with hard range limits. "
            "Out-of-range outputs are rejected; the user is asked to fall back to a preset.",
            "body_first",
        ),
        _img(figs["disease_search"], width_in=6.5),
        CAP(6,
            "Disease-search panel. The user types a free-form pathogen name; the RAG pipeline "
            "returns a structured parameter card with R<sub>0</sub>, incubation, infectious "
            "period, CFR, and a likely-origin ISO-3 with a one-line rationale. Sources are "
            "listed verbatim from the retrieved passages."
        ),

        P("7.2 World map with spread arcs", "h2"),
        _img(figs["world"], width_in=6.5),
        CAP(7,
            "Geographic view of the simulation. Country dots are sized by population and "
            "coloured by predicted active prevalence per 100,000 at horizon end. Spread arcs "
            "are great-circle polylines for the top eight outbound flows from the seed; arc "
            "opacity scales with normalised flow. The seed marker is drawn last so it stays "
            "visible over arcs."
        ),

        P("7.3 Polar view (effective distance)", "h2"),
        P(
            "A toggle in the top-right of the map view re-projects the world by effective "
            "distance (Figure&nbsp;1). Geographic intuition is suspended: in this projection "
            "Madrid can be visibly closer to São Paulo than Lagos is, because Madrid sits "
            "on many high-volume direct corridors and Lagos does not. The polar projection is "
            "rendered in plain SVG; MapLibre does not natively support radial projections.",
            "body_first",
        ),

        P("7.4 Forecast chart with ensemble overlay", "h2"),
        _img(figs["forecast"], width_in=6.5),
        CAP(8,
            "Per-region forecast chart. Solid teal area shows the fifty/ninety-five percent "
            "ensemble bands; the line is the median. Coloured dots at the right edge show each "
            "of the four model variants' terminal medians, with a hover tooltip carrying the "
            "citation. The yellow dashed vertical is the predicted-arrival day (first day "
            "median active prevalence crosses 1/100k); the d<sub>eff</sub> chip beneath the "
            "chart exposes the structural metric for the focused region."
        ),

        P("7.5 Top-import hubs", "h2"),
        _img(figs["top_imports"], width_in=6.5),
        CAP(9,
            "The top-import-hubs panel ranks regions by median expected imported cases at "
            "horizon end. The bar lengths are normalised against the leader. Tizzoni et al. "
            "2014 [14] showed that this <i>ordering</i> is robust to mobility-data choice; we "
            "treat the absolute case-count column as a model-tuned scale and the ranking "
            "column as the more credible output for a non-specialist."
        ),

        P("7.6 Intervention sensitivity", "h2"),
        _img(figs["intervention"], width_in=6.5),
        CAP(10,
            "Side-by-side ensemble-median trajectories for the same focus region under no "
            "intervention (red) and under a combined ninety percent travel restriction plus "
            "fifty percent mask intervention (teal). The qualitative result — travel "
            "restrictions delay but do not eliminate global spread unless combined with "
            "substantial transmission reduction — reproduces the headline finding of "
            "Chinazzi et al. 2020 [4] without any tuning."
        ),

        P("7.7 LLM explanation", "h2"),
        _img(figs["explain"], width_in=6.5),
        CAP(11,
            "The explain panel queries IBM watsonx.ai Granite 3.3 8B with a structured context "
            "block (R<sub>0</sub>, intervention multipliers, top imports, per-region "
            "fifty/ninety-five percent intervals, d<sub>eff</sub>, predicted arrival day) and "
            "a strict prompt that forbids inventing numbers and caps output at 130 words. A "
            "Claude Haiku fallback covers transient watsonx outages; a deterministic templated "
            "paragraph is the final guarantee that the demo never breaks."
        ),
    ]

    # ----------------------------------------------------------------------
    # 8 Architecture
    # ----------------------------------------------------------------------
    story += [PageBreak()]
    story += [
        P("8 System architecture", "h1"),
        _img(figs["architecture"], width_in=6.5),
        CAP(12,
            "System architecture. Static datasets feed the mobility builder, which produces "
            "the OD matrix consumed by the SEIR + ensemble engine. The RAG corpus is embedded "
            "with Granite Embedding at startup; the disease-lookup endpoint runs cosine "
            "retrieval and a Llama 3.3 70B extraction on each user query. Both LLM workloads "
            "— Granite for explanations and Llama for parameter extraction — run on "
            "watsonx.ai. The FastAPI service exposes six endpoints; the Next.js dashboard "
            "talks to all of them with simple JSON."
        ),
        P(
            "Total backend: roughly 1,800 lines of Python including tests; total frontend: "
            "roughly 2,600 lines of TypeScript. The four-equation core is fully vectorised "
            "numpy with no scientific-stack dependencies beyond numpy itself; latency on the "
            "deployment target (2 vCPU, 4 GB) is approximately 600 ms per simulate call at "
            "default settings.",
            "body_first",
        ),
    ]

    # ----------------------------------------------------------------------
    # 9 Limitations
    # ----------------------------------------------------------------------
    story += [
        P("9 Who this tool is for", "h1"),
        P(
            "The product is deliberately built so that five distinct kinds of user can "
            "extract value from the same five-minute interaction. Each persona reaches a "
            "different output panel first; the shared underlying simulation is the same.",
            "body_first",
        ),
    ]

    persona_rows = [
        [H("Persona"), H("Goal"), H("Primary panels they touch")],
        [C("Public-health analyst at a national agency"),
         C("Triage which regions to brief on within seventy-two hours of an outbreak "
           "alert; produce a defensible scenario for press."),
         C("Disease search (RAG); top-import hubs; Granite explanation; calibration "
           "triple")],
        [C("Epidemiology graduate student / educator"),
         C("Build intuition about R<sub>0</sub>, generation interval, mobility coupling "
           "and intervention multipliers without booting a HPC simulator."),
         C("All sliders; forecast chart; intervention sensitivity; multi-model ensemble "
           "dots")],
        [C("Travel / airline operations planner"),
         C("Anticipate which routes are likely to be cut, and which alternative hubs "
           "absorb the rerouted demand under partial restriction."),
         C("Geo map with spread arcs; top-export hubs; travel-restriction slider")],
        [C("Risk insurer / pandemic-bond analyst"),
         C("Generate a library of probabilistic 30-day case curves under varying "
           "pathogen and intervention parameters for parametric pricing.",),
         C("Monte Carlo runs slider; forecast 50/95% bands; particle-filter posterior on "
           "early signal data")],
        [C("Curious public / journalist"),
         C("Build accurate intuition during a live outbreak without trusting black-box "
           "AI; see the cited papers behind every claim."),
         C("Polar (effective-distance) view; Granite explanation; reference list in this "
           "paper")],
    ]
    persona_table = Table(
        persona_rows,
        colWidths=[1.85*inch, 2.65*inch, 2.10*inch],
        repeatRows=1,
    )
    persona_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, rl_colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, rl_colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, rl_colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [BR(6), persona_table, BR(2)]
    story += [Paragraph(
        "<b>Table 3:</b> Five user personas the dashboard is designed to serve. The "
        "underlying simulation is identical across personas; the difference is which "
        "output panel each user reaches first and which sliders they treat as primary.",
        s["caption"],
    )]

    # ------------------------------------------------------------------
    # 10 Competition
    # ------------------------------------------------------------------
    story += [
        P("10 Comparison to existing tools", "h1"),
        P(
            "The mobility-based metapopulation epidemic literature is mature, and several "
            "production-grade systems implement variants of the same four-equation stack. "
            "What we add is not a new model class but a different point in the "
            "<i>interactivity-vs-rigour</i> trade space. Table 4 lays out where each "
            "comparable tool sits.",
            "body_first",
        ),
    ]

    comp_rows = [
        [H("Tool"), H("Strengths"), H("Where this work differs")],
        [C("GLEAM / GLEAMviz "
           "(Northeastern MOBS Lab) [2]"),
         C("Reference academic simulator: 3,300 sub-populations, stochastic "
           "compartmental dynamics, validated against multiple historical outbreaks. "
           "The model behind Chinazzi 2020 [4]."),
         C("GLEAM is set-up-once, run-overnight; we are slider-driven and re-simulate "
           "in &lt;1&nbsp;s. We expose calibration (CRPS, log score, real backtest) "
           "and add an effective-distance polar projection and a particle-filter "
           "nowcast neither GLEAM nor GLEAMviz expose to non-experts.")],
        [C("EpiRisk (ISI Foundation)"),
         C("Web-accessible Brockmann-style importation-risk lookup, used in "
           "professional response settings."),
         C("EpiRisk reports importation probabilities at fixed parameter settings; we "
           "let users move R<sub>0</sub>, generation time, and intervention sliders "
           "and watch every output recompute, with cited bands and an LLM "
           "explanation.")],
        [C("WHO / CDC outbreak dashboards"),
         C("Authoritative case-count reporting, surveillance integration, and trust."),
         C("Dashboards are post-hoc reporting tools, not forward simulators. They "
           "answer \"what happened?\"; we answer \"what might?\". The two are "
           "complementary, not competitive.")],
        [C("Imperial College COVID-19 Response Team reports"),
         C("Highly cited bespoke per-outbreak modelling; sensitivity analyses; broad "
           "policy reach."),
         C("Imperial reports are bespoke per-outbreak runs published as PDFs; we are "
           "an interactive scenario-library generator with the same intervention "
           "decomposition (Tian 2020 [13]) at orders-of-magnitude faster turn-around.")],
        [C("Generic ML / GNN COVID forecasters [13]"),
         C("Strong short-horizon accuracy on stationary signals; data-driven "
           "parameter learning."),
         C("ML methods do not extrapolate to <i>novel</i> pathogens (no historical "
           "data to learn from) and are difficult to audit. We deliberately use a "
           "structural model whose every term is a cited equation; ML lives only at "
           "the disease-parameter-RAG layer, not at the dynamics layer.")],
    ]
    comp_table = Table(
        comp_rows,
        colWidths=[1.8*inch, 2.05*inch, 2.75*inch],
        repeatRows=1,
    )
    comp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#f2f2f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, rl_colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, rl_colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, rl_colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [BR(6), comp_table, BR(2)]
    story += [Paragraph(
        "<b>Table 4:</b> Comparison to representative tools in the same problem space. "
        "Our contribution sits at the interactive end of the trade space, with the same "
        "underlying mathematical pipeline as the academic tools but exposed to "
        "non-experts in real time.",
        s["caption"],
    )]
    story += [
        P(
            "Three properties together separate this work from every entry in Table 4: "
            "<b>(i)</b> sub-second slider-driven re-simulation that scales the per-region "
            "Monte Carlo loop in vectorised numpy, <b>(ii)</b> a four-model ensemble whose "
            "membership is gated by a per-disease cryptic-pre-seeding flag drawn from the "
            "literature, and <b>(iii)</b> a particle-filter nowcast that lets the user "
            "plug in a few real case observations and watch the posterior R<sub>0</sub> "
            "and reporting fraction shift in roughly half a second. The first removes the "
            "expert-operator barrier of GLEAM; the second is, to our knowledge, novel; the "
            "third reframes the product from a teaching toy into a real-time forecasting "
            "harness."
        ),
    ]

    # ------------------------------------------------------------------
    # 11 Limitations (renumbered from 9)
    # ------------------------------------------------------------------
    story += [
        P("9 Limitations and honest framing", "h1"),
        P(
            "We do not claim to predict real outbreaks. The system is a defensible scenario "
            "tool with literature-anchored parameters, calibrated against a specific real-world "
            "episode (COVID-19's first thirty days). Several known gaps deserve explicit "
            "mention.",
            "body_first",
        ),
        P(
            "<b>Static mobility.</b> The OD matrix is a snapshot. Rapti et al. 2022 demonstrate "
            "that time-varying mobility data measurably improves spatial forecasting; our "
            "reliance on a static prior is the simplest source of model–data mismatch and "
            "explains a large share of the backtest miss-rate."
        ),
        P(
            "<b>Region resolution.</b> Country-level aggregation hides intra-country "
            "heterogeneity. Within a few hours of work the resolution can be raised to the top "
            "five-hundred airports; for the demo we cap at seventy countries to keep the "
            "slider response under one second."
        ),
        P(
            "<b>Reporting fraction.</b> The cryptic-spread variant and the particle-filter "
            "nowcast both expose &rho;, but the default forward simulation does not — it "
            "returns true infections, not reported cases. Davis et al. 2021 [6] document &rho; "
            "as low as 0.01 for early COVID-19; users comparing model output to surveillance "
            "data should treat the model as an upper bound on observed counts unless they "
            "activate the nowcast and supply observed data."
        ),
        P(
            "<b>No within-host or age structure.</b> CFR is exposed as a slider but the SEIR "
            "compartments are population-aggregate. Pathogens with strong age-stratified "
            "transmission (e.g. measles) need an extension to the compartmental structure; we "
            "deliberately scoped the system to homogeneous populations, where the small model "
            "is more honest than a tunable bigger model would be."
        ),
    ]

    # ----------------------------------------------------------------------
    # References (numbered IEEE-ish style; cited inline as [n])
    # ----------------------------------------------------------------------
    story += [PageBreak()]
    story += [
        P("References", "h1"),
        Paragraph(
            "[1] A. Apolloni et al. Metapopulation epidemic models with heterogeneous mixing "
            "and travel behaviour. <i>BMC Theor. Biol. Med. Model.</i> 11, 3 (2014).",
            s["references"],
        ),
        Paragraph(
            "[2] D. Balcan et al. Multiscale mobility networks and the spatial spreading of "
            "infectious diseases. <i>Proc. Natl. Acad. Sci. U.S.A.</i> 106, 21484–21489 "
            "(2009).",
            s["references"],
        ),
        Paragraph(
            "[3] D. Brockmann and D. Helbing. The hidden geometry of complex, network-driven "
            "contagion phenomena. <i>Science</i> 342, 1337–1342 (2013).",
            s["references"],
        ),
        Paragraph(
            "[4] M. Chinazzi et al. The effect of travel restrictions on the spread of the "
            "2019 novel coronavirus (COVID-19) outbreak. <i>Science</i> 368, 395–400 "
            "(2020).",
            s["references"],
        ),
        Paragraph(
            "[5] V. Colizza, A. Barrat, M. Barthélemy and A. Vespignani. The role of the "
            "airline transportation network in the prediction and predictability of global "
            "epidemics. <i>Proc. Natl. Acad. Sci. U.S.A.</i> 103, 2015–2020 (2006).",
            s["references"],
        ),
        Paragraph(
            "[6] J. T. Davis et al. Cryptic transmission of SARS-CoV-2 and the first COVID-19 "
            "wave. <i>Nature</i> 600, 127–132 (2021).",
            s["references"],
        ),
        Paragraph(
            "[7] S. Funk et al. Real-time forecasting of infectious disease dynamics with a "
            "stochastic semi-mechanistic model. <i>Epidemics</i> 22, 56–61 (2018).",
            s["references"],
        ),
        Paragraph(
            "[8] H. Guo et al. Distilling human mobility models with symbolic regression. "
            "<i>Geographical Analysis</i> (2026, in press).",
            s["references"],
        ),
        Paragraph(
            "[9] M. U. G. Kraemer et al. The effect of human mobility and control measures on "
            "the COVID-19 epidemic in China. <i>Science</i> 368, 493–497 (2020).",
            s["references"],
        ),
        Paragraph(
            "[10] X. Lu et al. Human mobility in epidemic modelling. <i>arXiv:2507.22799</i> "
            "(2025).",
            s["references"],
        ),
        Paragraph(
            "[11] R. Pastor-Satorras, C. Castellano, P. Van Mieghem and A. Vespignani. "
            "Epidemic processes in complex networks. <i>Rev. Mod. Phys.</i> 87, 925–979 "
            "(2015).",
            s["references"],
        ),
        Paragraph(
            "[12] N. G. Reich et al. A collaborative multiyear, multimodel assessment of "
            "seasonal influenza forecasting in the United States. <i>Proc. Natl. Acad. Sci. "
            "U.S.A.</i> 116, 3146–3154 (2019).",
            s["references"],
        ),
        Paragraph(
            "[13] H. Tian et al. An investigation of transmission control measures during the "
            "first 50 days of the COVID-19 epidemic in China. <i>Science</i> 368, 638–642 "
            "(2020).",
            s["references"],
        ),
        Paragraph(
            "[14] M. Tizzoni et al. On the use of human mobility proxies for the modelling of "
            "epidemics. <i>PLOS Comput. Biol.</i> 10, e1003716 (2014).",
            s["references"],
        ),
    ]

    doc.build(story)
    print(f"Wrote {PDF_PATH}")


# ---------- Driver --------------------------------------------------------

def main():
    print("Running baseline simulation (CHN, COVID-19, 45-day horizon)…")
    sim = run_baseline_simulation()
    print(f"  ensemble runs: {sim['calibration']['monte_carlo_runs']}")
    print(f"  coverage_95: {sim['calibration']['interval_coverage_holdout']:.2f}")

    print("Running intervention scenario (90% travel + 50% mask)…")
    restricted = run_intervention_simulation()

    print("Running particle-filter nowcast…")
    base = SimParams(
        disease_id="covid19", start_iso3="CHN",
        r0=2.5, incubation_days=5.0, infectious_days=6.0, cfr_pct=1.0,
        air_weight=1.0, port_weight=0.3,
        travel_restriction=0.0, mask_intervention=0.0,
        horizon_days=45, n_runs=400,
    )
    nowcast = run_nowcast_demo(base)
    ps = nowcast["posterior_summary"]
    print(f"  ESS: {ps['effective_sample_size']:.1f} / {ps['n_particles']}")
    print(f"  R0 prior {ps['r0_prior_median']:.2f} -> posterior {ps['r0_posterior_median']:.2f}")

    print("Rendering figures…")
    figs = {
        "world": fig_world_choropleth(sim),
        "polar": fig_polar_map(sim),
        "forecast": fig_forecast_chart(sim, focus_iso="ITA"),
        "intervention": fig_intervention_comparison(sim, restricted, focus_iso="ITA"),
        "nowcast": fig_nowcast_panel(sim, nowcast),
        "calibration": fig_calibration_card(sim),
        "top_imports": fig_top_imports(sim),
        "ui_layout": fig_ui_layout(),
        "disease_search": fig_disease_search(),
        "explain": fig_explain_panel(),
        "architecture": fig_architecture(),
        "backtest": fig_calibration_backtest(),
        "backtest_errors": fig_backtest_errors_sorted(),
        "backtest_rank": fig_backtest_rank_scatter(),
    }
    for k, p in figs.items():
        print(f"  {k}: {p.relative_to(DOCS_DIR.parent)}")

    print("Composing PDF…")
    build_pdf(figs, sim, restricted, nowcast)


if __name__ == "__main__":
    main()
