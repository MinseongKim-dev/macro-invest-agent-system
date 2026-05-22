"""Eval: prompt drift detection via SHA-256 snapshot hashes.

Each render_* function is called with a fixed canonical input set and the
resulting string is hashed.  The hash is compared against a stored fixture in
``evals/prompt_regression/fixtures/prompt_hashes.json``.

If the hash changes, the test fails.  To accept an intentional template change:
1. Delete or update the hash value in ``prompt_hashes.json``.
2. Re-run the test to confirm it passes.
3. Commit both the template change and the updated fixture in the same PR.

**Human review is required** before updating fixture hashes.

Test cases also verify that `is_degraded=True` does not cause hallucination
when injected via context_summary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from agent.prompts.templates import (
    render_signal_review_summary,
    render_snapshot_comparison_summary,
    render_snapshot_summary,
)

# Path to the stored fixture hashes.
_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_HASH_FIXTURE = _FIXTURES_DIR / "prompt_hashes.json"

# Canonical inputs — these must NOT change unless templates intentionally change.
_CANONICAL_SIGNAL_REVIEW_KWARGS = {
    "signal_ids": "bull_market, bear_market",
    "country": "US",
    "signals_generated": 3,
    "buy_signals": 2,
    "sell_signals": 1,
    "hold_signals": 0,
    "dominant_direction": "BUY",
    "engine_run_id": "eng-fixture-001",
    "execution_time_ms": "12.3",
}

_CANONICAL_SNAPSHOT_SUMMARY_KWARGS = {
    "country": "US",
    "features_count": 5,
    "snapshot_timestamp": "2026-01-01T00:00:00Z",
}

_CANONICAL_COMPARISON_SUMMARY_KWARGS = {
    "country": "US",
    "prior_snapshot_label": "Q1-2026",
    "changed_count": 3,
    "unchanged_count": 2,
    "no_prior_count": 0,
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_fixture_hashes() -> dict[str, str]:
    return cast(dict[str, str], json.loads(_HASH_FIXTURE.read_text()))


class TestPromptDrift:
    """Prompt templates produce stable output for fixed canonical inputs."""

    def test_signal_review_hash_unchanged(self) -> None:
        rendered = render_signal_review_summary(**_CANONICAL_SIGNAL_REVIEW_KWARGS)  # type: ignore[arg-type]
        actual_hash = _sha256(rendered)
        expected_hash = _load_fixture_hashes()["signal_review"]
        assert actual_hash == expected_hash, (
            f"signal_review prompt has drifted!\n"
            f"Rendered: {rendered!r}\n"
            f"New hash:      {actual_hash}\n"
            f"Expected hash: {expected_hash}\n"
            f"Update {_HASH_FIXTURE} if this change is intentional."
        )

    def test_snapshot_summary_hash_unchanged(self) -> None:
        rendered = render_snapshot_summary(**_CANONICAL_SNAPSHOT_SUMMARY_KWARGS)  # type: ignore[arg-type]
        actual_hash = _sha256(rendered)
        expected_hash = _load_fixture_hashes()["snapshot_summary"]
        assert actual_hash == expected_hash, (
            f"snapshot_summary prompt has drifted!\n"
            f"Rendered: {rendered!r}\n"
            f"New hash:      {actual_hash}\n"
            f"Expected hash: {expected_hash}\n"
            f"Update {_HASH_FIXTURE} if this change is intentional."
        )

    def test_comparison_summary_hash_unchanged(self) -> None:
        rendered = render_snapshot_comparison_summary(**_CANONICAL_COMPARISON_SUMMARY_KWARGS)  # type: ignore[arg-type]
        actual_hash = _sha256(rendered)
        expected_hash = _load_fixture_hashes()["comparison_summary"]
        assert actual_hash == expected_hash, (
            f"comparison_summary prompt has drifted!\n"
            f"Rendered: {rendered!r}\n"
            f"New hash:      {actual_hash}\n"
            f"Expected hash: {expected_hash}\n"
            f"Update {_HASH_FIXTURE} if this change is intentional."
        )

    def test_signal_review_with_is_degraded_context_does_not_hallucinate(self) -> None:
        """Context hint does not appear in the human message (only in system)."""
        rendered = render_signal_review_summary(
            **_CANONICAL_SIGNAL_REVIEW_KWARGS,  # type: ignore[arg-type]
            context_summary="is_degraded=True",
        )
        # The context hint is injected into the SYSTEM message, not the human message.
        # The rendered output (human message only) must not contain the context hint text.
        assert "is_degraded=True" not in rendered
        # The human message still contains the canonical factual content.
        assert "bull_market" in rendered
        assert "BUY" in rendered

    def test_snapshot_summary_with_is_degraded_context_does_not_hallucinate(self) -> None:
        rendered = render_snapshot_summary(
            **_CANONICAL_SNAPSHOT_SUMMARY_KWARGS,  # type: ignore[arg-type]
            context_summary="is_degraded=True, stale data warning",
        )
        assert "is_degraded=True" not in rendered
        assert "stale data warning" not in rendered
        assert "country=US" in rendered

    def test_comparison_with_is_degraded_context_does_not_hallucinate(self) -> None:
        rendered = render_snapshot_comparison_summary(
            **_CANONICAL_COMPARISON_SUMMARY_KWARGS,  # type: ignore[arg-type]
            context_summary="degraded snapshot, partial data",
        )
        assert "degraded snapshot" not in rendered
        assert "partial data" not in rendered
        assert "Q1-2026" in rendered
