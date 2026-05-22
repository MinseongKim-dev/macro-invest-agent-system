"""Unit tests for core/config/settings.py."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.core.config.settings import Environment, LogLevel, Settings, get_settings


class TestSettingsDefaults:
    """Settings loads sensible defaults without a .env file."""

    def setup_method(self) -> None:
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        get_settings.cache_clear()

    def test_default_app_env(self) -> None:
        settings = Settings()
        assert settings.app_env == Environment.LOCAL

    def test_default_log_level(self) -> None:
        settings = Settings()
        assert settings.log_level == LogLevel.INFO

    def test_default_log_pretty_is_false(self) -> None:
        settings = Settings()
        assert settings.log_pretty is False

    def test_default_minio_endpoint(self) -> None:
        settings = Settings()
        assert settings.minio_endpoint == "http://localhost:9000"

    def test_default_minio_bucket_raw(self) -> None:
        settings = Settings()
        assert settings.minio_bucket_raw == "macro-raw"


class TestSettingsFromEnv:
    """Settings reads values from environment variables correctly."""

    def setup_method(self) -> None:
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        get_settings.cache_clear()

    def test_app_env_from_env_var(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "test"}):
            settings = Settings()
            assert settings.app_env == Environment.TEST

    def test_log_level_from_env_var(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            settings = Settings()
            assert settings.log_level == LogLevel.DEBUG

    def test_log_pretty_from_env_var(self) -> None:
        with patch.dict(os.environ, {"LOG_PRETTY": "true"}):
            settings = Settings()
            assert settings.log_pretty is True

    def test_minio_endpoint_from_env_var(self) -> None:
        with patch.dict(os.environ, {"MINIO_ENDPOINT": "http://minio:9000"}):
            settings = Settings()
            assert settings.minio_endpoint == "http://minio:9000"


class TestSettingsSecrets:
    """Secrets are stored as SecretStr and not accidentally exposed."""

    def test_database_url_is_secret(self) -> None:
        settings = Settings()
        repr_str = repr(settings.database_url)
        assert "macro_pass" not in repr_str
        assert "**" in repr_str

    def test_minio_password_is_secret(self) -> None:
        settings = Settings()
        repr_str = repr(settings.minio_root_password)
        assert "minioadmin" not in repr_str
        assert "**" in repr_str

    def test_database_url_get_secret_value(self) -> None:
        settings = Settings()
        value = settings.database_url.get_secret_value()
        assert "postgresql" in value


class TestSettingsHelpers:
    """Settings.is_local and is_test return expected booleans."""

    def test_is_local_true(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "local"}):
            settings = Settings()
            assert settings.is_local is True

    def test_is_local_false_for_production(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            settings = Settings()
            assert settings.is_local is False

    def test_is_test_true(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "test"}):
            settings = Settings()
            assert settings.is_test is True

    def test_is_test_false_for_local(self) -> None:
        settings = Settings()
        assert settings.is_test is False


class TestSettingsValidation:
    """Invalid environment variable values raise a validation error."""

    def setup_method(self) -> None:
        get_settings.cache_clear()

    def test_invalid_app_env_raises(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "not_a_valid_env"}), pytest.raises(ValidationError):
            Settings()

    def test_invalid_log_level_raises(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "VERBOSE"}), pytest.raises(ValidationError):
            Settings()


class TestGetSettingsSingleton:
    """get_settings returns a cached singleton."""

    def setup_method(self) -> None:
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        get_settings.cache_clear()

    def test_returns_same_instance(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_creates_new_instance(self) -> None:
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        assert s1 is not s2
