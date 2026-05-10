from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _sim_payload(**overrides):
    base = dict(
        disease_id="covid19",
        start_iso3="USA",
        r0=2.5,
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
    base.update(overrides)
    return base


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_countries_shape():
    r = client.get("/countries")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 70
    sample = rows[0]
    assert {"iso3", "name", "lat", "lng", "population", "hub"} <= sample.keys()


def test_presets_keys():
    r = client.get("/presets")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"covid19", "flu", "mpox", "sars", "pathogenx"}
    for v in data.values():
        assert {"id", "label", "r0", "incubation_days", "infectious_days", "cfr_pct"} <= v.keys()


def test_simulate_happy_path():
    r = client.post("/simulate", json=_sim_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_days"] == 15
    assert len(body["regions"]) >= 70
    assert len(body["top_imports"]) > 0


def test_simulate_rejects_unknown_iso():
    r = client.post("/simulate", json=_sim_payload(start_iso3="ZZZ"))
    assert r.status_code == 400


def test_simulate_lowercase_iso_normalized():
    r = client.post("/simulate", json=_sim_payload(start_iso3="usa"))
    assert r.status_code == 200


def test_simulate_validates_ranges():
    r = client.post("/simulate", json=_sim_payload(r0=99.0))
    assert r.status_code == 422
    r = client.post("/simulate", json=_sim_payload(travel_restriction=2.0))
    assert r.status_code == 422


def test_explain_returns_text_in_template_mode(monkeypatch):
    # Force the templated branch by clearing the API key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sim = client.post("/simulate", json=_sim_payload()).json()
    r = client.post("/explain", json={"simulation": sim, "focus_iso3": sim["top_imports"][0]["iso3"]})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "template"
    assert len(body["text"]) > 50


def test_explain_without_focus():
    sim = client.post("/simulate", json=_sim_payload()).json()
    r = client.post("/explain", json={"simulation": sim, "focus_iso3": None})
    assert r.status_code == 200
    assert "text" in r.json()
