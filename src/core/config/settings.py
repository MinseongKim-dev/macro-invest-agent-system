"""Application configuration loaded from environment variables.

Uses :mod:`pydantic_settings` to validate and type all settings at startup.
Secrets (passwords, API keys) are never logged.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Valid deployment environments."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Valid log level names, matching :mod:`logging` constants."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Platform-wide application settings.

    All values are read from environment variables (or a ``.env`` file).
    Sensitive values are typed as :class:`~pydantic.SecretStr` so that they
    are masked when the model is serialised or repr'd.

    Example::

        from core.config.settings import get_settings
        settings = get_settings()
        print(settings.app_env)  # Environment.LOCAL
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    app_env: Environment = Field(
        default=Environment.LOCAL,
        description="Deployment environment (local | test | staging | production).",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Minimum log level emitted by the structured logger.",
    )
    log_pretty: bool = Field(
        default=False,
        description="When True, emit human-readable logs instead of JSON (recommended for local dev).",
    )

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://macro_user:macro_pass@localhost:5432/macro_db"),
        description="SQLAlchemy-compatible database URL. Never logged.",
    )

    # ------------------------------------------------------------------
    # MinIO / S3
    # ------------------------------------------------------------------

    minio_endpoint: str = Field(
        default="http://localhost:9000",
        description="MinIO API endpoint.",
    )
    minio_root_user: str = Field(
        default="minioadmin",
        description="MinIO root username (local dev only).",
    )
    minio_root_password: SecretStr = Field(
        default=SecretStr("minioadmin"),
        description="MinIO root password. Never logged.",
    )
    minio_bucket_raw: str = Field(
        default="macro-raw",
        description="Bucket name for raw macro data artefacts.",
    )

    # ------------------------------------------------------------------
    # FRED (Federal Reserve Economic Data)
    # ------------------------------------------------------------------

    fred_api_key: SecretStr | None = Field(
        default=None,
        description="FRED API key.  Required to call the live FRED API.  Never logged.",
    )
    fred_base_url: str = Field(
        default="https://api.stlouisfed.org/fred",
        description="Base URL for the FRED REST API.",
    )
    fred_request_timeout_s: float = Field(
        default=10.0,
        description="HTTP request timeout in seconds for FRED API calls.",
    )

    # ------------------------------------------------------------------
    # OpenTelemetry tracing
    # ------------------------------------------------------------------

    tracing_enabled: bool = Field(
        default=False,
        description="When True, initialise the OpenTelemetry SDK and export traces.",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP HTTP endpoint for trace export (e.g. local Jaeger or Grafana Tempo).",
    )
    otel_service_name: str = Field(
        default="macro-invest-agent-platform",
        description="OpenTelemetry service.name resource attribute.",
    )
    otel_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of traces to sample (0.0–1.0). 1.0 = 100%.",
    )

    # ------------------------------------------------------------------
    # Prometheus metrics
    # ------------------------------------------------------------------

    metrics_enabled: bool = Field(
        default=True,
        description="When True, expose Prometheus metrics via the /metrics endpoint.",
    )
    metrics_namespace: str = Field(
        default="macro_platform",
        description="Prometheus metric name prefix (namespace).",
    )

    # ------------------------------------------------------------------
    # Startup seeder
    # ------------------------------------------------------------------

    seed_on_startup: bool = Field(
        default=True,
        description=(
            "When True, the startup seeder runs on application boot to ensure the "
            "in-memory regime store is populated with synthetic bootstrap data. "
            "Set to False in production environments that use a real ingestion pipeline. "
            "Recommendation: True for local/dev, False for staging/production."
        ),
    )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def is_local(self) -> bool:
        """Return True when running in a local development environment."""
        return self.app_env == Environment.LOCAL

    @property
    def is_test(self) -> bool:
        """Return True when running inside the test suite."""
        return self.app_env == Environment.TEST


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application settings singleton.

    The result is cached after the first call so that environment variables
    are read only once per process.  In tests, call
    ``get_settings.cache_clear()`` between cases that need different settings.
    """
    return Settings()
