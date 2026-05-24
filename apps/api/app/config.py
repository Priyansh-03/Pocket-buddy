from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """Repo root `.env` pehle, phir `apps/api/.env` — monorepo root = `apps/` ke upar wala folder."""
    api_dir = Path(__file__).resolve().parent.parent  # .../apps/api
    root_dir = api_dir.parent.parent  # .../<repo> (parent of apps/)
    paths: list[str] = []
    root_env = root_dir / ".env"
    api_env = api_dir / ".env"
    if root_env.is_file():
        paths.append(str(root_env))
    if api_env.is_file():
        paths.append(str(api_env))
    if paths:
        return tuple(paths)
    return (str(api_dir / ".env"),)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg2://user:pass@localhost:5432/survival"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.0-flash"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    # Reasoning models (e.g. gpt-oss) default ~16k reasoning budget on OpenRouter → 402 on low credits.
    # None: auto (cap only for known reasoning slugs). 0: never send reasoning.* body.
    # Positive: hard cap for reasoning.max_tokens (still clamped to completion cap).
    openrouter_reasoning_max_tokens: int | None = None
    gemini_api_key: str = ""
    # Comma-separated; localhost vs 127.0.0.1 pairs are auto-expanded in main.py
    cors_origin: str = "http://localhost:5173,http://127.0.0.1:5173"
    credentials_encryption_key: str = ""
    # Per-request bounds for LLM HTTP calls (tool loops = multiple round-trips).
    llm_connect_timeout_seconds: float = 45.0
    llm_read_timeout_seconds: float = 300.0
    # Cap each completion (output) size — OpenRouter credits scale with this; use max_completion_tokens on OR.
    llm_max_output_tokens: int = 2048
    # If set (absolute or relative to apps/api), each /chat LLM run writes JSON traces under {dir}/{user_id}/{run_id}/
    llm_flow_trace_dir: str = ""
    llm_flow_trace_max_chars: int = 6000

    def openai_key_effective(self) -> str:
        """OpenAI API + Whisper: OPENAI_API_KEY only."""
        return (self.openai_api_key or "").strip()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.database_url = normalize_database_url(s.database_url)
    return s
