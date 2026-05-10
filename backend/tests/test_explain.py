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


def _clear_provider_env(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "WATSONX_APIKEY", "WATSONX_PROJECT_ID"):
        monkeypatch.delenv(key, raising=False)


def test_template_fallback_with_focus(monkeypatch):
    _clear_provider_env(monkeypatch)
    sim = _sim()
    iso3 = sim["top_imports"][0]["iso3"]
    out = explain(sim, focus_iso3=iso3)
    assert out["source"] == "template"
    assert iso3 in out["text"] or any(r["iso3"] == iso3 and r["name"] in out["text"] for r in sim["regions"])


def test_template_fallback_without_focus(monkeypatch):
    _clear_provider_env(monkeypatch)
    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"
    # The summary mentions at least one of the top three import region names.
    top_names = [r["name"] for r in sim["top_imports"][:3]]
    assert any(name in out["text"] for name in top_names)


def test_template_handles_unknown_focus(monkeypatch):
    _clear_provider_env(monkeypatch)
    sim = _sim()
    out = explain(sim, focus_iso3="ZZZ")
    # Falls through to the global summary path without raising.
    assert out["source"] == "template"
    assert len(out["text"]) > 0


def test_anthropic_path_falls_back_when_sdk_missing(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)  # force ImportError
    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"


def test_watsonx_provider_wins_when_configured(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")  # should be skipped

    from app import watsonx as wx_module

    monkeypatch.setattr(wx_module, "generate", lambda system, user, max_tokens=400: "Granite says: spread is mostly via air mobility from BRA.")

    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "watsonx"
    assert "Granite says" in out["text"]


def test_watsonx_request_error_falls_through_to_template(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    from app import watsonx as wx_module

    def boom(*args, **kwargs):
        raise wx_module.WatsonxRequestError("HTTP 500: simulated outage")

    monkeypatch.setattr(wx_module, "generate", boom)

    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"
    # The chain still produced a meaningful narrative.
    assert len(out["text"]) > 50


def test_watsonx_not_configured_falls_through(monkeypatch):
    _clear_provider_env(monkeypatch)
    # Only one of the two required vars set should keep watsonx disabled.
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    sim = _sim()
    out = explain(sim, focus_iso3=None)
    assert out["source"] == "template"
