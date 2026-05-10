import json

import pytest

from app import watsonx


@pytest.fixture(autouse=True)
def _reset_token_cache():
    watsonx.reset_token_cache()
    yield
    watsonx.reset_token_cache()


def _chat_response(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


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


def test_generate_happy_path_posts_chat_messages_with_role_tags(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    calls: list[tuple[str, dict, bytes]] = []

    def fake_post(url, body, headers, timeout=20.0):
        calls.append((url, headers, body))
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        if "/ml/v1/text/chat" in url:
            return _chat_response("  Madrid is exposed via gravity.  ")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    out = watsonx.generate("you are a helpful analyst", "explain the spread", max_tokens=120)

    assert out == "Madrid is exposed via gravity."
    assert calls[0][0] == watsonx.IAM_TOKEN_URL
    chat_url, headers, body = calls[1]
    assert "/ml/v1/text/chat" in chat_url
    # Bumped API version landed.
    assert "version=2024-05-31" in chat_url
    assert headers["Authorization"] == "Bearer TOK"
    payload = json.loads(body.decode("utf-8"))
    assert payload["project_id"] == "fake-project"
    assert payload["max_tokens"] == 120
    assert payload["messages"][0] == {"role": "system", "content": "you are a helpful analyst"}
    assert payload["messages"][1] == {"role": "user", "content": "explain the spread"}


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


def test_generate_raises_on_empty_choices(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    def fake_post(url, body, headers, timeout=20.0):
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        return {"choices": []}

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    with pytest.raises(watsonx.WatsonxRequestError):
        watsonx.generate("system", "user")


def test_generate_raises_on_missing_assistant_content(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake-project")

    def fake_post(url, body, headers, timeout=20.0):
        if "iam.cloud.ibm.com" in url:
            return {"access_token": "TOK", "expires_in": 3600}
        return {"choices": [{"message": {"role": "assistant"}}]}

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
        return _chat_response("ok")

    monkeypatch.setattr(watsonx, "_http_post_json", fake_post)
    watsonx.generate("s", "u")
    watsonx.generate("s", "u")
    assert calls["iam"] == 1
