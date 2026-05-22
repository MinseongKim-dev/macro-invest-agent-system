"""Deterministic snapshot comparison logic for the macro domain.

This module provides pure functions and typed models for comparing a current
:class:`~domain.macro.models.MacroSnapshot` against a set of prior feature
values.  All logic is deterministic — no LLM or external I/O is involved.

Design constraints
------------------
* **Deterministic**: same inputs always produce the same output.
* **Explicit**: each change is represented as a typed :class:`FeatureDelta`.
* **Bounded**: only indicators present in the current snapshot are compared;
  excess prior values are ignored.
* **No speculation**: the comparison describes measured differences only.
* **Read-only**: no snapshot or service state is mutated.

Comparison semantics
--------------------
For each feature in the current snapshot, the function looks for a matching
entry in *prior_features* by ``indicator_type``.

* **Match found**: a :class:`FeatureDelta` with ``direction`` set to
  ``"increased"``, ``"decreased"``, or ``"unchanged"`` is produced.
* **No match**: a :class:`FeatureDelta` with ``direction="no_prior"`` is
  produced; ``prior_value`` and ``delta`` are ``None``.

The ``unchanged_threshold`` parameter controls the minimum absolute delta
that counts as a change (default ``1e-9`` — effectively float equality).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from domain.macro.models import MacroSnapshot

# ---------------------------------------------------------------------------
# Prior feature input
# ---------------------------------------------------------------------------


class PriorFeatureInput(BaseModel, extra="forbid"):
    """Minimal prior-snapshot feature data required for comparison.

    Only ``indicator_type`` and ``value`` are needed to compute a delta.
    The caller is responsible for ensuring the values come from a prior
    snapshot (not the current one).

    Attributes:
        indicator_type: The :attr:`~domain.macro.enums.MacroIndicatorType`
            string value (e.g. ``"gdp"``).
        value: The indicator value at the prior snapshot time.
    """

    indicator_type: str = Field(..., description="MacroIndicatorType string value")
    value: float = Field(..., description="Indicator value at the prior snapshot time")


# ---------------------------------------------------------------------------
# Comparison result types
# ---------------------------------------------------------------------------

ChangeDirection = Literal["increased", "decreased", "unchanged", "no_prior"]


class FeatureDelta(BaseModel, extra="forbid"):
    """The measured difference for a single indicator between two snapshots.

    Attributes:
        indicator_type: The indicator being compared.
        current_value: Value in the current snapshot.
        prior_value: Value in the prior snapshot; ``None`` if no prior entry
            was found.
        delta: ``current_value - prior_value``; ``None`` if no prior entry.
        direction: One of ``"increased"``, ``"decreased"``, ``"unchanged"``,
            or ``"no_prior"``.
    """

    indicator_type: str = Field(..., description="Indicator type being compared")
    current_value: float = Field(..., description="Value in the current snapshot")
    prior_value: float | None = Field(
        default=None, description="Value in the prior snapshot; None if not present"
    )
    delta: float | None = Field(
        default=None, description="current_value - prior_value; None if no prior"
    )
    direction: ChangeDirection = Field(
        ...,
        description=(
            "'increased' | 'decreased' | 'unchanged' | 'no_prior'"
        ),
    )


class SnapshotComparison(BaseModel, extra="forbid"):
    """Structured result of comparing a current snapshot against prior values.

    Attributes:
        country: Country code for which the comparison was performed.
        prior_snapshot_label: Human-readable label for the prior snapshot
            (e.g. ``"Q1-2026"`` or a timestamp string).
        current_snapshot_timestamp: Reference time of the current snapshot;
            ``None`` if not available.
        deltas: Per-indicator comparison results, in the same order as the
            current snapshot's feature list.
        changed_count: Number of indicators that changed (increased or
            decreased).
        unchanged_count: Number of indicators that did not change.
        no_prior_count: Number of indicators with no prior value.
    """

    country: str = Field(..., description="Country code for the comparison")
    prior_snapshot_label: str = Field(..., description="Human-readable prior snapshot label")
    current_snapshot_timestamp: datetime | None = Field(
        default=None,
        description="Reference time of the current snapshot",
    )
    deltas: list[FeatureDelta] = Field(
        default_factory=list,
        description="Per-indicator deltas (same order as current snapshot features)",
    )
    changed_count: int = Field(
        default=0,
        ge=0,
        description="Number of indicators that changed (increased or decreased)",
    )
    unchanged_count: int = Field(
        default=0,
        ge=0,
        description="Number of indicators with no change",
    )
    no_prior_count: int = Field(
        default=0,
        ge=0,
        description="Number of indicators with no prior value available",
    )


# ---------------------------------------------------------------------------
# Comparison function
# ---------------------------------------------------------------------------


def compare_snapshots(
    current: MacroSnapshot,
    prior_features: list[PriorFeatureInput],
    prior_snapshot_label: str,
    country: str,
    unchanged_threshold: float = 1e-9,
) -> SnapshotComparison:
    """Compare a current snapshot against a set of prior feature values.

    For each feature in *current*, the function looks up a matching entry in
    *prior_features* by ``indicator_type`` (case-sensitive string match).
    The first match is used; subsequent matches for the same indicator are
    ignored.

    Args:
        current: The current :class:`~domain.macro.models.MacroSnapshot`.
        prior_features: Minimal prior snapshot data (type + value per
            indicator).  May be empty — each current indicator then gets
            ``direction="no_prior"``.
        prior_snapshot_label: Human-readable label for the prior snapshot.
        country: Country code for the comparison result.
        unchanged_threshold: Minimum absolute delta to register as a change.
            Defaults to ``1e-9`` (effectively float equality).

    Returns:
        A :class:`SnapshotComparison` with one :class:`FeatureDelta` per
        feature in *current*.

    Example::

        from domain.macro.comparison import compare_snapshots, PriorFeatureInput

        comparison = compare_snapshots(
            current=current_snapshot,
            prior_features=[PriorFeatureInput(indicator_type="gdp", value=3.2)],
            prior_snapshot_label="Q1-2026",
            country="US",
        )
        for delta in comparison.deltas:
            print(delta.indicator_type, delta.direction, delta.delta)
    """
    # Build a lookup map from indicator_type → prior value (first match wins).
    prior_lookup: dict[str, float] = {}
    for p in prior_features:
        if p.indicator_type not in prior_lookup:
            prior_lookup[p.indicator_type] = p.value

    deltas: list[FeatureDelta] = []
    changed = 0
    unchanged = 0
    no_prior = 0

    for feature in current.features:
        ind_key = str(feature.indicator_type)
        curr_val = feature.value

        if ind_key not in prior_lookup:
            deltas.append(
                FeatureDelta(
                    indicator_type=ind_key,
                    current_value=curr_val,
                    prior_value=None,
                    delta=None,
                    direction="no_prior",
                )
            )
            no_prior += 1
        else:
            prior_val = prior_lookup[ind_key]
            delta_val = curr_val - prior_val
            if abs(delta_val) <= unchanged_threshold:
                direction: ChangeDirection = "unchanged"
                unchanged += 1
            elif delta_val > 0:
                direction = "increased"
                changed += 1
            else:
                direction = "decreased"
                changed += 1

            deltas.append(
                FeatureDelta(
                    indicator_type=ind_key,
                    current_value=curr_val,
                    prior_value=prior_val,
                    delta=delta_val,
                    direction=direction,
                )
            )

    return SnapshotComparison(
        country=country,
        prior_snapshot_label=prior_snapshot_label,
        current_snapshot_timestamp=current.snapshot_time,
        deltas=deltas,
        changed_count=changed,
        unchanged_count=unchanged,
        no_prior_count=no_prior,
    )
