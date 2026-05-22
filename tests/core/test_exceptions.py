"""Unit tests for core/exceptions/base.py."""

from datetime import UTC, datetime

import pytest

from src.core.exceptions.base import (
    AppError,
    ConfigurationError,
    ConflictError,
    DomainError,
    InternalError,
    MCPToolError,
    NotFoundError,
    PartialDataError,
    ProviderError,
    ProviderHTTPError,
    ProviderNetworkError,
    ProviderTimeoutError,
    SchemaConformanceError,
    StaleDataError,
    StorageError,
    ValidationError,
)


class TestAppError:
    """AppError carries the expected attributes and defaults."""

    def test_message_stored(self) -> None:
        exc = AppError("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "something went wrong"

    def test_default_error_code(self) -> None:
        exc = AppError("msg")
        assert exc.error_code == "APP_ERROR"

    def test_custom_error_code(self) -> None:
        exc = AppError("msg", error_code="CUSTOM_CODE")
        assert exc.error_code == "CUSTOM_CODE"

    def test_default_detail_is_empty_dict(self) -> None:
        exc = AppError("msg")
        assert exc.detail == {}

    def test_custom_detail(self) -> None:
        exc = AppError("msg", detail={"key": "value"})
        assert exc.detail == {"key": "value"}

    def test_is_exception(self) -> None:
        exc = AppError("msg")
        assert isinstance(exc, Exception)


class TestSubclassErrorCodes:
    """Each subclass has the expected default error_code."""

    @pytest.mark.parametrize(
        ("cls", "expected_code"),
        [
            (ValidationError, "VALIDATION_ERROR"),
            (NotFoundError, "NOT_FOUND"),
            (ConflictError, "CONFLICT"),
            (InternalError, "INTERNAL_ERROR"),
            (StorageError, "STORAGE_ERROR"),
            (ConfigurationError, "CONFIGURATION_ERROR"),
            (DomainError, "DOMAIN_ERROR"),
            (MCPToolError, "MCP_TOOL_ERROR"),
        ],
    )
    def test_default_error_code(self, cls: type[AppError], expected_code: str) -> None:
        exc = cls("test message")
        assert exc.error_code == expected_code


class TestSubclassInheritance:
    """All subclasses inherit from AppError."""

    def test_validation_error_is_app_error(self) -> None:
        assert issubclass(ValidationError, AppError)

    def test_not_found_is_app_error(self) -> None:
        assert issubclass(NotFoundError, AppError)

    def test_domain_error_is_app_error(self) -> None:
        assert issubclass(DomainError, AppError)

    def test_mcp_tool_error_is_app_error(self) -> None:
        assert issubclass(MCPToolError, AppError)


class TestRaiseAndCatch:
    """Exceptions can be raised and caught as expected."""

    def test_raise_and_catch_as_app_error(self) -> None:
        with pytest.raises(AppError) as exc_info:
            raise NotFoundError("Signal not found.", detail={"id": "abc"})
        assert exc_info.value.error_code == "NOT_FOUND"
        assert exc_info.value.detail["id"] == "abc"

    def test_raise_and_catch_as_specific_type(self) -> None:
        with pytest.raises(NotFoundError):
            raise NotFoundError("Missing resource.")

    def test_error_code_override_on_subclass(self) -> None:
        exc = ValidationError("bad input", error_code="CUSTOM_VALIDATION")
        assert exc.error_code == "CUSTOM_VALIDATION"


# ---------------------------------------------------------------------------
# Provider exception hierarchy
# ---------------------------------------------------------------------------


class TestProviderError:
    """ProviderError and subclasses carry correct attributes."""

    def test_provider_error_default_code(self) -> None:
        exc = ProviderError("provider down", provider_id="fred")
        assert exc.error_code == "PROVIDER_ERROR"
        assert exc.provider_id == "fred"

    def test_provider_error_is_app_error(self) -> None:
        assert issubclass(ProviderError, AppError)

    def test_provider_timeout_error_carries_timeout(self) -> None:
        exc = ProviderTimeoutError("timed out", provider_id="fred", timeout_s=30.0)
        assert exc.error_code == "PROVIDER_TIMEOUT"
        assert exc.timeout_s == 30.0
        assert exc.provider_id == "fred"
        assert isinstance(exc, ProviderError)

    def test_provider_http_error_carries_status(self) -> None:
        exc = ProviderHTTPError("HTTP 503", provider_id="fred", http_status=503)
        assert exc.error_code == "PROVIDER_HTTP_ERROR"
        assert exc.http_status == 503
        assert isinstance(exc, ProviderError)

    def test_provider_http_error_default_status(self) -> None:
        exc = ProviderHTTPError("no status")
        assert exc.http_status == 0

    def test_provider_network_error(self) -> None:
        exc = ProviderNetworkError("connection refused", provider_id="fred")
        assert exc.error_code == "PROVIDER_NETWORK_ERROR"
        assert isinstance(exc, ProviderError)

    def test_provider_errors_catchable_as_provider_error(self) -> None:
        for cls, kwargs in [
            (ProviderTimeoutError, {"timeout_s": 5.0}),
            (ProviderHTTPError, {"http_status": 404}),
            (ProviderNetworkError, {}),
        ]:
            with pytest.raises(ProviderError):
                raise cls("test", **kwargs)  # type: ignore[arg-type]

    def test_repr_does_not_include_api_key(self) -> None:
        """Repr must not expose secrets — provider_id only, not credentials."""
        exc = ProviderHTTPError("error", provider_id="fred", http_status=401)
        r = repr(exc)
        assert "api_key" not in r.lower()
        assert "secret" not in r.lower()


# ---------------------------------------------------------------------------
# StaleDataError and PartialDataError
# ---------------------------------------------------------------------------


class TestStaleDataError:
    """StaleDataError carries stale_since and inherits from AppError."""

    def test_default_code(self) -> None:
        exc = StaleDataError("data too old")
        assert exc.error_code == "STALE_DATA"

    def test_is_app_error(self) -> None:
        assert issubclass(StaleDataError, AppError)

    def test_stale_since_none_by_default(self) -> None:
        exc = StaleDataError("stale")
        assert exc.stale_since is None

    def test_carries_stale_since(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        exc = StaleDataError("stale", stale_since=ts)
        assert exc.stale_since == ts

    def test_not_provider_error(self) -> None:
        exc = StaleDataError("stale")
        assert not isinstance(exc, ProviderError)


class TestPartialDataError:
    """PartialDataError carries available/requested counts and inherits from AppError."""

    def test_default_code(self) -> None:
        exc = PartialDataError("partial", available_count=2, requested_count=5)
        assert exc.error_code == "PARTIAL_DATA"

    def test_is_app_error(self) -> None:
        assert issubclass(PartialDataError, AppError)

    def test_carries_counts(self) -> None:
        exc = PartialDataError("partial", available_count=3, requested_count=7)
        assert exc.available_count == 3
        assert exc.requested_count == 7

    def test_default_counts(self) -> None:
        exc = PartialDataError("partial")
        assert exc.available_count == 0
        assert exc.requested_count == 0

    def test_catchable_as_app_error(self) -> None:
        with pytest.raises(AppError):
            raise PartialDataError("partial", available_count=1, requested_count=3)


# ---------------------------------------------------------------------------
# SchemaConformanceError
# ---------------------------------------------------------------------------


class TestSchemaConformanceError:
    """SchemaConformanceError inherits from AppError with correct default code."""

    def test_default_code(self) -> None:
        exc = SchemaConformanceError("bad schema")
        assert exc.error_code == "SCHEMA_CONFORMANCE_ERROR"

    def test_is_app_error(self) -> None:
        assert issubclass(SchemaConformanceError, AppError)

