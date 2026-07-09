"""Notification delivery service — Resend email + VAPID web push.

All async functions are fire-and-forget safe: exceptions are caught and
logged so a delivery failure never crashes the caller.

Environment variables
---------------------
``RESEND_API_KEY``
    Resend API key.  Email alerts are skipped when absent.
``ALERT_EMAIL_TO``
    Comma-separated recipient addresses for regime alerts.
``ALERT_EMAIL_FROM``
    Sender address (must match a verified Resend domain).
``VAPID_PRIVATE_KEY``
    Base-64 URL-encoded raw 32-byte ECDSA P-256 private scalar.
    Generate with :func:`generate_vapid_keys`.
``VAPID_PUBLIC_KEY``
    Base-64 URL-encoded uncompressed P-256 public key (65 bytes).
``VAPID_SUBJECT``
    ``mailto:`` or ``https:`` URI used as VAPID claims subject.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


# ── VAPID key generation ───────────────────────────────────────────────────────

def generate_vapid_keys() -> dict[str, str]:
    """Generate a fresh VAPID ECDSA P-256 key pair.

    Returns a dict with ``private_key`` (raw 32-byte scalar, base-64 URL) and
    ``public_key`` (uncompressed 65-byte point, base-64 URL).  Persist the
    private key in ``VAPID_PRIVATE_KEY`` and expose the public key via the API.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_scalar = private_key.private_numbers().private_value
    priv_bytes  = priv_scalar.to_bytes(32, "big")
    pub_bytes   = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return {"private_key": _b64url(priv_bytes), "public_key": _b64url(pub_bytes)}


def _load_vapid_private_key() -> ec.EllipticCurvePrivateKey | None:
    """Load the VAPID private key from VAPID_PRIVATE_KEY env var."""
    priv_b64 = _env("VAPID_PRIVATE_KEY")
    if not priv_b64:
        return None
    try:
        priv_bytes = _b64url_decode(priv_b64)
        d = int.from_bytes(priv_bytes, "big")
        return ec.derive_private_key(d, ec.SECP256R1())
    except Exception as exc:
        logger.warning("vapid_key_load_error", extra={"error": str(exc)})
        return None


def _vapid_authorization(endpoint: str) -> str | None:
    """Build a VAPID ``Authorization`` header value for the push endpoint.

    Returns ``None`` when VAPID keys are not configured (push is sent unsigned).
    """
    private_key = _load_vapid_private_key()
    pub_b64     = _env("VAPID_PUBLIC_KEY")
    subject     = _env("VAPID_SUBJECT", "mailto:admin@example.com")
    if private_key is None or not pub_b64:
        return None

    from urllib.parse import urlparse  # noqa: PLC0415
    parsed   = urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    now      = int(time.time())
    header   = _b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    payload  = _b64url(json.dumps({"aud": audience, "exp": now + 43200, "sub": subject}).encode())
    signing_input = f"{header}.{payload}".encode()
    sig_der       = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s          = decode_dss_signature(sig_der)
    sig           = _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    jwt           = f"{header}.{payload}.{sig}"
    return f"vapid t={jwt},k={pub_b64}"


# ── Web push payload encryption (RFC 8291 AES-128-GCM) ────────────────────────

def _encrypt_push_payload(plaintext: bytes, p256dh: str, auth_secret: str) -> tuple[bytes, str]:
    """Encrypt *plaintext* for web push using RFC 8291 AES-128-GCM.

    Returns ``(ciphertext_with_header, content_encoding)`` where the header
    follows the salt + record_size + key_id format from RFC 8291 §2.
    """
    subscriber_pub_bytes = _b64url_decode(p256dh)
    auth_bytes           = _b64url_decode(auth_secret)

    # Ephemeral sender ECDH key pair
    sender_key   = ec.generate_private_key(ec.SECP256R1())
    sender_pub   = sender_key.public_key()
    sender_pub_b = sender_pub.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    # Subscriber's public key
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey  # noqa: PLC0415
    subscriber_pub = EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), subscriber_pub_bytes)

    # ECDH shared secret
    shared_secret = sender_key.exchange(ec.ECDH(), subscriber_pub)

    # IKM (RFC 8291 §3.3)
    salt     = os.urandom(16)
    ikm_info = b"WebPush: info\x00" + subscriber_pub_bytes + sender_pub_b
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_bytes, info=ikm_info).derive(shared_secret)

    # Content Encryption Key + nonce
    cek   = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)

    # Pad with 0x02 delimiter, encrypt
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)

    # RFC 8291 §2 header: salt (16) + rs (4 big-endian) + idlen (1) + sender_pub
    rs     = len(ciphertext) + 16 + 1
    header = salt + struct.pack(">I", rs) + bytes([len(sender_pub_b)]) + sender_pub_b
    return header + ciphertext, "aes128gcm"


