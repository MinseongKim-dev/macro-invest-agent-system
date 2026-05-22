"""Lightweight latency instrumentation for async operations.

Provides :func:`timed_operation` — a simple async context manager that
measures wall-clock time and emits a structured ``operation_complete`` log
record on exit.  On exception it emits ``operation_failed`` instead and
re-raises the original exception unchanged so existing error semantics are
never altered.

Usage::

    from core.logging.timing import timed_operation
    from core.logging.logger import get_logger

    log = get_logger(__name__)

    async def fetch_data() -> list[str]:
        async with timed_operation("service", "fetch_data", log):
            return await _do_fetch()

Design constraints
------------------
* No exception wrapping — the context manager re-raises exactly what the body
  raises.
* No external dependencies beyond the stdlib :mod:`time` module.
* The ``layer`` field enables per-layer latency breakdown in log aggregators.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def timed_operation(
    layer: str,
    operation: str,
    log: Any,  # noqa: ANN401  – accepts any structlog FilteringBoundLogger
) -> AsyncGenerator[None, None]:
    """Async context manager that measures latency and emits structured logs.

    Emits ``operation_complete`` with ``latency_ms`` on clean exit, or
    ``operation_failed`` with ``latency_ms`` and ``error`` on exception.  The
    exception is always re-raised unchanged.

    Args:
        layer: Short label for the architectural layer (e.g. ``"runtime"``,
            ``"service"``, ``"mcp_adapter"``, ``"mcp_tool"``).
        operation: Name of the specific operation being timed (e.g.
            ``"review_signals"``, ``"get_macro_snapshot"``).
        log: A structlog logger instance (or any object with ``info`` /
            ``warning`` methods that accept keyword arguments).

    Yields:
        Nothing — the context manager only wraps the body.

    Example::

        async with timed_operation("service", "review_signals", log):
            result = await self._do_review(request)
    """
    start_ns = time.perf_counter_ns()
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        log.warning(
            "operation_failed",
            layer=layer,
            operation=operation,
            latency_ms=round(elapsed_ms, 3),
            error=type(exc).__name__,
        )
        raise
    else:
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        log.debug(
            "operation_complete",
            layer=layer,
            operation=operation,
            latency_ms=round(elapsed_ms, 3),
        )
