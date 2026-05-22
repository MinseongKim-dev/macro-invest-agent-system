"""Aleph-One engine layer — polymorphic multi-engine architecture.

Hierarchy::

    BaseEngine (ABC)  ← analyze(ticker, market_data, context_data) → dict
    ├── QuantEngine          — 5/20 SMA golden/dead-cross + 20-day σ → momentum_score
    │                          + Ray Dalio Volatility Targeting (vol spike → WATCH + penalty)
    ├── SentimentEngine      — weighted financial lexicon → sentiment_score [-1, +1]
    │                          + James Simons Regime Switching (crisis keyword → regime_switch)
    └── PersonaAdapterEngine — persona weight-matrix blend → BUY/HOLD/SELL + confidence
                               + Warren Buffett Margin of Safety (RSI ≥ 70 → BUY Lock→HOLD)

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
    ticker:            str
    momentum_score:    float        # 0.0 – 1.0  (>0.5 = bullish bias from SMA spread)
    volatility:        float        # raw std-dev of 20-day close prices (price units)
    vol_ratio:         float        # volatility / mean_price  (dimensionless coefficient)
    status:            MarketStatus # WATCH if vol_ratio > 5% OR vol_spike, else STABLE
    sma5_last:         float        # latest 5-day Simple Moving Average
    sma20_last:        float        # latest 20-day Simple Moving Average
    crossover_bull:    bool         # SMA5 > SMA20 on the current bar
    golden_cross:      bool         # SMA5 just crossed above SMA20 (prev bar was below)
    dead_cross:        bool         # SMA5 just crossed below SMA20 (prev bar was above)
    # ── Ray Dalio: Volatility Targeting ──────────────────────────────────────
    vol_spike:         bool         # recent 5-day σ > 1.5 × 20-day baseline σ
    vol_spike_penalty: float        # deduction applied to momentum_score (0.0 if no spike)


@dataclass(frozen=True)
class SentimentResult:
    ticker:               str
    sentiment_score:      float  # -1.0 – +1.0
    positive_ratio:       float  # fraction of total tokens that matched positive-weight words
    negative_ratio:       float  # fraction of total tokens that matched negative-weight words
    sample_size:          int
    # ── James Simons: Regime Switching ───────────────────────────────────────
    regime_switch:        bool   # True when macro crisis keyword frequency exceeds threshold
    crisis_keyword_count: int    # raw count of crisis keywords across all texts


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

# Ray Dalio — Volatility Targeting parameters
# When recent_vol (5-day σ) > _VOL_SPIKE_RATIO × baseline_vol (20-day σ), the
# regime is classified as a volatility spike: status forced to WATCH and
# _VOL_SPIKE_PENALTY subtracted from momentum_score (bullish price action
# insufficient to offset elevated risk).
_VOL_SPIKE_RATIO:   float = 1.5
_VOL_SPIKE_PENALTY: float = 0.15
_RECENT_VOL_WINDOW: int   = 5   # short window for spike detection

_NORM_FACTOR:   float = 5.0    # SMA spread-ratio → score: ±20 % spread saturates [0, 1]


class QuantEngine(BaseEngine):
    """5/20 SMA golden-cross + 20-day std-dev volatility → momentum_score.

    Inputs
    ------
    market_data : pd.DataFrame with a ``close_price`` column and ≥20 rows.

    Ray Dalio — Volatility Targeting
    --------------------------------
    * Compare recent 5-day σ vs 20-day baseline σ.
    * recent_vol > 1.5 × baseline_vol → vol_spike = True.
    * On spike: status forced WATCH + momentum_score -= 0.15 (even if price is rising).
      This prevents entering a position during a volatility shock, consistent with
      Dalio's All Weather risk-parity principle.

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
                "vol_spike": result.vol_spike,
                "vol_spike_penalty": result.vol_spike_penalty,
            },
        )
        return {
            "ticker":            result.ticker,
            "momentum_score":    result.momentum_score,
            "volatility":        result.volatility,
            "vol_ratio":         result.vol_ratio,
            "status":            result.status,
            "sma5_last":         result.sma5_last,
            "sma20_last":        result.sma20_last,
            "crossover_bull":    result.crossover_bull,
            "golden_cross":      result.golden_cross,
            "dead_cross":        result.dead_cross,
            "vol_spike":         result.vol_spike,
            "vol_spike_penalty": result.vol_spike_penalty,
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
        raw_momentum   = float(np.clip(0.5 + spread_ratio * _NORM_FACTOR, 0.0, 1.0))

        # ── Volatility: std-dev of last 20 closes ─────────────────────────────
        tail_20      = close.tail(_SMA_SLOW)
        volatility   = float(tail_20.std())
        mean_price   = float(tail_20.mean())
        vol_ratio    = volatility / max(mean_price, 1e-8)

        # ── Ray Dalio — Volatility Targeting ─────────────────────────────────
        # recent_vol: 5-day std; baseline_vol: full 20-day std
        # Spike detected when recent activity is 1.5× more turbulent than baseline.
        baseline_vol  = volatility  # 20-day σ (already computed)
        recent_tail   = close.tail(_RECENT_VOL_WINDOW)
        recent_vol    = float(recent_tail.std()) if len(recent_tail) >= 2 else baseline_vol
        vol_spike     = recent_vol > _VOL_SPIKE_RATIO * max(baseline_vol, 1e-10)

        # Apply penalty: momentum_score discounted even on bullish bar
        vol_spike_penalty = _VOL_SPIKE_PENALTY if vol_spike else 0.0
        momentum_score    = float(np.clip(raw_momentum - vol_spike_penalty, 0.0, 1.0))

        # ── Status ───────────────────────────────────────────────────────────
        status: MarketStatus = "WATCH" if (vol_ratio > _VOL_THRESHOLD or vol_spike) else "STABLE"

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
            vol_spike=vol_spike,
            vol_spike_penalty=vol_spike_penalty,
        )

    @staticmethod
    def _neutral(ticker: str) -> QuantResult:
        return QuantResult(
            ticker=ticker, momentum_score=0.5, volatility=0.0, vol_ratio=0.0,
            status="STABLE", sma5_last=0.0, sma20_last=0.0,
            crossover_bull=False, golden_cross=False, dead_cross=False,
            vol_spike=False, vol_spike_penalty=0.0,
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

# James Simons — Regime Switching parameters
# Macro crisis keywords that, when frequent enough, signal a systemic regime shift
# rather than mere single-ticker bearishness.
_CRISIS_KEYWORDS: frozenset[str] = frozenset({
    "inflation", "hawkish", "tightening", "crisis",
})
# Trigger when: absolute count ≥ threshold OR crisis_ratio > 3% of all tokens
_CRISIS_SWITCH_COUNT_THRESHOLD: int   = 3
_CRISIS_SWITCH_RATIO_THRESHOLD: float = 0.03


class SentimentEngine(BaseEngine):
    """Weighted financial lexicon → precision sentiment_score (-1.0 to +1.0).

    Scanning method: token-level lookup against ``_WEIGHTED_LEXICON``.
    Scoring formula: weighted_sum / total_tokens × ``_SENT_SCALE``, clipped to [-1, +1].

    James Simons — Regime Switching
    --------------------------------
    Tracks the frequency of macro crisis keywords (inflation, hawkish, tightening, crisis)
    across all input texts. When cumulative count ≥ 3 OR ratio > 3% of total tokens,
    sets ``regime_switch = True`` — signalling that market context has shifted beyond
    individual ticker sentiment to a systemic macro crisis mode.

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
                regime_switch=False, crisis_keyword_count=0,
            )

        logger.debug(
            "sentiment_result",
            extra={
                "ticker": ticker, "score": result.sentiment_score, "n": result.sample_size,
                "regime_switch": result.regime_switch,
                "crisis_kw_count": result.crisis_keyword_count,
            },
        )
        return {
            "ticker":               result.ticker,
            "sentiment_score":      result.sentiment_score,
            "positive_ratio":       result.positive_ratio,
            "negative_ratio":       result.negative_ratio,
            "sample_size":          result.sample_size,
            "regime_switch":        result.regime_switch,
            "crisis_keyword_count": result.crisis_keyword_count,
        }

    def _score(self, ticker: str, texts: list[str]) -> SentimentResult:
        weighted_sum        = 0.0
        total_tokens        = 0
        positive_hits       = 0
        negative_hits       = 0
        crisis_keyword_count = 0

        for text in texts:
            tokens = [t.strip(_STRIP_CHARS) for t in text.lower().split()]
            total_tokens += len(tokens)
            for token in tokens:
                # Crisis keyword count (James Simons regime detection)
                if token in _CRISIS_KEYWORDS:
                    crisis_keyword_count += 1

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
                regime_switch=False, crisis_keyword_count=0,
            )

        raw   = weighted_sum / total_tokens * _SENT_SCALE
        score = float(np.clip(raw, -1.0, 1.0))

        crisis_ratio  = crisis_keyword_count / total_tokens
        regime_switch = (
            crisis_keyword_count >= _CRISIS_SWITCH_COUNT_THRESHOLD
            or crisis_ratio > _CRISIS_SWITCH_RATIO_THRESHOLD
        )

        return SentimentResult(
            ticker=ticker,
            sentiment_score=score,
            positive_ratio=positive_hits / total_tokens,
            negative_ratio=negative_hits / total_tokens,
            sample_size=len(texts),
            regime_switch=regime_switch,
            crisis_keyword_count=crisis_keyword_count,
        )


# ── RSI helper ────────────────────────────────────────────────────────────────

_RSI_PERIOD: int   = 14
_RSI_OVERBOUGHT: float = 70.0


def _compute_rsi(close: pd.Series, period: int = _RSI_PERIOD) -> float:
    """Compute RSI(period) using Wilder's smoothed average method.

    Returns a value in [0, 100].  Returns 50.0 if there is insufficient data.
    """
    if len(close) < period + 1:
        return 50.0

    delta  = close.diff().dropna()
    gains  = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    # Wilder's initial average (simple mean for first period)
    avg_gain = float(gains.iloc[:period].mean())
    avg_loss = float(losses.iloc[:period].mean())

    # Wilder's smoothing over remaining bars
    for g, loss in zip(gains.iloc[period:], losses.iloc[period:], strict=False):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss < 1e-10:
        return 100.0

    rs  = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


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

    Warren Buffett — Margin of Safety (CONSERVATIVE persona only)
    -------------------------------------------------------------
    Before finalising a BUY signal for CONSERVATIVE investors, RSI(14) is evaluated.
    If RSI ≥ 70 (overbought), there is no margin of safety — the asset is priced
    above intrinsic value. The BUY signal is locked down to HOLD regardless of the
    composite score. This prevents chasing momentum at peak valuations.
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

            # ── Warren Buffett — Margin of Safety ────────────────────────────
            # CONSERVATIVE persona: if signal is BUY but RSI ≥ 70, no safety margin
            # exists — asset is overbought and priced above intrinsic value.
            # Lock BUY → HOLD to protect capital.
            margin_of_safety_lock = False
            rsi_value             = 50.0
            if (self._persona == "CONSERVATIVE" and signal == "BUY"
                    and "close_price" in market_data.columns
                    and len(market_data) >= _RSI_PERIOD + 1):
                rsi_value = _compute_rsi(market_data["close_price"].astype(float))
                if rsi_value >= _RSI_OVERBOUGHT:
                    signal                = "HOLD"
                    margin_of_safety_lock = True
                    logger.info(
                        "margin_of_safety_lock",
                        extra={
                            "ticker": ticker, "rsi": round(rsi_value, 2),
                            "persona": self._persona,
                        },
                    )

            strategy = _strategy_text(ticker, signal, quant_d, sentiment_d)

            logger.info(
                "persona_result",
                extra={
                    "ticker": ticker, "signal": signal,
                    "confidence": round(confidence, 3), "persona": self._persona,
                    "composite": round(composite, 4),
                    "margin_of_safety_lock": margin_of_safety_lock,
                    "rsi": round(rsi_value, 2),
                },
            )
            return {
                "ticker":                ticker,
                "signal":                signal,
                "confidence":            confidence,
                "strategy":              strategy,
                "persona":               self._persona,
                "quant":                 quant_d,
                "sentiment":             sentiment_d,
                "rsi":                   round(rsi_value, 2),
                "margin_of_safety_lock": margin_of_safety_lock,
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
    name      = DISPLAY_NAMES.get(ticker, ticker)
    score     = sentiment_d.get("sentiment_score", 0.0)
    vol_r     = quant_d.get("vol_ratio", 0.0)
    golden    = quant_d.get("golden_cross", False)
    dead      = quant_d.get("dead_cross",   False)
    bull      = quant_d.get("crossover_bull", False)
    vol_spike = quant_d.get("vol_spike", False)
    reg_sw    = sentiment_d.get("regime_switch", False)

    spike_note  = " [VOL-SPIKE: Dalio-WATCH]"   if vol_spike else ""
    regime_note = " [REGIME-SWITCH: Simons-MODE]" if reg_sw   else ""

    if signal == "BUY":
        cross = "Golden Cross — " if golden else ("SMA5>SMA20 — " if bull else "")
        return f"{name}: {cross}momentum surge, sentiment {score:+.2f}{spike_note}{regime_note}"
    if signal == "SELL":
        cross = "Dead Cross — " if dead else ("SMA5<SMA20 — " if not bull else "")
        return f"{name}: {cross}momentum deteriorating, sentiment drag {score:+.2f}, vol={vol_r:.1%}{spike_note}{regime_note}"
    return f"{name}: Neutral posture — monitoring SMA convergence, vol={vol_r:.1%}{spike_note}{regime_note}"


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
        news:        News headline strings for SentimentEngine.
        macro_phase: Current macro phase string (e.g. ``"LATE_CYCLE"``).
        persona:     Investor persona profile.

    Returns:
        Dict matching the ``risk_matrix`` entry shape from the UI contract.
        Internal keys (prefixed ``_``) carry engine metadata consumed by main.py
        but stripped from the public SSE payload.

    Pipeline data flow to UI columns
    ---------------------------------
    ┌──────────────────┬──────────────────────────────────────────────────────┐
    │ UI Column        │ Engine source                                        │
    ├──────────────────┼──────────────────────────────────────────────────────┤
    │ momentum         │ QuantEngine: vol_ratio > 5% OR vol_spike OR cross     │
    │ regime           │ macro_phase + SentimentEngine.regime_switch           │
    │ rates            │ macro_phase (LATE/CONTRACT) + regime_switch           │
    │ sentiment        │ SentimentEngine.sentiment_score < −0.1 OR regime_sw   │
    │ sig_score        │ PersonaAdapterEngine signal (incl. MoS HOLD lock)     │
    └──────────────────┴──────────────────────────────────────────────────────┘
    """
    engine = PersonaAdapterEngine(persona)
    result = engine.analyze(ticker, price_df, news)

    quant_dict    = result["quant"]
    sent_dict     = result["sentiment"]
    regime_switch = sent_dict.get("regime_switch", False)

    # ── Momentum: WATCH on vol spike, vol ratio, or crossover event ──────────
    crossover_event   = quant_dict.get("golden_cross", False) or quant_dict.get("dead_cross", False)
    momentum_status: MarketStatus = (
        "WATCH" if (quant_dict["status"] == "WATCH" or crossover_event) else "STABLE"
    )

    # ── Regime + Rates: macro phase AND Simons regime_switch flag ─────────────
    phase_up    = macro_phase.upper()
    macro_watch = "LATE" in phase_up or "CONTRACT" in phase_up
    rate_status: MarketStatus = "WATCH" if (macro_watch or regime_switch) else "STABLE"

    # ── Sentiment: score threshold OR Simons regime_switch ───────────────────
    sent_watch   = sent_dict.get("sentiment_score", 0.0) < -0.1
    sent_status: MarketStatus = "WATCH" if (sent_watch or regime_switch) else "STABLE"

    return {
        "ticker":      DISPLAY_NAMES.get(ticker, ticker),
        "momentum":    momentum_status,
        "regime":      rate_status,
        "rates":       rate_status,
        "sentiment":   sent_status,
        "sig_score":   result["signal"],
        # ── Internal fields (stripped from public payload in main.py) ─────────
        "_confidence":            result["confidence"],
        "_regime_switch":         regime_switch,
        "_vol_spike":             quant_dict.get("vol_spike", False),
        "_margin_of_safety_lock": result.get("margin_of_safety_lock", False),
        "_rsi":                   result.get("rsi", 50.0),
    }