# ── Resend email ───────────────────────────────────────────────────────────────

async def send_email_alert(subject: str, html_body: str) -> None:
    """Send a regime-alert email via Resend.  No-op when key or recipient absent."""
    api_key   = _env("RESEND_API_KEY")
    to_raw    = _env("ALERT_EMAIL_TO")
    from_addr = _env("ALERT_EMAIL_FROM", "Aleph-One <alerts@aleph-one.dev>")
    if not api_key or not to_raw:
        logger.debug("resend_email_skipped: RESEND_API_KEY or ALERT_EMAIL_TO not set")
        return
    recipients = [e.strip() for e in to_raw.split(",") if e.strip()]
    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": from_addr, "to": recipients, "subject": subject, "html": html_body},
            )
        if resp.status_code >= 400:
            logger.warning("resend_email_error", extra={"status": resp.status_code})
        else:
            logger.info("resend_email_sent", extra={"subject": subject, "to": recipients})
    except Exception as exc:
        logger.warning("resend_email_exception", extra={"error": str(exc)})


# ── Web push ───────────────────────────────────────────────────────────────────

async def send_web_push(subscription: dict[str, Any], title: str, body: str) -> bool:
    """Send a web push notification to one subscription.

    *subscription* follows ``PushSubscription.toJSON()`` shape::

        {"endpoint": "https://…", "keys": {"p256dh": "…", "auth": "…"}}

    Returns ``True`` on HTTP 2xx, ``False`` on any other outcome.  Callers
    should remove subscriptions that return ``False`` with an HTTP 410.
    """
    endpoint = subscription.get("endpoint", "")
    keys     = subscription.get("keys") or {}
    p256dh   = keys.get("p256dh", "")
    auth     = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        logger.warning("web_push_invalid_subscription")
        return False
    try:
        payload_bytes = json.dumps({"title": title, "body": body}).encode()
        ciphertext, content_encoding = _encrypt_push_payload(payload_bytes, p256dh, auth)
        headers: dict[str, str] = {
            "Content-Type":     "application/octet-stream",
            "Content-Encoding": content_encoding,
            "TTL":              "86400",
        }
        vapid_auth = _vapid_authorization(endpoint)
        if vapid_auth:
            headers["Authorization"] = vapid_auth
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(endpoint, headers=headers, content=ciphertext)
        if resp.status_code in (200, 201):
            logger.info("web_push_sent", extra={"endpoint": endpoint[:50]})
            return True
        logger.warning("web_push_error", extra={"status": resp.status_code, "endpoint": endpoint[:50]})
        return False
    except Exception as exc:
        logger.warning("web_push_exception", extra={"error": str(exc)})
        return False


# ── Regime alert helpers ───────────────────────────────────────────────────────

def build_regime_email_html(
    old_regime: str, new_regime: str, confidence: float, market_phase: str
) -> str:
    """Return a minimal HTML email body for a regime transition alert."""
    return (
        f"<h2>Aleph-One — Regime Transition Alert</h2>"
        f"<p><strong>Previous regime:</strong> {old_regime}</p>"
        f"<p><strong>New regime:</strong> {new_regime}</p>"
        f"<p><strong>Confidence:</strong> {confidence:.0%}</p>"
        f"<p><strong>Market phase:</strong> {market_phase}</p>"
        f"<hr><p style='color:gray;font-size:12px'>Aleph-One Macro Intelligence</p>"
    )
