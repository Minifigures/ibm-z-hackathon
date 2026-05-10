from app.explain import explain
from app.simulate import SimParams, run


def _sim():
    return run(
        SimParams(
            disease_id="covid19",
            start_iso3="BRA",
            r0=2.0,
            incubation_days=5.0,
            infectious_days=6.0,
            cfr_pct=1.0,
            air_weight=1.0,
            port_weight=0.3,
            travel_restriction=0.0,
            mask_intervention=0.0,
            horizon_days=15,
            n_runs=40,
        )
    )


def test_template_fallback_with_focus(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sim = _sim()
    iso3 = sim["top_imports"][0]["iso3"]
    out = explain(sim, focus_iso3=iso3)
    assert out["source"] == "template"
    assert iso3 in out["text"] or any(r["iso3"] == iso3 and r["name"] in out["text"] for r in sim["regions"])


def test_template_fallback_without_focus(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"
    # The summary mentions at least one of the top three import region names.
    top_names = [r["name"] for r in sim["top_imports"][:3]]
    assert any(name in out["text"] for name in top_names)


def test_template_handles_unknown_focus(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sim = _sim()
    out = explain(sim, focus_iso3="ZZZ")
    # Falls through to the global summary path without raising.
    assert out["source"] == "template"
    assert len(out["text"]) > 0


def test_anthropic_path_falls_back_when_sdk_missing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)  # force ImportError
    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"
