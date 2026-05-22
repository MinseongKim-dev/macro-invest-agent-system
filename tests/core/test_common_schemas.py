"""Unit tests for core/schemas/common.py."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.exceptions.base import AppError, NotFoundError
from src.core.schemas.common import AuditMetadata, BaseResponse, ErrorDetail, FreshnessMetadata


class TestFreshnessMetadata:
    """FreshnessMetadata stores and reports freshness correctly."""

    def test_now_sets_computed_at_to_utc(self) -> None:
        before = datetime.now(tz=UTC)
        fm = FreshnessMetadata.now()
        after = datetime.now(tz=UTC)
        assert before <= fm.computed_at <= after

    def test_no_expiry_is_not_stale(self) -> None:
        fm = FreshnessMetadata.now(expires_at=None)
        assert fm.is_stale is False
        assert fm.expires_at is None

    def test_future_expiry_is_not_stale(self) -> None:
        future = datetime.now(tz=UTC) + timedelta(hours=1)
        fm = FreshnessMetadata.now(expires_at=future)
        assert fm.is_stale is False

    def test_past_expiry_is_stale(self) -> None:
        past = datetime.now(tz=UTC) - timedelta(seconds=1)
        fm = FreshnessMetadata.now(expires_at=past)
        assert fm.is_stale is True

    def test_immutable(self) -> None:
        fm = FreshnessMetadata.now()
        with pytest.raises(PydanticValidationError):
            fm.is_stale = False

    def test_missing_computed_at_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            FreshnessMetadata(expires_at=None, is_stale=False)  # type: ignore[call-arg]


class TestAuditMetadata:
    """AuditMetadata generates a unique request_id and records created_at."""

    def test_new_generates_request_id(self) -> None:
        audit = AuditMetadata.new()
        uuid.UUID(audit.request_id)  # should not raise

    def test_two_instances_have_different_request_ids(self) -> None:
        a1 = AuditMetadata.new()
        a2 = AuditMetadata.new()
        assert a1.request_id != a2.request_id

    def test_trace_id_is_stored(self) -> None:
        audit = AuditMetadata.new(trace_id="test-trace-123")
        assert audit.trace_id == "test-trace-123"

    def test_trace_id_defaults_to_none(self) -> None:
        audit = AuditMetadata.new()
        assert audit.trace_id is None

    def test_created_at_is_utc(self) -> None:
        before = datetime.now(tz=UTC)
        audit = AuditMetadata.new()
        after = datetime.now(tz=UTC)
        assert before <= audit.created_at <= after

    def test_immutable(self) -> None:
        audit = AuditMetadata.new()
        with pytest.raises(PydanticValidationError):
            audit.trace_id = "new-trace"


class TestErrorDetail:
    """ErrorDetail carries the correct fields and can be built from AppError."""

    def test_required_fields(self) -> None:
        err = ErrorDetail(error_code="TEST_CODE", message="Test message")
        assert err.error_code == "TEST_CODE"
        assert err.message == "Test message"
        assert err.detail == {}

    def test_detail_payload(self) -> None:
        err = ErrorDetail(
            error_code="VALIDATION_ERROR",
            message="Bad input",
            detail={"field": "name", "issue": "required"},
        )
        assert err.detail["field"] == "name"

    def test_from_app_error(self) -> None:
        exc = NotFoundError("Widget not found.", detail={"id": "xyz"})
        err = ErrorDetail.from_app_error(exc, request_id="req-001")
        assert err.error_code == "NOT_FOUND"
        assert err.message == "Widget not found."
        assert err.detail["id"] == "xyz"
        assert err.request_id == "req-001"

    def test_from_generic_exception(self) -> None:
        exc = RuntimeError("secret internal details should not leak")
        err = ErrorDetail.from_app_error(exc)
        assert err.error_code == "INTERNAL_ERROR"
        # The original exception message must not appear in the error detail
        assert "secret internal details" not in err.message.lower()

    def test_request_id_auto_generated(self) -> None:
        exc = AppError("msg")
        err = ErrorDetail.from_app_error(exc)
        uuid.UUID(err.request_id)  # should not raise

    def test_immutable(self) -> None:
        err = ErrorDetail(error_code="X", message="y")
        with pytest.raises(PydanticValidationError):
            err.error_code = "Z"


class TestBaseResponse:
    """BaseResponse wraps typed data with success flag and audit metadata."""

    def test_success_flag_defaults_to_true(self) -> None:
        response: BaseResponse[str] = BaseResponse(data="hello")
        assert response.success is True

    def test_data_is_stored(self) -> None:
        response: BaseResponse[int] = BaseResponse(data=42)
        assert response.data == 42

    def test_audit_defaults_to_none(self) -> None:
        response: BaseResponse[str] = BaseResponse(data="x")
        assert response.audit is None

    def test_with_audit_metadata(self) -> None:
        audit = AuditMetadata.new(trace_id="t-999")
        response: BaseResponse[str] = BaseResponse(data="payload", audit=audit)
        assert response.audit is not None
        assert response.audit.trace_id == "t-999"

    def test_generic_with_dict(self) -> None:
        payload: dict[str, str] = {"key": "value"}
        response: BaseResponse[dict[str, str]] = BaseResponse(data=payload)
        assert response.data["key"] == "value"

    def test_missing_data_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            BaseResponse()  # type: ignore[call-arg]
