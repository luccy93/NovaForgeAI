from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "NovaForge AI"
    app_version: str = "0.1.0"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/novaforge"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    jwt_issuer: str = "novaforge-ai"

    # Encryption
    encryption_master_key: Optional[str] = None
    encryption_key_rotation_days: int = 90

    # MFA
    mfa_required: bool = False
    mfa_issuer: str = "NovaForge AI"
    mfa_backup_code_count: int = 10

    # Password policy
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    password_history_count: int = 5
    password_max_age_days: int = 90

    # Account lockout
    account_lockout_attempts: int = 10
    account_lockout_window_minutes: int = 5
    account_lockout_duration_minutes: int = 15

    # Session
    session_max_concurrent: int = 10
    session_idle_timeout_minutes: int = 60
    session_absolute_timeout_hours: int = 24

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"]

    github_app_id: Optional[str] = None
    github_app_private_key: Optional[str] = None
    github_webhook_secret: Optional[str] = None
    github_oauth_client_id: Optional[str] = None
    github_oauth_client_secret: Optional[str] = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/github/callback"

    log_level: str = "INFO"
    sentry_dsn: Optional[str] = None

    rate_limit_auth_max: int = 100
    rate_limit_default_max: int = 200
    rate_limit_window_seconds: int = 60

    stripe_api_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_price_free: str = "price_free"
    stripe_price_pro: str = "price_pro"
    stripe_price_team: str = "price_team"
    stripe_price_business: str = "price_business"
    stripe_price_enterprise: str = "price_enterprise"

    default_org_plan: str = "free"

    # Notifications
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: str = "NovaForge AI"
    slack_client_id: Optional[str] = None
    slack_client_secret: Optional[str] = None
    slack_signing_secret: Optional[str] = None
    discord_bot_token: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
