"""Tests for the /data-sources manifest endpoint."""

from fastapi.testclient import TestClient

from app.data_sources import manifest
from app.main import app


def test_manifest_lists_six_sources_with_all_required_fields():
    m = manifest()
    sources = m["sources"]
    assert len(sources) == 6
    required = {
        "name",
        "file",
        "source",
        "year",
        "n_records",
        "active",
        "note",
        "file_size_bytes",
        "file_mtime_iso",
    }
    for s in sources:
        assert required.issubset(s.keys()), f"missing fields in {s}"


def test_manifest_marks_eurostat_as_inactive_with_documented_reason():
    m = manifest()
    eurostat = next(s for s in m["sources"] if "Eurostat" in s["name"])
    assert eurostat["active"] is False
    assert "rho 0.573" in eurostat["note"]


def test_manifest_records_real_data_for_each_active_source():
    """Active sources must point at a present file with non-zero size."""
    m = manifest()
    for s in m["sources"]:
        if s["active"]:
            assert s["file_size_bytes"] > 0, f"{s['name']} file missing or empty"
            assert s["file_mtime_iso"] is not None
            assert s["n_records"] is not None and s["n_records"] > 0


def test_manifest_summary_reports_active_count():
    m = manifest()
    assert m["summary"]["active_sources"] == 5
    assert m["summary"]["total_sources"] == 6


def test_data_sources_endpoint_returns_200_with_payload():
    client = TestClient(app)
    r = client.get("/data-sources")
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    assert "summary" in body
    assert isinstance(body["sources"], list)
    assert len(body["sources"]) == 6
    assert any(s["name"].startswith("OpenFlights") for s in body["sources"])
