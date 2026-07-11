"""Notification domain models — push subscription and delivery envelope."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PushSubscriptionKeys(BaseModel, extra="forbid"):
    """Browser-generated ECDH / auth keys embedded in a push subscription.

    These values arrive from ``PushSubscription.toJSON()`` in the browser and
    must be passed verbatim to the push-send step.

    Attributes:
        p256dh: Base-64 URL-encoded browser ECDH public key (uncompressed P-256).
        auth:   Base-64 URL-encoded 16-byte random authentication secret.
    """

    p256dh: str = Field(description="Base-64 URL-encoded browser ECDH public key")
    auth: str = Field(description="Base-64 URL-encoded 16-byte auth secret")


class PushSubscription(BaseModel, extra="forbid"):
    """A browser push subscription as returned by ``PushSubscription.toJSON()``.

    Attributes:
        endpoint: Push service URL (FCM, Mozilla, etc.).
        keys:     ECDH + auth material needed to encrypt the push payload.
    """

    endpoint: str = Field(description="Push service endpoint URL")
    keys: PushSubscriptionKeys


class RegimeAlertPayload(BaseModel, extra="forbid"):
    """Structured payload for a regime-transition notification.

    Attributes:
        old_regime:  Regime label before the transition.
        new_regime:  Regime label after the transition.
        confidence:  Confidence score of the new regime [0.0, 1.0].
        market_phase: Broad market phase label (e.g. EARLY_CYCLE, LATE_CYCLE).
    """

    old_regime: str
    new_regime: str
    confidence: float = Field(ge=0.0, le=1.0)
    market_phase: str
