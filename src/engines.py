"""Aleph-One engine layer — polymorphic multi-engine architecture.

Hierarchy::

    BaseEngine (ABC)  ← analyze(ticker, market_data, context_data) → dict
    ├── QuantEngine          — 5/20 EMA crossover + σ → momentum_score
    ├── SentimentEngine      — keyword rule-base → sentiment_score [-1, +1]
    └── PersonaAdapterEngine — weighted blend → BUY/HOLD/SELL + confidence

Target universe: AAPL · MSFT · TSLA · 삼성전자(005930) · SK하이닉스(000660)

Helper::
    build_intelligence_row()  — full UI-contract risk_matrix row per ticker
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Domain constants ──────────────────────────────────────────────────────────

TICKERS: list[str] = ["AAPL", "MSFT", "TSLA", "005930", "000660"]

DISPLAY_NAMES: dict[str, str] = {
    "AAPL":  "AAPL",
    "MSFT":  "MSFT",
    "TSLA":  "TSLA",
    "005930": "삼성전자",
    "000660": "SK하이닉스",
}

TICKER_GROUPS: dict[str, str] = {
    "AAPL":  "TECH",
    "MSFT":  "TECH",
    "TSLA":  "TECH",
    "005930": "KR_TECH",
    "000660": "KR_TECH",
}

# ── Domain types ──────────────────────────────────────────────────────────────

PersonaProfile = Literal["AGGRESSIVE", "CONSERVATIVE", "BALANCED"]
Signal         = Literal["BUY", "HOLD", "SELL"]
MarketStatus   = Literal["WATCH", "STABLE"]

_PERSONA_WEIGHTS: dict[PersonaProfile, dict[str, float]] = {
    "AGGRESSIVE":   {"quant": 0.70, "sentiment": 0.30},
    "BALANCED":     {"quant": 0.50, "sentiment": 0.50},
    "CONSERVATIVE": {"quant": 0.30, "sentiment": 0.70},
}

# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuantResult:
    ticker:         str
    momentum_score: float   # 0.0 – 1.0
    volatility:     float   # annualised σ
    status:         MarketStatus
    ema5_last:      float
    ema20_last:     float
    macd_hist:      float
    crossover_bull: bool    # EMA5 > EMA20


@dataclass(frozen=True)
class SentimentResult:
    ticker:          str
    sentiment_score: float  # -1.0 – 1.0
    positive_ratio:  float
    negative_ratio:  float
    sample_size:     int


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseEngine(ABC):
    """Abstract interface every Aleph-One engine must implement."""

    @abstractmethod
    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        """Run analysis and return a serialisable result dict."""


# ── Quant Engine ──────────────────────────────────────────────────────────────

_EMA_FAST:     int   = 5
_EMA_SLOW:     int   = 20
_EMA_SIGNAL:   int   = 9
_TRADING_DAYS: int   = 252
_NORM_HALF:    float = 0.02   # ±2 % of price scale → [0, 1] momentum range


class QuantEngine(BaseEngine):
    """5/20 EMA crossover + annualised volatility → momentum_score.

    Requires ≥20 rows in market_data with a ``close_price`` column.
    Falls back to neutral (0.5) when data is insufficient.
    """

    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,
        context_data: list[str],    # unused — satisfies BaseEngine contract
    ) -> dict[str, Any]:
        try:
            result = self._compute(ticker, market_data)
        except Exception as exc:
            logger.warning("quant_fallback", extra={"ticker": ticker, "error": str(exc)})
            result = self._neutral(ticker)

        logger.debug(
            "quant_result",
            extra={"ticker": ticker, "momentum": result.momentum_score, "status": result.status},
        )
        return {
            "ticker":         result.ticker,
            "momentum_score": result.momentum_score,
            "volatility":     result.volatility,
            "status":         result.status,
            "ema5_last":      result.ema5_last,
            "ema20_last":     result.ema20_last,
            "macd_hist":      result.macd_hist,
            "crossover_bull": result.crossover_bull,
        }

    def _compute(self, ticker: str, df: pd.DataFrame) -> QuantResult:
        if df.empty or "close_price" not in df.columns:
            raise ValueError(f"no close_price data for {ticker}")
        if len(df) < _EMA_SLOW:
            raise ValueError(f"need ≥{_EMA_SLOW} rows, got {len(df)}")

        close  = df["close_price"].astype(float)
        ema5   = close.ewm(span=_EMA_FAST,   adjust=False).mean()
        ema20  = close.ewm(span=_EMA_SLOW,   adjust=False).mean()
        macd   = ema5 - ema20
        signal = macd.ewm(span=_EMA_SIGNAL,  adjust=False).mean()
        hist   = macd - signal

        last_hist  = float(hist.iloc[-1])
        last_ema5  = float(ema5.iloc[-1])
        last_ema20 = float(ema20.iloc[-1])

        # Annualised volatility from daily log-returns (vectorised)
        log_ret    = np.log(close / close.shift(1)).dropna()
        volatility = float(log_ret.std() * math.sqrt(_TRADING_DAYS))

        # Momentum score: normalise MACD hist relative to mean price scale
        price_scale    = max(float(close.mean()), 1e-8)
        raw            = last_hist / price_scale
        momentum_score = float(np.clip((raw + _NORM_HALF) / (2 * _NORM_HALF), 0.0, 1.0))

        status: MarketStatus = (
            "WATCH" if (momentum_score > 0.65 or volatility > 0.35) else "STABLE"
        )

        return QuantResult(
            ticker=ticker, momentum_score=momentum_score, volatility=volatility,
            status=status, ema5_last=last_ema5, ema20_last=last_ema20,
            macd_hist=last_hist, crossover_bull=(last_ema5 > last_ema20),
        )

    @staticmethod
    def _neutral(ticker: str) -> QuantResult:
        return QuantResult(
            ticker=ticker, momentum_score=0.5, volatility=0.2,
            status="STABLE", ema5_last=0.0, ema20_last=0.0,
            macd_hist=0.0, crossover_bull=False,
        )


# ── Sentiment Engine ──────────────────────────────────────────────────────────

_POSITIVE_WORDS: frozenset[str] = frozenset({
    "growth", "surpass", "bullish", "beat", "rally", "surge", "record",
    "upgrade", "outperform", "strong", "exceed", "gain", "recovery", "expansion",
    "boost", "breakout", "optimistic", "profit", "upside", "positive",
})
_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "drag", "drop", "bearish", "miss", "decline", "fall", "loss", "downgrade",
    "underperform", "weak", "below", "cut", "risk", "warn", "crisis",
    "sell-off", "recession", "contraction", "slump", "plunge", "concern",
})
_STRIP_CHARS: str = ".,!?;:'\"()\n\t"


class SentimentEngine(BaseEngine):
    """Keyword rule-base → sentiment_score (-1.0 – 1.0).

    ``market_data`` is accepted but unused — preserves BaseEngine contract.
    """

    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,    # unused — satisfies BaseEngine contract
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            result = self._score(ticker, context_data)
        except Exception as exc:
            logger.warning("sentiment_fallback", extra={"ticker": ticker, "error": str(exc)})
            result = SentimentResult(ticker=ticker, sentiment_score=0.0,
                                     positive_ratio=0.0, negative_ratio=0.0, sample_size=0)

        logger.debug(
            "sentiment_result",
            extra={"ticker": ticker, "score": result.sentiment_score, "n": result.sample_size},
        )
        return {
            "ticker":          result.ticker,
            "sentiment_score": result.sentiment_score,
            "positive_ratio":  result.positive_ratio,
            "negative_ratio":  result.negative_ratio,
            "sample_size":     result.sample_size,
        }

    def _score(self, ticker: str, texts: list[str]) -> SentimentResult:
        positive = 0
        negative = 0
        total    = 0

        for text in texts:
            tokens = text.lower().split()
            total += len(tokens)
            for token in tokens:
                clean = token.strip(_STRIP_CHARS)
                if clean in _POSITIVE_WORDS:
                    positive += 1
                elif clean in _NEGATIVE_WORDS:
                    negative += 1

        if total == 0:
            return SentimentResult(ticker=ticker, sentiment_score=0.0,
                                   positive_ratio=0.0, negative_ratio=0.0, sample_size=0)

        pos_r = positive / total
        neg_r = negative / total
        score = float(np.clip(pos_r - neg_r, -1.0, 1.0))

        return SentimentResult(
            ticker=ticker, sentiment_score=score,
            positive_ratio=pos_r, negative_ratio=neg_r, sample_size=len(texts),
        )


# ── Persona Adapter Engine ────────────────────────────────────────────────────

_BUY_THRESHOLD:  float = 0.15
_SELL_THRESHOLD: float = -0.15


class PersonaAdapterEngine(BaseEngine):
    """Hyper-personalisation layer: blends quant + sentiment by user profile.

    Args:
        persona: ``"AGGRESSIVE"`` (default) | ``"BALANCED"`` | ``"CONSERVATIVE"``
    """

    def __init__(self, persona: PersonaProfile = "AGGRESSIVE") -> None:
        self._persona:   PersonaProfile = persona
        self._quant:     QuantEngine     = QuantEngine()
        self._sentiment: SentimentEngine = SentimentEngine()

    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            quant_d     = self._quant.analyze(ticker, market_data, context_data)
            sentiment_d = self._sentiment.analyze(ticker, market_data, context_data)

            weights   = _PERSONA_WEIGHTS[self._persona]
            q_score   = (quant_d["momentum_score"] - 0.5) * 2.0   # [0,1] → [-1,+1]
            composite = weights["quant"] * q_score + weights["sentiment"] * sentiment_d["sentiment_score"]

            confidence = float(np.clip(abs(composite), 0.0, 1.0))
            signal: Signal = (
                "BUY"  if composite > _BUY_THRESHOLD  else
                "SELL" if composite < _SELL_THRESHOLD  else
                "HOLD"
            )
            strategy = _strategy_text(ticker, signal, quant_d, sentiment_d)

            logger.info(
                "persona_result",
                extra={"ticker": ticker, "signal": signal,
                       "confidence": round(confidence, 3), "persona": self._persona},
            )
            return {
                "ticker":     ticker,
                "signal":     signal,
                "confidence": confidence,
                "strategy":   strategy,
                "persona":    self._persona,
                "quant":      quant_d,
                "sentiment":  sentiment_d,
            }
        except Exception as exc:
            logger.error("persona_adapter_error",
                         extra={"ticker": ticker, "persona": self._persona, "error": str(exc)})
            raise


def _strategy_text(
    ticker:     str,
    signal:     Signal,
    quant_d:    dict[str, Any],
    sentiment_d: dict[str, Any],
) -> str:
    name  = DISPLAY_NAMES.get(ticker, ticker)
    score = sentiment_d.get("sentiment_score", 0.0)
    vol   = quant_d.get("volatility", 0.0)
    bull  = quant_d.get("crossover_bull", False)

    if signal == "BUY":
        return (
            f"{name}: EMA5{'>' if bull else '<'}EMA20 crossover bullish — "
            f"momentum surge, sentiment {score:+.2f}"
        )
    if signal == "SELL":
        return (
            f"{name}: EMA crossdown detected — momentum deteriorating, "
            f"sentiment drag {score:+.2f}, σ={vol:.2f}"
        )
    return (
        f"{name}: Neutral posture — monitoring EMA convergence, "
        f"volatility σ={vol:.2f}"
    )


# ── Orchestration helper ──────────────────────────────────────────────────────

def build_intelligence_row(
    ticker:      str,
    price_df:    pd.DataFrame,
    news:        list[str],
    macro_phase: str,
    persona:     PersonaProfile = "AGGRESSIVE",
) -> dict[str, Any]:
    """Run the full engine pipeline and return a UI-contract risk_matrix row.

    Args:
        ticker:      Internal ticker code (e.g. ``"005930"``).
        price_df:    DataFrame with ``close_price`` column (≥20 rows).
        news:        News headline strings for SentimentEngine.
        macro_phase: Current macro phase string (e.g. ``"LATE_CYCLE"``).
        persona:     Investor persona profile.

    Returns:
        Dict matching the ``risk_matrix`` entry shape from the UI contract.
    """
    engine = PersonaAdapterEngine(persona)
    result = engine.analyze(ticker, price_df, news)

    phase_up    = macro_phase.upper()
    macro_watch = "LATE" in phase_up or "CONTRACT" in phase_up
    rate_status: MarketStatus  = "WATCH" if macro_watch else "STABLE"
    sent_watch  = result["sentiment"]["sentiment_score"] < -0.1
    sent_status: MarketStatus  = "WATCH" if sent_watch else "STABLE"

    return {
        "ticker":    DISPLAY_NAMES.get(ticker, ticker),
        "momentum":  result["quant"]["status"],
        "regime":    rate_status,
        "rates":     rate_status,
        "sentiment": sent_status,
        "sig_score": result["signal"],
        # Internal — used for portfolio_health computation, not exposed to UI
        "_confidence": result["confidence"],
    }
