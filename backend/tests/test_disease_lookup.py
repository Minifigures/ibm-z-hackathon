from unittest.mock import MagicMock

from app import disease_lookup, watsonx_client


def _good_payload(label="Test Pox", r0=2.0, incubation=5, infectious=7, cfr=1.0):
    return (
        '{"label":"%s","r0":%s,"incubation_days":%s,"infectious_days":%s,'
        '"cfr_pct":%s,"sources":["WHO 2024"],"confidence":"high","notes":"Test entry."}'
        % (label, r0, incubation, infectious, cfr)
    )


def _wrap(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def _fake_emb_for_corpus():
    fake_emb = MagicMock()
    corpus_len = len(disease_lookup._load_corpus())
    fake_emb.embed_documents.side_effect = lambda texts: [[1.0, 0.0] for _ in texts]
    return fake_emb, corpus_len


def test_returns_unconfigured_when_no_credentials(monkeypatch):
    monkeypatch.delenv("WATSONX_APIKEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    out = disease_lookup.lookup("ebola")
    assert out["status"] == "unconfigured"


def test_rejects_empty_name(monkeypatch):
    monkeypatch.delenv("WATSONX_APIKEY", raising=False)
    out = disease_lookup.lookup("   ")
    assert out["status"] == "rejected"
    assert "empty" in out["message"].lower()


def test_hard_validation_rejects_out_of_range(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake")
    bad = _good_payload(r0=99.0)  # out of range
    fake_chat = MagicMock()
    fake_chat.chat.return_value = _wrap(bad)
    fake_emb, _ = _fake_emb_for_corpus()
    monkeypatch.setattr(watsonx_client, "get_chat_model", lambda: fake_chat)
    monkeypatch.setattr(watsonx_client, "get_embedding_model", lambda: fake_emb)

    out = disease_lookup.lookup("madeup-pathogen")
    assert out["status"] == "rejected"
    assert "validation" in out["message"].lower()


def test_rejects_unparseable_json(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake")
    fake_chat = MagicMock()
    fake_chat.chat.return_value = _wrap("the model rambled and did not return JSON")
    fake_emb, _ = _fake_emb_for_corpus()
    monkeypatch.setattr(watsonx_client, "get_chat_model", lambda: fake_chat)
    monkeypatch.setattr(watsonx_client, "get_embedding_model", lambda: fake_emb)

    out = disease_lookup.lookup("unknown-x")
    assert out["status"] == "rejected"
    assert "json" in out["message"].lower()


def test_propagates_model_error_object(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake")
    fake_chat = MagicMock()
    fake_chat.chat.return_value = _wrap('{"error": "Disease not found in literature."}')
    fake_emb, _ = _fake_emb_for_corpus()
    monkeypatch.setattr(watsonx_client, "get_chat_model", lambda: fake_chat)
    monkeypatch.setattr(watsonx_client, "get_embedding_model", lambda: fake_emb)

    out = disease_lookup.lookup("zzz-not-real")
    assert out["status"] == "rejected"
    assert "not found" in out["message"].lower()


def test_happy_path_returns_validated_params(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake")
    fake_chat = MagicMock()
    fake_chat.chat.return_value = _wrap(_good_payload(label="Ebola", r0=1.8, cfr=50.0))
    fake_emb, _ = _fake_emb_for_corpus()
    monkeypatch.setattr(watsonx_client, "get_chat_model", lambda: fake_chat)
    monkeypatch.setattr(watsonx_client, "get_embedding_model", lambda: fake_emb)

    out = disease_lookup.lookup("ebola")
    assert out["status"] == "ok"
    assert out["params"]["label"] == "Ebola"
    assert out["params"]["r0"] == 1.8
    assert out["params"]["cfr_pct"] == 50.0
    assert out["cached"] is False
    assert isinstance(out["retrieved"], list)
    assert len(out["retrieved"]) > 0


def test_caches_repeat_lookups_case_insensitively(monkeypatch):
    monkeypatch.setenv("WATSONX_APIKEY", "fake")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "fake")
    fake_chat = MagicMock()
    fake_chat.chat.return_value = _wrap(_good_payload())
    fake_emb, _ = _fake_emb_for_corpus()
    monkeypatch.setattr(watsonx_client, "get_chat_model", lambda: fake_chat)
    monkeypatch.setattr(watsonx_client, "get_embedding_model", lambda: fake_emb)

    first = disease_lookup.lookup("Test-Pox")
    second = disease_lookup.lookup("  test-pox  ")
    assert first["status"] == "ok"
    assert first["cached"] is False
    assert second["cached"] is True
    fake_chat.chat.assert_called_once()
