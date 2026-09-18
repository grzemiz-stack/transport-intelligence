"""Konfiguracja aplikacji ladowana ze zmiennych srodowiskowych (.env).

Pola oznaczone jako wymagane (bez defaulta) musza byc ustawione w .env
lub zmiennych srodowiskowych — w przeciwnym razie aplikacja nie wystartuje.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "transport_intel"
    postgres_user: str = "admin"
    postgres_password: str  # REQUIRED — no default
    database_url: str  # REQUIRED — no default

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # JWT Auth
    jwt_secret_key: str  # REQUIRED — no default
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # NLP / AI
    spacy_model: str = "xx_ent_wiki_sm"
    transformers_model: str = "xlm-roberta-base"

    # SMTP (email notifications)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "alerts@transport-intel.com"
    smtp_enabled: bool = False
    dashboard_url: str = "http://localhost:3000"

    # Anthropic (translation)
    anthropic_api_key: str = ""

    # Companies House (UK) API
    companies_house_api_key: str = ""
    translation_enabled: bool = False

    # Telegram (Telethon)
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_session_name: str = "ti_session"

    # Discord
    discord_bot_token: str = ""

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_must_not_be_weak(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
