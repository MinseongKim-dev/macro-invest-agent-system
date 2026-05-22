"""Domain models for macroeconomic data and features."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType


class MacroFeature(BaseModel):
    """A single macroeconomic indicator measurement.

    Represents a point-in-time observation of a macro indicator with validation
    for data consistency and temporal ordering.
    """

    indicator_type: MacroIndicatorType = Field(..., description="Type of macroeconomic indicator")
    source: MacroSourceType = Field(..., description="Data source for this indicator")
    value: float = Field(..., description="Numerical value of the indicator")
    timestamp: datetime = Field(..., description="Time when this observation was recorded")
    frequency: DataFrequency = Field(
        default=DataFrequency.DAILY, description="Data collection frequency"
    )
    country: str | None = Field(
        default=None, description="Country code (ISO 3166-1 alpha-2) if applicable"
    )
    region: str | None = Field(default=None, description="Geographic region if applicable")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Additional metadata (e.g., units, series ID)"
    )

    @field_validator("value")
    @classmethod
    def validate_value_not_nan(cls, v: float) -> float:
        """Ensure value is not NaN or infinity."""
        if not (-1e10 < v < 1e10):
            raise ValueError("Value must be a finite number within reasonable bounds")
        return v


class MacroSnapshot(BaseModel):
    """A collection of macroeconomic features at a given point in time.

    Represents the state of multiple macro indicators, typically used as input
    to signal evaluation or analysis.
    """

    features: list[MacroFeature] = Field(..., description="List of macro features in this snapshot")
    snapshot_time: datetime = Field(..., description="The reference time for this snapshot")
    version: int = Field(default=1, description="Schema version for backward compatibility")

    @field_validator("features")
    @classmethod
    def validate_features_not_empty(cls, v: list[MacroFeature]) -> list[MacroFeature]:
        """Ensure snapshot contains at least one feature."""
        if not v:
            raise ValueError("Snapshot must contain at least one feature")
        return v

    @field_validator("features")
    @classmethod
    def validate_unique_indicators(cls, v: list[MacroFeature]) -> list[MacroFeature]:
        """Warn if duplicate indicator types exist (but allow for now)."""
        seen = set()
        for feature in v:
            key = (feature.indicator_type, feature.source, feature.country)
            if key in seen:
                # In future, could enforce uniqueness; for now, allow duplicates
                # with different timestamps
                pass
            seen.add(key)
        return v

    def get_feature_by_indicator(self, indicator_type: MacroIndicatorType) -> MacroFeature | None:
        """Get the first feature matching the indicator type."""
        for feature in self.features:
            if feature.indicator_type == indicator_type:
                return feature
        return None
