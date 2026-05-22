"""Typed application exception hierarchy for macro-invest-agent-platform.

All custom exceptions inherit from :class:`AppError`, which carries a machine-
readable ``error_code`` and a ``detail`` payload so that callers can handle
errors programmatically rather than parsing message strings.

Exception design rules:
- Every public exception class has an explicit ``error_code`` default.
- Subclasses refine the ``error_code`` to a specific domain prefix.
- HTTP status semantics (4xx / 5xx) are encoded in subclass names, not here.
- Secrets and PII must never appear in ``detail`` or ``message``.

Provider failure hierarchy::

    AppError
    └── ProviderError               # base for all external-provider failures
        ├── ProviderTimeoutError    # request timed out
        ├── ProviderHTTPError       # non-200 HTTP status from provider
        └── ProviderNetworkError    # OS-level / network I/O failure

Data-quality failures::

    AppError
    ├── StaleDataError              # data is older than expected freshness window
    ├── PartialDataError            # fewer indicators returned than requested
    └── SchemaConformanceError      # response does not match expected schema

Usage::

    from core.exceptions.base import NotFoundError, ValidationError
    from core.exceptions.base import ProviderHTTPError, StaleDataError

    raise NotFoundError(
        message="Signal result not found.",
        error_code="SIGNAL_NOT_FOUND",
        detail={"strategy_id": strategy_id},
    )

    raise ProviderHTTPError(
        message="FRED API returned HTTP 503.",
        provider_id="fred",
        http_status=503,
    )
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class AppError(Exception):
    """Base class for all application-level exceptions.

    Args:
        message: Human-readable error summary (safe to surface to callers).
        error_code: Machine-readable identifier, e.g. ``"SIGNAL_NOT_FOUND"``.
        detail: Optional structured context for debugging.  Must not contain
            secrets or PII.
    """

    error_code: str = "APP_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        self.detail: dict[str, Any] = detail or {}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"message={self.message!r}, "
            f"detail={self.detail!r})"
        )


# ---------------------------------------------------------------------------
# 4xx — client / input errors
# ---------------------------------------------------------------------------


class ValidationError(AppError):
    """Raised when input data fails schema or business-rule validation.

    Maps to HTTP 422 Unprocessable Entity.
    """

    error_code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    """Raised when a requested resource does not exist.

    Maps to HTTP 404 Not Found.
    """

    error_code = "NOT_FOUND"


class ConflictError(AppError):
    """Raised when an operation would create a conflicting state.

    Maps to HTTP 409 Conflict.
    """

    error_code = "CONFLICT"


# ---------------------------------------------------------------------------
# 5xx — server / infrastructure errors
# ---------------------------------------------------------------------------


class InternalError(AppError):
    """Raised for unexpected server-side errors that should not be retried.

    Maps to HTTP 500 Internal Server Error.
    """

    error_code = "INTERNAL_ERROR"


class StorageError(AppError):
    """Raised when a database or object-store operation fails.

    Maps to HTTP 503 Service Unavailable.
    """

    error_code = "STORAGE_ERROR"


class ConfigurationError(AppError):
    """Raised when the application is mis-configured at startup.

    Typically indicates a missing or invalid environment variable.
    This exception is fatal -- the application should not continue.
    """

    error_code = "CONFIGURATION_ERROR"


# ---------------------------------------------------------------------------
# Domain-specific errors
# ---------------------------------------------------------------------------


class DomainError(AppError):
    """Base class for domain-logic violations (signal engine, feature compute).

    Raised when inputs are structurally valid but violate a business rule.
    """

    error_code = "DOMAIN_ERROR"


class MCPToolError(AppError):
    """Raised by MCP tool implementations on execution failure.

    Agents should treat this as a non-retryable tool call failure unless
    the subclass indicates otherwise.
    """

    error_code = "MCP_TOOL_ERROR"


# ---------------------------------------------------------------------------
# Provider / external data-source errors
# ---------------------------------------------------------------------------


class ProviderError(AppError):
    """Base class for all external data-provider failures.

    Raised by data-source adapters (e.g. FredMacroDataSource) when
    the upstream provider is unavailable or returns an unexpected response.
    Callers can catch ``ProviderError`` to handle all provider failures
    uniformly, or catch a specific subclass for finer-grained handling.

    Args:
        message: Human-readable error summary.
        provider_id: Short identifier for the failing provider (e.g. ``"fred"``).
        error_code: Machine-readable code; defaults to ``"PROVIDER_ERROR"``.
        detail: Optional structured debugging context.  Must not contain secrets.
    """

    error_code = "PROVIDER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, detail=detail)
        self.provider_id = provider_id


class ProviderTimeoutError(ProviderError):
    """Raised when a request to an external provider times out.

    Args:
        message: Human-readable error summary.
        provider_id: Short identifier for the failing provider.
        timeout_s: Configured timeout in seconds that was exceeded.
    """

    error_code = "PROVIDER_TIMEOUT"

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        timeout_s: float | None = None,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, provider_id=provider_id, error_code=error_code, detail=detail)
        self.timeout_s = timeout_s


class ProviderHTTPError(ProviderError):
    """Raised when an external provider returns a non-success HTTP status.

    Args:
        message: Human-readable error summary.
        provider_id: Short identifier for the failing provider.
        http_status: The HTTP status code returned by the provider.
    """

    error_code = "PROVIDER_HTTP_ERROR"

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        http_status: int = 0,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, provider_id=provider_id, error_code=error_code, detail=detail)
        self.http_status = http_status


class ProviderNetworkError(ProviderError):
    """Raised on OS-level or network I/O failure when contacting a provider.

    Args:
        message: Human-readable error summary.
        provider_id: Short identifier for the failing provider.
    """

    error_code = "PROVIDER_NETWORK_ERROR"


# ---------------------------------------------------------------------------
# Data-quality errors
# ---------------------------------------------------------------------------


class StaleDataError(AppError):
    """Raised when returned data is older than the expected freshness window.

    Callers that receive this exception should surface ``is_degraded=True`` in
    their response and not treat the data as current.

    Args:
        message: Human-readable error summary.
        stale_since: The timestamp at which the data became stale, if known.
    """

    error_code = "STALE_DATA"

    def __init__(
        self,
        message: str,
        *,
        stale_since: datetime | None = None,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, detail=detail)
        self.stale_since = stale_since


class PartialDataError(AppError):
    """Raised when fewer indicators are returned than were requested.

    This is a *degraded* (not hard-failure) state -- callers should surface
    ``is_degraded=True`` rather than treating the partial result as a hard error.

    Args:
        message: Human-readable error summary.
        available_count: Number of indicators that were actually returned.
        requested_count: Number of indicators that were requested.
    """

    error_code = "PARTIAL_DATA"

    def __init__(
        self,
        message: str,
        *,
        available_count: int = 0,
        requested_count: int = 0,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, detail=detail)
        self.available_count = available_count
        self.requested_count = requested_count


class SchemaConformanceError(AppError):
    """Raised when a response does not match the expected schema.

    Used to surface unexpected structural changes in external API responses
    that could not be handled by normal parsing logic.
    """

    error_code = "SCHEMA_CONFORMANCE_ERROR"
