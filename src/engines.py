"""Aleph-One engine layer — polymorphic multi-engine architecture.

Hierarchy::

    BaseEngine (ABC)  ← analyze(ticker, market_data, context_data) → dict
    ├── QuantEngine          — 5/20 SMA golden/dead-cross + 20-day σ → momentum_score
    ├── SentimentEngine      — weighted financial lexicon → sentiment_score [-1, +1]
    └── PersonaAdapterEngine — persona weight-matrix blend → BUY/HOLD/SELL + confidence

Target universe: AAPL · MSFT · TSLA · 삼성전자(005930) · SK하이닉스(000660)

Helper::
    build_intelligence_row()  — full UI-contract risk_matrix row per ticker
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Domain constants ──────────────────────────────────────────────────────────

TICKERS: list[str] = ["AAPL", "MSFT", "TSLA", "005930", "000660"]

DISPLAY_NAMES: dict[str, str] = {
    "AAPL":   "AAPL",
    "MSFT":   "MSFT",
    "TSLA":   "TSLA",
    "005930": "삼성전자",
    "000660": "SK하이닉스",
}

TICKER_GROUPS: dict[str, str] = {
    "AAPL":   "TECH",
    "MSFT":   "TECH",
    "TSLA":   "TECH",
    "005930": "KR_TECH",
    "000660": "KR_TECH",
}

# ── Domain types ──────────────────────────────────────────────────────────────

PersonaProfile = Literal["AGGRESSIVE", "CONSERVATIVE", "BALANCED"]
Signal         = Literal["BUY", "HOLD", "SELL"]
MarketStatus   = Literal["WATCH", "STABLE"]

# Persona weight matrices — fraction of quant vs sentiment score in composite
_PERSONA_WEIGHTS: dict[PersonaProfile, dict[str, float]] = {
    "AGGRESSIVE":   {"quant": 0.70, "sentiment": 0.30},
    "BALANCED":     {"quant": 0.50, "sentiment": 0.50},
    "CONSERVATIVE": {"quant": 0.30, "sentiment": 0.70},
}

# Per-persona BUY/SELL composite thresholds — AGGRESSIVE fires at lower conviction
_PERSONA_THRESHOLDS: dict[PersonaProfile, dict[str, float]] = {
    "AGGRESSIVE":   {"buy": 0.10, "sell": -0.10},
    "BALANCED":     {"buy": 0.15, "sell": -0.15},
    "CONSERVATIVE": {"buy": 0.25, "sell": -0.25},
}

# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QuantResult:
    ticker:         str
    momentum_score: float        # 0.0 – 1.0  (>0.5 = bullish bias from SMA spread)
    volatility:     float        # raw std-dev of 20-day close prices (price units)
    vol_ratio:      float        # volatility / mean_price  (dimensionless coefficient)
    status:         MarketStatus # WATCH if vol_ratio > 5%, else STABLE
    sma5_last:      float        # latest 5-day Simple Moving Average
    sma20_last:     float        # latest 20-day Simple Moving Average
    crossover_bull: bool         # SMA5 > SMA20 on the current bar
    golden_cross:   bool         # SMA5 just crossed above SMA20 (prev bar was below)
    dead_cross:     bool         # SMA5 just crossed below SMA20 (prev bar was above)


@dataclass(frozen=True)
class SentimentResult:
    ticker:          str
    sentiment_score: float  # -1.0 – +1.0
    positive_ratio:  float  # fraction of total tokens that matched positive-weight words
    negative_ratio:  float  # fraction of total tokens that matched negative-weight words
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

_SMA_FAST:      int   = 5
_SMA_SLOW:      int   = 20
_VOL_THRESHOLD: float = 0.05   # std-dev / mean_price > 5 % → WATCH
_NORM_FACTOR:   float = 5.0    # SMA spread-ratio → score: ±20 % spread saturates [0, 1]


class QuantEngine(BaseEngine):
    """5/20 SMA golden-cross + 20-day std-dev volatility → momentum_score.

    Inputs
    ------
    market_data : pd.DataFrame with a ``close_price`` column and ≥20 rows.
                  Supply the last 20 trading days from ``market_ticks`` via
                  ``database.get_connection()`` for real computed results.

    Signal logic
    ------------
    * Golden cross (SMA5 just crossed above SMA20) → momentum surge detected
    * Dead   cross (SMA5 just crossed below SMA20) → momentum deterioration
    * momentum_score ∈ [0, 1]: derived from the SMA spread ratio (>0.5 = bullish)
    * Volatility threshold: std-dev > 5% of 20-day mean price → status = WATCH
    """

    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            result = self._compute(ticker, market_data)
        except Exception as exc:
            logger.warning("quant_fallback", extra={"ticker": ticker, "error": str(exc)})
            result = self._neutral(ticker)

        logger.debug(
            "quant_result",
            extra={
                "ticker": ticker, "momentum": result.momentum_score,
                "status": result.status,
                "golden": result.golden_cross, "dead": result.dead_cross,
                "vol_ratio": round(result.vol_ratio, 4),
            },
        )
        return {
            "ticker":         result.ticker,
            "momentum_score": result.momentum_score,
            "volatility":     result.volatility,
            "vol_ratio":      result.vol_ratio,
            "status":         result.status,
            "sma5_last":      result.sma5_last,
            "sma20_last":     result.sma20_last,
            "crossover_bull": result.crossover_bull,
            "golden_cross":   result.golden_cross,
            "dead_cross":     result.dead_cross,
        }

    def _compute(self, ticker: str, df: pd.DataFrame) -> QuantResult:
        if df.empty or "close_price" not in df.columns:
            raise ValueError(f"no close_price data for {ticker}")
        if len(df) < _SMA_SLOW:
            raise ValueError(f"need ≥{_SMA_SLOW} rows, got {len(df)}")

        close = df["close_price"].astype(float)

        # ── Simple Moving Averages ────────────────────────────────────────────
        sma5  = close.rolling(window=_SMA_FAST,  min_periods=_SMA_FAST).mean()
        sma20 = close.rolling(window=_SMA_SLOW,  min_periods=_SMA_SLOW).mean()

        last_sma5  = float(sma5.iloc[-1])
        last_sma20 = float(sma20.iloc[-1])
        prev_sma5  = float(sma5.iloc[-2])
        prev_sma20 = float(sma20.iloc[-2])

        # ── Golden / Dead cross detection ─────────────────────────────────────
        golden_cross = (last_sma5 > last_sma20) and (prev_sma5 <= prev_sma20)
        dead_cross   = (last_sma5 < last_sma20) and (prev_sma5 >= prev_sma20)

        # ── Momentum score: normalised SMA spread ─────────────────────────────
        # spread_ratio ∈ [−∞, +∞]; ±20% saturates to [0.0, 1.0] via _NORM_FACTOR=5
        spread_ratio   = (last_sma5 - last_sma20) / max(abs(last_sma20), 1e-8)
        momentum_score = float(np.clip(0.5 + spread_ratio * _NORM_FACTOR, 0.0, 1.0))

        # ── Volatility: std-dev of last 20 closes ─────────────────────────────
        tail_20    = close.tail(_SMA_SLOW)
        volatility = float(tail_20.std())
        mean_price = float(tail_20.mean())
        vol_ratio  = volatility / max(mean_price, 1e-8)

        status: MarketStatus = "WATCH" if vol_ratio > _VOL_THRESHOLD else "STABLE"

        return QuantResult(
            ticker=ticker,
            momentum_score=momentum_score,
            volatility=volatility,
            vol_ratio=vol_ratio,
            status=status,
            sma5_last=last_sma5,
            sma20_last=last_sma20,
            crossover_bull=(last_sma5 > last_sma20),
            golden_cross=golden_cross,
            dead_cross=dead_cross,
        )

    @staticmethod
    def _neutral(ticker: str) -> QuantResult:
        return QuantResult(
            ticker=ticker, momentum_score=0.5, volatility=0.0, vol_ratio=0.0,
            status="STABLE", sma5_last=0.0, sma20_last=0.0,
            crossover_bull=False, golden_cross=False, dead_cross=False,
        )


# ── Sentiment Engine ──────────────────────────────────────────────────────────

# Financial-domain weighted lexicon.
# Positive weights (>0) = bullish signal; negative weights (<0) = bearish.
# Magnitude reflects signal strength in a macro/equity investment context.
_WEIGHTED_LEXICON: dict[str, float] = {
    # ── Strong positive ────────────────────────────────────────────────────────
    "breakout":      0.90, "bullish":      0.85, "surge":        0.85,
    "rally":         0.80, "record":       0.80, "beat":         0.80,
    "exceed":        0.80, "outperform":   0.80, "surpass":      0.75,
    "boom":          0.80,
    # ── Moderate positive ──────────────────────────────────────────────────────
    "growth":        0.70, "expansion":    0.70, "boost":        0.65,
    "recovery":      0.65, "upgrade":      0.65, "profit":       0.60,
    "gain":          0.60, "upside":       0.55, "positive":     0.55,
    "strong":        0.55, "optimistic":   0.55,
    # ── Mildly positive ────────────────────────────────────────────────────────
    "resilient":     0.35, "stabilize":    0.30, "support":      0.25,
    # ── Macro headwinds (mildly negative for equity multiples) ─────────────────
    "tightening":   -0.25, "inflation":   -0.30, "uncertainty":  -0.20,
    "headwind":     -0.35, "pressure":    -0.35,
    # ── Moderate negative ──────────────────────────────────────────────────────
    "concern":      -0.35, "risk":        -0.30, "warn":        -0.45,
    "weak":         -0.45, "below":       -0.35, "decline":     -0.50,
    "cut":          -0.45, "drag":        -0.55, "miss":        -0.60,
    "loss":         -0.70,
    # ── Strong negative ────────────────────────────────────────────────────────
    "bearish":      -0.85, "drop":        -0.70, "fall":        -0.65,
    "crisis":       -0.85, "plunge":      -0.85, "sell-off":    -0.80,
    "slump":        -0.75, "recession":   -0.85, "contraction": -0.70,
    "downgrade":    -0.70, "underperform":-0.70,
}

_STRIP_CHARS: str  = ".,!?;:'\"()\n\t"
# Amplifier: weighted_sum / total_tokens × scale → typical 5% hit-rate × avg 0.7 ≈ 0.7 output
_SENT_SCALE: float = 20.0


class SentimentEngine(BaseEngine):
    """Weighted financial lexicon → precision sentiment_score (-1.0 to +1.0).

    Scanning method: token-level lookup against ``_WEIGHTED_LEXICON``.
    Scoring formula: weighted_sum / total_tokens × ``_SENT_SCALE``, clipped to [-1, +1].

    ``market_data`` is accepted but unused — preserves the BaseEngine contract.
    """

    def analyze(
        self,
        ticker:       str,
        market_data:  pd.DataFrame,
        context_data: list[str],
    ) -> dict[str, Any]:
        try:
            result = self._score(ticker, context_data)
        except Exception as exc:
            logger.warning("sentiment_fallback", extra={"ticker": ticker, "error": str(exc)})
            result = SentimentResult(
                ticker=ticker, sentiment_score=0.0,
                positive_ratio=0.0, negative_ratio=0.0, sample_size=0,
            )

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
        weighted_sum  = 0.0
        total_tokens  = 0
        positive_hits = 0
        negative_hits = 0

        for text in texts:
            tokens = [t.strip(_STRIP_CHARS) for t in text.lower().split()]
            total_tokens += len(tokens)
            for token in tokens:
                weight = _WEIGHTED_LEXICON.get(token, 0.0)
                if weight != 0.0:
                    weighted_sum += weight
                    if weight > 0.0:
                        positive_hits += 1
                    else:
                        negative_hits += 1

        if total_tokens == 0:
            return SentimentResult(
                ticker=ticker, sentiment_score=0.0,
                positive_ratio=0.0, negative_ratio=0.0, sample_size=0,
            )

        raw   = weighted_sum / total_tokens * _SENT_SCALE
        score = float(np.clip(raw, -1.0, 1.0))

        return SentimentResult(
            ticker=ticker,
            sentiment_score=score,
            positive_ratio=positive_hits / total_tokens,
            negative_ratio=negative_hits / total_tokens,
            sample_size=len(texts),
        )


# ── Persona Adapter Engine ────────────────────────────────────────────────────


class PersonaAdapterEngine(BaseEngine):
    """Hyper-personalisation layer: blends quant + sentiment by investor persona.

    Weight matrices and thresholds by persona
    -----------------------------------------
    AGGRESSIVE:   quant 70% / sentiment 30%  |  BUY if composite > +0.10
    BALANCED:     quant 50% / sentiment 50%  |  BUY if composite > +0.15
    CONSERVATIVE: quant 30% / sentiment 70%  |  BUY if composite > +0.25

    Composite composite ∈ [−1, +1]:
        composite = w_q × (momentum_score − 0.5) × 2  +  w_s × sentiment_score
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

            weights    = _PERSONA_WEIGHTS[self._persona]
            thresholds = _PERSONA_THRESHOLDS[self._persona]

            # Map momentum_score [0, 1] → [-1, +1] for composite arithmetic
            q_score   = (quant_d["momentum_score"] - 0.5) * 2.0
            composite = (weights["quant"]     * q_score
                         + weights["sentiment"] * sentiment_d["sentiment_score"])

            confidence = float(np.clip(abs(composite), 0.0, 1.0))
            signal: Signal = (
                "BUY"  if composite > thresholds["buy"]  else
                "SELL" if composite < thresholds["sell"] else
                "HOLD"
            )
            strategy = _strategy_text(ticker, signal, quant_d, sentiment_d)

            logger.info(
                "persona_result",
                extra={
                    "ticker": ticker, "signal": signal,
                    "confidence": round(confidence, 3), "persona": self._persona,
                    "composite": round(composite, 4),
                },
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
            logger.error(
                "persona_adapter_error",
                extra={"ticker": ticker, "persona": self._persona, "error": str(exc)},
            )
            raise


def _strategy_text(
    ticker:      str,
    signal:      Signal,
    quant_d:     dict[str, Any],
    sentiment_d: dict[str, Any],
) -> str:
    name   = DISPLAY_NAMES.get(ticker, ticker)
    score  = sentiment_d.get("sentiment_score", 0.0)
    vol_r  = quant_d.get("vol_ratio", 0.0)
    golden = quant_d.get("golden_cross", False)
    dead   = quant_d.get("dead_cross",   False)
    bull   = quant_d.get("crossover_bull", False)

    if signal == "BUY":
        cross = "Golden Cross — " if golden else ("SMA5>SMA20 — " if bull else "")
        return f"{name}: {cross}momentum surge, sentiment {score:+.2f}"
    if signal == "SELL":
        cross = "Dead Cross — " if dead else ("SMA5<SMA20 — " if not bull else "")
        return f"{name}: {cross}momentum deteriorating, sentiment drag {score:+.2f}, vol={vol_r:.1%}"
    return f"{name}: Neutral posture — monitoring SMA convergence, vol={vol_r:.1%}"


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
        price_df:    DataFrame with ``close_price`` column, ≥20 rows.
                     Typically: last 20 rows from ``market_ticks`` + latest live tick.
        news:        News headline strings for SentimentEngine.
        macro_phase: Current macro phase string (e.g. ``"LATE_CYCLE"``).
        persona:     Investor persona profile.

    Returns:
        Dict matching the ``risk_matrix`` entry shape from the UI contract.
        Includes internal ``_confidence`` key used for portfolio_health scoring.
    """
    engine = PersonaAdapterEngine(persona)
    result = engine.analyze(ticker, price_df, news)

    quant_dict = result["quant"]

    # Momentum: WATCH when volatility threshold exceeded OR a crossover event fired
    crossover_event   = quant_dict.get("golden_cross", False) or quant_dict.get("dead_cross", False)
    momentum_status: MarketStatus = (
        "WATCH" if (quant_dict["status"] == "WATCH" or crossover_event) else "STABLE"
    )

    phase_up    = macro_phase.upper()
    macro_watch = "LATE" in phase_up or "CONTRACT" in phase_up
    rate_status: MarketStatus = "WATCH" if macro_watch else "STABLE"

    sent_watch   = result["sentiment"]["sentiment_score"] < -0.1
    sent_status: MarketStatus = "WATCH" if sent_watch else "STABLE"

    return {
        "ticker":      DISPLAY_NAMES.get(ticker, ticker),
        "momentum":    momentum_status,
        "regime":      rate_status,
        "rates":       rate_status,
        "sentiment":   sent_status,
        "sig_score":   result["signal"],
        # Internal — used for portfolio_health computation, not exposed to UI
        "_confidence": result["confidence"],
    }
