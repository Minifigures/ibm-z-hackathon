import pytest

from app import watsonx


@pytest.fixture(autouse=True)
def _reset_token_cache():
    watsonx.reset_token_cache()
    yield
    watsonx.reset_token_cache()


def test_is_configured_requires_both_env_vars(monkeypatch):
    monkeypatch.delenv("WATSONX_APIKEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    assert watsonx.is_configured() is False

    monkeypatch.setenv("WATSONX_APIKEY", "k")
    assert watsonx.is_configured() is False

    monkeypatch.setenv("WATSONX_PROJECT_ID", "p")
    assert watsonx.is_configured() is True


def test_generate_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("WATSONX_APIKEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    with pytest.raises(watsonx.WatsonxNotConfigured):
        watsonx.generate("system", "user")


def test_generate_happy_path_uses_iam_token_then_text_endpoint(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    calls: list[tuple[str, dict, bytes]] = []

    def fake_post(url, body, headers, timeout=20.0):
        calls.append((url, headers, body))
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        if "/ml/v1/text/generation" in url:
            return {"results": [{"generated_text": "  Madrid is exposed via gravity.  "}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    out = watsonx.generate("system", "user", max_tokens=120)
    assert out == "Madrid is exposed via gravity."
    assert calls[0][0] == watsonx.IAM_TOKEN_URL
    assert calls[1][1]["Authorization"] == "Bearer TOK"
    assert b'"project_id": "fake-project"' in calls[1][2]


def test_generate_propagates_request_error(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    def fake_post(url, body, headers, timeout=20.0):
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        raise watsonx.WatsonxRequestError("HTTP 503: outage")

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    with pytest.raises(watsonx.WatsonxRequestError):
        watsonx.generate("system", "user")


def test_generate_raises_on_empty_results(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    def fake_post(url, body, headers, timeout=20.0):
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        return {"results": []}

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    with pytest.raises(watsonx.WatsonxRequestError):
        watsonx.generate("system", "user")


def test_iam_token_is_cached_within_expiry(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    calls = {"iam": 0}

    def fake_post(url, body, headers, timeout=20.0):
        if "iam.cloud.ibm.com" in url:
            calls["iam"] += 1
            return {"access_token": "TOK", "expires_in": 3600}
        return {"results": [{"generated_text": "ok"}]}

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    watsonx.generate("s", "u")
    watsonx.generate("s", "u")
    assert calls["iam"] == 1
