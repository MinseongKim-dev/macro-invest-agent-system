"""Aleph-One engine layer — polymorphic multi-engine architecture.

Hierarchy::

    BaseEngine (ABC)
    ├── QuantEngine          — MACD + annualised volatility → momentum score
    ├── SentimentEngine      — keyword rule-base → sentiment score (-1 to +1)
    └── PersonaAdapterEngine — weights by profile → BUY / HOLD / SELL + confidence

All engines share the same ``analyze(ticker, market_data, context_data) -> dict``
interface so they can be composed, swapped, or wrapped uniformly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Domain types ──────────────────────────────────────────────────────────────

PersonaProfile = Literal["AGGRESSIVE", "CONSERVATIVE", "BALANCED"]
Signal = Literal["BUY", "HOLD", "SELL"]
MarketStatus = Literal["WATCH", "STABLE"]


@dataclass(frozen=True)
class QuantResult:
    ticker: str
    momentum_score: float  # 0.0 – 1.0  (higher = stronger bullish momentum)
    volatility: float      # annualised σ
    status: MarketStatus
    macd_signal: float
    macd_hist: float


@dataclass(frozen=True)
class SentimentResult:
    ticker: str
    sentiment_score: float  # -1.0 – 1.0  (positive = bullish)
    positive_ratio: float
    negative_ratio: float
    sample_size: int


@dataclass(frozen=True)
class IntelligenceResult:
    ticker: str
    signal: Signal
    confidence: float       # 0.0 – 1.0
    persona: PersonaProfile
    quant: QuantResult
    sentiment: SentimentResult


# ── Base ──────────────────────────────────────────────────────────────────────


class BaseEngine(ABC):
    """Abstract interface every Aleph-One engine must implement.

    Engines are stateless with respect to individual analyses — all state
    is passed explicitly via arguments.
    """

    @abstractmethod
    def analyze(
        self,
        ticker: str,
        market_data: pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        """Run analysis and return a serialisable result dict."""


# ── Quant Engine ──────────────────────────────────────────────────────────────

_MACD_FAST: int = 12
_MACD_SLOW: int = 26
_MACD_SIG: int = 9
_TRADING_DAYS: int = 252

# Momentum normalisation window: MACD-hist / price_scale maps ±2 % → 0–1
_NORM_HALF: float = 0.02


class QuantEngine(BaseEngine):
    """Mathematical engine: MACD + annualised volatility → momentum scoring.

    Input DataFrame must contain a ``close_price`` column.
    Requires at least ``_MACD_SLOW`` (26) data points.
    """

    def analyze(
        self,
        ticker: str,
        market_data: pd.DataFrame,
        context_data: list[str],  # not used by quant — satisfies interface
    ) -> dict[str, Any]:
        try:
            result = self._compute(ticker, market_data)
            logger.info(
                "quant_analysis_complete",
                extra={"ticker": ticker, "signal": result.status, "momentum": result.momentum_score},
            )
            return {
                "ticker": result.ticker,
                "momentum_score": result.momentum_score,
                "volatility": result.volatility,
                "status": result.status,
                "macd_signal": result.macd_signal,
                "macd_hist": result.macd_hist,
            }
        except Exception as exc:
            logger.error("quant_engine_error", extra={"ticker": ticker, "error": str(exc)})
            raise

    def _compute(self, ticker: str, df: pd.DataFrame) -> QuantResult:
        if df.empty or "close_price" not in df.columns:
            raise ValueError(f"market_data for {ticker} is empty or missing 'close_price'")

        close = df["close_price"].astype(float)

        if len(close) < _MACD_SLOW:
            raise ValueError(
                f"Insufficient data for {ticker}: need ≥{_MACD_SLOW} points, got {len(close)}"
            )

        ema_fast = close.ewm(span=_MACD_FAST, adjust=False).mean()
        ema_slow = close.ewm(span=_MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=_MACD_SIG, adjust=False).mean()

        macd_hist = float((macd_line - signal_line).iloc[-1])
        macd_signal = float(signal_line.iloc[-1])

        # Annualised volatility from daily log returns
        returns = close.pct_change().dropna()
        volatility = float(returns.std() * np.sqrt(_TRADING_DAYS))

        # Momentum score: normalise MACD histogram relative to mean price level
        price_scale = max(float(close.mean()), 1e-8)
        raw_momentum = macd_hist / price_scale
        momentum_score = float(np.clip((raw_momentum + _NORM_HALF) / (2 * _NORM_HALF), 0.0, 1.0))

        status: MarketStatus = "WATCH" if (momentum_score > 0.65 or volatility > 0.35) else "STABLE"

        logger.debug(
            "quant_result",
            extra={
                "ticker": ticker,
                "momentum": round(momentum_score, 4),
                "volatility": round(volatility, 4),
                "status": status,
            },
        )
        return QuantResult(
            ticker=ticker,
            momentum_score=momentum_score,
            volatility=volatility,
            status=status,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
        )


# ── Sentiment Engine ──────────────────────────────────────────────────────────

_POSITIVE_WORDS: frozenset[str] = frozenset({
    "beat", "surge", "rally", "record", "profit", "growth", "upgrade",
    "bullish", "outperform", "strong", "exceed", "gain", "rise",
    "positive", "optimistic", "recovery", "expansion", "boost", "breakout",
})
_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "miss", "drop", "fall", "loss", "decline", "downgrade", "bearish",
    "underperform", "weak", "below", "cut", "risk", "warn", "crisis",
    "sell-off", "recession", "contraction", "slump", "plunge", "concern",
})
_STRIP_CHARS: str = ".,!?;:'\"()\n\t"


class SentimentEngine(BaseEngine):
    """Rule-based NLP engine: keyword ratios → sentiment score (-1.0 – 1.0).

    ``market_data`` is accepted but not used, preserving the BaseEngine contract.
    """

    def analyze(
        self,
        ticker: str,
        market_data: pd.DataFrame,  # not used by sentiment — satisfies interface
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            result = self._score(ticker, context_data)
            logger.info(
                "sentiment_analysis_complete",
                extra={"ticker": ticker, "score": result.sentiment_score, "samples": result.sample_size},
            )
            return {
                "ticker": result.ticker,
                "sentiment_score": result.sentiment_score,
                "positive_ratio": result.positive_ratio,
                "negative_ratio": result.negative_ratio,
                "sample_size": result.sample_size,
            }
        except Exception as exc:
            logger.error("sentiment_engine_error", extra={"ticker": ticker, "error": str(exc)})
            raise

    def _score(self, ticker: str, texts: list[str]) -> SentimentResult:
        positive = 0
        negative = 0
        total_tokens = 0

        for text in texts:
            tokens = text.lower().split()
            total_tokens += len(tokens)
            for token in tokens:
                clean = token.strip(_STRIP_CHARS)
                if clean in _POSITIVE_WORDS:
                    positive += 1
                elif clean in _NEGATIVE_WORDS:
                    negative += 1

        if total_tokens == 0:
            return SentimentResult(
                ticker=ticker,
                sentiment_score=0.0,
                positive_ratio=0.0,
                negative_ratio=0.0,
                sample_size=0,
            )

        pos_ratio = positive / total_tokens
        neg_ratio = negative / total_tokens
        score = float(np.clip(pos_ratio - neg_ratio, -1.0, 1.0))

        logger.debug(
            "sentiment_result",
            extra={"ticker": ticker, "score": score, "pos": pos_ratio, "neg": neg_ratio},
        )
        return SentimentResult(
            ticker=ticker,
            sentiment_score=score,
            positive_ratio=pos_ratio,
            negative_ratio=neg_ratio,
            sample_size=len(texts),
        )


# ── Persona Adapter Engine ────────────────────────────────────────────────────

_PERSONA_WEIGHTS: dict[PersonaProfile, dict[str, float]] = {
    "AGGRESSIVE":   {"quant": 0.70, "sentiment": 0.30},
    "BALANCED":     {"quant": 0.50, "sentiment": 0.50},
    "CONSERVATIVE": {"quant": 0.30, "sentiment": 0.70},
}

# Composite score thresholds for signal classification
_BUY_THRESHOLD: float = 0.15
_SELL_THRESHOLD: float = -0.15


class PersonaAdapterEngine(BaseEngine):
    """Hyper-personalisation layer: blends quant + sentiment by user profile.

    Internally composes a ``QuantEngine`` and a ``SentimentEngine``, then
    applies persona-specific weights to derive a final investment signal.

    Args:
        persona: One of ``"AGGRESSIVE"``, ``"BALANCED"``, ``"CONSERVATIVE"``.
    """

    def __init__(self, persona: PersonaProfile = "BALANCED") -> None:
        self._persona: PersonaProfile = persona
        self._quant = QuantEngine()
        self._sentiment = SentimentEngine()

    def analyze(
        self,
        ticker: str,
        market_data: pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            quant_dict = self._quant.analyze(ticker, market_data, context_data)
            sentiment_dict = self._sentiment.analyze(ticker, market_data, context_data)

            quant_r = QuantResult(**quant_dict)
            sentiment_r = SentimentResult(**sentiment_dict)

            signal, confidence = self._adapt(quant_r, sentiment_r)

            logger.info(
                "intelligence_result",
                extra={
                    "ticker": ticker,
                    "signal": signal,
                    "confidence": round(confidence, 3),
                    "persona": self._persona,
                },
            )
            return {
                "ticker": ticker,
                "signal": signal,
                "confidence": confidence,
                "persona": self._persona,
                "quant": quant_dict,
                "sentiment": sentiment_dict,
            }
        except Exception as exc:
            logger.error(
                "persona_adapter_error",
                extra={"ticker": ticker, "persona": self._persona, "error": str(exc)},
            )
            raise

    def _adapt(self, quant: QuantResult, sentiment: SentimentResult) -> tuple[Signal, float]:
        """Compute weighted composite score and derive signal + confidence."""
        weights = _PERSONA_WEIGHTS[self._persona]

        # Normalise momentum_score [0,1] → [-1,+1] for symmetric blending
        quant_score = (quant.momentum_score - 0.5) * 2.0

        composite = (
            weights["quant"] * quant_score
            + weights["sentiment"] * sentiment.sentiment_score
        )

        confidence = float(np.clip(abs(composite), 0.0, 1.0))

        if composite > _BUY_THRESHOLD:
            signal: Signal = "BUY"
        elif composite < _SELL_THRESHOLD:
            signal = "SELL"
        else:
            signal = "HOLD"

        return signal, confidence
