"""Unit tests for src/domain/notifications/service.py.

No network, no DB — all I/O is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.notifications.service import (
    _b64url,
    _b64url_decode,
    build_regime_email_html,
    generate_vapid_keys,
    send_email_alert,
    send_web_push,
)

# ── VAPID key generation ───────────────────────────────────────────────────────

def test_generate_vapid_keys_returns_two_non_empty_strings() -> None:
    keys = generate_vapid_keys()
    assert isinstance(keys["private_key"], str) and len(keys["private_key"]) > 10
    assert isinstance(keys["public_key"],  str) and len(keys["public_key"]) > 10


def test_generate_vapid_keys_produces_different_pairs() -> None:
    k1 = generate_vapid_keys()
    k2 = generate_vapid_keys()
    assert k1["private_key"] != k2["private_key"]
    assert k1["public_key"]  != k2["public_key"]


def test_b64url_roundtrip() -> None:
    data = b"\x00\xFF\xAB\xCD\xEF"
    assert _b64url_decode(_b64url(data)) == data


# ── HTML email builder ─────────────────────────────────────────────────────────

def test_build_regime_email_html_contains_regimes() -> None:
    html = build_regime_email_html("POLICY_TIGHTENING", "CRISIS_MODE", 0.75, "LATE_CYCLE")
    assert "POLICY_TIGHTENING" in html
    assert "CRISIS_MODE"       in html
    assert "75%"               in html
    assert "LATE_CYCLE"        in html


# ── send_email_alert — env gating ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_email_skips_when_no_api_key() -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("RESEND_API_KEY",    None)
        os.environ.pop("ALERT_EMAIL_TO",    None)
        # Should return without raising or making any HTTP call
        await send_email_alert("test subject", "<p>body</p>")


@pytest.mark.asyncio
async def test_send_email_posts_to_resend() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_resp)

    env = {
        "RESEND_API_KEY":   "re_test_key",
        "ALERT_EMAIL_TO":   "test@example.com",
        "ALERT_EMAIL_FROM": "Aleph-One <noreply@test.com>",
    }
    with patch.dict("os.environ", env), patch("httpx.AsyncClient", return_value=mock_client):
        await send_email_alert("Regime Alert", "<h1>Hi</h1>")

    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("json", {})
    assert payload.get("subject") == "Regime Alert"
    assert "test@example.com" in payload.get("to", [])


# ── send_web_push ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_web_push_returns_false_on_invalid_subscription() -> None:
    result = await send_web_push({}, "title", "body")
    assert result is False


@pytest.mark.asyncio
async def test_send_web_push_returns_false_on_http_error() -> None:
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

    # Generate a real P-256 key pair for the mock subscriber
    priv = generate_private_key(SECP256R1())
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    p256dh = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    import secrets
    auth   = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()

    sub = {"endpoint": "https://example.com/push/test", "keys": {"p256dh": p256dh, "auth": auth}}

    mock_resp = MagicMock()
    mock_resp.status_code = 500

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await send_web_push(sub, "title", "body")

    assert result is False


@pytest.mark.asyncio
async def test_send_web_push_returns_true_on_201() -> None:
    import base64
    import secrets

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

    priv = generate_private_key(SECP256R1())
    pub_bytes = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    p256dh = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    auth   = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()

    sub = {"endpoint": "https://fcm.googleapis.com/push/test", "keys": {"p256dh": p256dh, "auth": auth}}

    mock_resp = MagicMock()
    mock_resp.status_code = 201

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_resp)

    with (
        patch.dict("os.environ", {"VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": ""}),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await send_web_push(sub, "Regime Alert", "POLICY_TIGHTENING → CRISIS_MODE")

    assert result is True
