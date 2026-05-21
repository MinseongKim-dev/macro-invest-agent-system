"""TimescaleDB connection management.

Provides `DatabaseConfig` (env-var backed dataclass) and `DatabaseConnection`
(context-manager with exponential-backoff retry) for psycopg v3.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator

import psycopg
from psycopg import Connection

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RETRIES = 5
_DEFAULT_RETRY_BASE_DELAY = 1.0  # seconds; doubles on each attempt


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = field(default_factory=lambda: os.environ.get("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("DB_PORT", "5432")))
    name: str = field(default_factory=lambda: os.environ.get("DB_NAME", "aleph_core"))
    user: str = field(default_factory=lambda: os.environ.get("DB_USER", "aleph_admin"))
    password: str = field(default_factory=lambda: os.environ.get("DB_PASSWORD", "aleph_secure_pass"))
    max_retries: int = _DEFAULT_MAX_RETRIES
    retry_base_delay: float = _DEFAULT_RETRY_BASE_DELAY

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password}"
        )


class DatabaseConnection:
    """Manages a single psycopg v3 connection with retry-on-startup logic.

    Usage::

        db = DatabaseConnection(DatabaseConfig())
        with db.connect() as conn:
            conn.execute("SELECT 1")
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._config = config or DatabaseConfig()

    def open(self) -> Connection:  # type: ignore[type-arg]
        """Open and return a raw connection with retry/backoff.

        Callers are responsible for closing the returned connection.
        Prefer `connect()` context manager for automatic cleanup.
        """
        config = self._config
        delay = config.retry_base_delay

        for attempt in range(1, config.max_retries + 1):
            try:
                conn = psycopg.connect(config.conninfo)
                logger.info(
                    "db_connected",
                    extra={"host": config.host, "dbname": config.name, "attempt": attempt},
                )
                return conn
            except psycopg.OperationalError as exc:
                if attempt == config.max_retries:
                    logger.error(
                        "db_connection_failed",
                        extra={"host": config.host, "attempts": attempt, "error": str(exc)},
                    )
                    raise
                logger.warning(
                    "db_connection_retry",
                    extra={"host": config.host, "attempt": attempt, "retry_in": delay, "error": str(exc)},
                )
                time.sleep(delay)
                delay *= 2

        # Unreachable — loop always raises on final attempt
        raise RuntimeError("unreachable")  # pragma: no cover

    @contextmanager
    def connect(self) -> Generator[Connection, None, None]:  # type: ignore[type-arg]
        """Context manager that opens a connection and closes it on exit."""
        conn = self.open()
        try:
            yield conn
        finally:
            conn.close()
            logger.debug("db_connection_closed", extra={"host": self._config.host})
