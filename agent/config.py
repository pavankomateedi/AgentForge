from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Anthropic / model
    anthropic_api_key: str
    model: str

    # Server
    host: str
    port: int
    log_level: str

    # Auth / session
    database_url: str
    session_secret: str
    session_https_only: bool

    # Bootstrap user (optional — runs once on startup if DB is empty and all three are set)
    default_user_username: str | None
    default_user_email: str | None
    default_user_password: str | None

    # Email (Phase 3 — password reset)
    resend_api_key: str | None
    resend_from: str | None
    app_base_url: str

    # Observability (Langfuse)
    langfuse_public_key: str | None
    langfuse_secret_key: str | None
    langfuse_host: str


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_config() -> Config:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    # SESSION_SECRET is required for the server but not for CLI commands;
    # main.py enforces it at server startup. We accept empty here.
    session_secret = os.environ.get("SESSION_SECRET", "").strip()

    return Config(
        anthropic_api_key=api_key,
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7").strip(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./agentforge.db").strip(),
        session_secret=session_secret,
        session_https_only=_bool(os.environ.get("SESSION_HTTPS_ONLY"), default=False),
        default_user_username=(os.environ.get("DEFAULT_USER_USERNAME") or "").strip() or None,
        default_user_email=(os.environ.get("DEFAULT_USER_EMAIL") or "").strip() or None,
        default_user_password=(os.environ.get("DEFAULT_USER_PASSWORD") or "") or None,
        resend_api_key=(os.environ.get("RESEND_API_KEY") or "").strip() or None,
        resend_from=(os.environ.get("RESEND_FROM") or "").strip() or None,
        app_base_url=os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").strip(),
        langfuse_public_key=(os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip() or None,
        langfuse_secret_key=(os.environ.get("LANGFUSE_SECRET_KEY") or "").strip() or None,
        langfuse_host=os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com").strip(),
    )
