"""Macroeconomic domain models and contracts."""

from domain.macro.comparison import (
    FeatureDelta,
    PriorFeatureInput,
    SnapshotComparison,
    compare_snapshots,
)
from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature, MacroSnapshot
from domain.macro.regime import (
    REGIME_LABEL_FAMILY_MAP,
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
    regime_family_for_label,
)
from domain.macro.regime_mapping import (
    build_regime_rationale,
    derive_regime_confidence,
    derive_regime_missing_inputs,
    map_snapshot_to_regime,
    map_snapshot_to_regime_label,
)
from domain.macro.regime_transition import derive_regime_transition

__all__ = [
    "MacroIndicatorType",
    "MacroSourceType",
    "DataFrequency",
    "MacroFeature",
    "MacroSnapshot",
    "PriorFeatureInput",
    "FeatureDelta",
    "SnapshotComparison",
    "compare_snapshots",
    "RegimeLabel",
    "RegimeFamily",
    "RegimeConfidence",
    "REGIME_LABEL_FAMILY_MAP",
    "regime_family_for_label",
    "map_snapshot_to_regime_label",
    "map_snapshot_to_regime",
    "build_regime_rationale",
    "derive_regime_confidence",
    "derive_regime_missing_inputs",
    "derive_regime_transition",
    "RegimeTransitionType",
    "RegimeTransition",
    "MacroRegime",
]
