"""Konfiguracja aplikacji ladowana ze zmiennych srodowiskowych (.env)."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "transport_intel"
    postgres_user: str = "osx"
    postgres_password: str = ""
    database_url: str = "postgresql+asyncpg://osx@localhost:5432/transport_intel"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "admin123"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    # JWT Auth
    jwt_secret_key: str = "220701570ec794826f887cd02c20fd2471db6c2775551aa03db8a043e5f3e660"
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
