import pytest
from pydantic import ValidationError

from src.config import Settings


def test_env_vars_map_to_expected_fields(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example:11434")
    monkeypatch.setenv("LLM_MODEL", "llama3.2-custom")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("MAX_AGENT_ITERATIONS", "20")
    monkeypatch.setenv("MAX_REACT_STEPS", "8")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "30")
    monkeypatch.setenv("RAG_API_BASE_URL", "http://example:8000")
    monkeypatch.setenv("RAG_API_KEY", "rag-test-key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PHOENIX_PORT", "7000")

    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://example:11434"
    assert settings.llm_model == "llama3.2-custom"
    assert settings.llm_temperature == 0.5
    assert settings.max_agent_iterations == 20
    assert settings.max_react_steps == 8
    assert settings.api_key == "test-key"
    assert settings.rate_limit_per_minute == 30
    assert settings.rag_api_base_url == "http://example:8000"
    assert settings.rag_api_key == "rag-test-key"
    assert settings.log_level == "DEBUG"
    assert settings.phoenix_port == 7000


def test_defaults_match_spec(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("API_KEY", "test-key")  # only required field, no safe default

    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.llm_model == "llama3.2"
    assert settings.llm_temperature == 0.0
    assert settings.max_agent_iterations == 10
    assert settings.max_react_steps == 5
    assert settings.rate_limit_per_minute == 60
    assert settings.rag_api_base_url == "http://localhost:8000"
    assert settings.rag_api_key == "dev-key-change-in-production"
    assert settings.log_level == "INFO"
    assert settings.phoenix_port == 6006


def test_api_key_is_required(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
