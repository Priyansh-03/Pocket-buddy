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
    # Same key, alternate env name (e.g. staging / internal pipelines)
    outspark_openai_staging_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.0-flash"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    cors_origin: str = "http://localhost:5173"
    credentials_encryption_key: str = ""
    # Per-request bounds for LLM HTTP calls (tool loops = multiple round-trips).
    llm_connect_timeout_seconds: float = 45.0
    llm_read_timeout_seconds: float = 300.0

    def openai_key_effective(self) -> str:
        """Prefer OPENAI_API_KEY; if empty, use OUTSPARK_OPENAI_STAGING_API_KEY."""
        a = (self.openai_api_key or "").strip()
        if a:
            return a
        return (self.outspark_openai_staging_api_key or "").strip()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.database_url = normalize_database_url(s.database_url)
    return s
