"""Failure category enumeration for MCP and agent response schemas.

:class:`FailureCategory` provides a controlled vocabulary for classifying
failure states in MCP responses and agent responses.  Callers can use
``failure_category`` fields to route on failure type without parsing
``error_message`` strings.

Values
------
* ``PROVIDER_TIMEOUT``  — upstream provider timed out.
* ``PROVIDER_HTTP``     — upstream provider returned a non-2xx HTTP status.
* ``PROVIDER_NETWORK``  — OS-level / network I/O failure reaching the provider.
* ``STALE_DATA``        — returned data is older than the freshness threshold.
* ``PARTIAL_DATA``      — fewer indicators returned than requested (degraded).
* ``SCHEMA_ERROR``      — response did not conform to the expected schema.
* ``UNKNOWN``           — unclassified failure; inspect ``error_message``.
"""

from __future__ import annotations

from enum import StrEnum


class FailureCategory(StrEnum):
    """Controlled vocabulary for classifying response failures.

    Use this enum to populate the ``failure_category`` field on MCP and agent
    response schemas rather than embedding category strings directly.
    """

    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_HTTP = "PROVIDER_HTTP"
    PROVIDER_NETWORK = "PROVIDER_NETWORK"
    STALE_DATA = "STALE_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    UNKNOWN = "UNKNOWN"
