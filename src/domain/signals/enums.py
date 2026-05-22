"""Enumerations for signal types and evaluation results."""

from enum import StrEnum


class SignalType(StrEnum):
    """Types of investment signals."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NEUTRAL = "neutral"


class SignalStrength(StrEnum):
    """Strength or confidence level of a signal."""

    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class TrendDirection(StrEnum):
    """Direction of a trend."""

    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
