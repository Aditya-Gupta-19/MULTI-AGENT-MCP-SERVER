from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"
    llm_temperature: float = 0.0

    # Agent behavior
    max_agent_iterations: int = 10
    max_react_steps: int = 5

    # API
    api_key: str
    rate_limit_per_minute: int = 60

    # External RAG service (a separate, independently-run project — the rag_query
    # tool cannot function without it, but claude.md's own .env reference omits
    # this config, so it is added here to close that gap).
    rag_api_base_url: str = "http://localhost:8000"
    rag_api_key: str = "dev-key-change-in-production"

    # Observability
    log_level: str = "INFO"
    phoenix_port: int = 6006


settings = Settings()

(REPO_ROOT / "data" / "agent_logs").mkdir(parents=True, exist_ok=True)
