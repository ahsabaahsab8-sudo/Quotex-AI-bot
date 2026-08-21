import os
import sys
import json
import asyncio
import time
import logging
import requests
import pandas as pd
import numpy as np
import ta
import re
from datetime import datetime, timezone, timedelta, time as dt_time
from dotenv import load_dotenv
from openai import OpenAI

from quotex_adapter import (
    get_quotex_connection as adapter_get_quotex_connection,
    close_quotex_connection,
    fetch_candles as adapter_fetch_candles,
    get_active_pairs as adapter_get_active_pairs,
    get_asset_payout as adapter_get_asset_payout,
)

from gmail_otp import fetch_latest_otp

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─── LATENCY / STALENESS KNOBS ─────────────────────────────────────────
# Fast-vote: stop waiting for all models as soon as 2 agree in the same
# direction (majority reached). Hard deadline: whatever votes we have by then
# are used. All 3 models are vision-capable now (Gemini Flash + Nemotron 3
# Nano Omni + Dots3-Note, both Kilo vision models), so the deadline is kept
# tight to keep the signal returning in seconds.
AI_VOTE_DEADLINE_SECONDS = float(os.getenv("AI_VOTE_DEADLINE_SECONDS", "30"))
AI_MODEL_TIMEOUT_SECONDS = float(os.getenv("AI_MODEL_TIMEOUT_SECONDS", "60"))
AI_OUTPUT_MAX_TOKENS = int(os.getenv("AI_OUTPUT_MAX_TOKENS", "2048"))
# LLM text models (Nemotron 3 Ultra, Llama 3.1 8B, Laguna-S 2.1) are slower than
# the vision models (they emit chain-of-thought before the JSON), so the LLM vote
# gets a longer fast-path deadline to let all 3 cast a vote.
LLM_VOTE_DEADLINE_SECONDS = float(os.getenv("LLM_VOTE_DEADLINE_SECONDS", "45"))
LLM_MODEL_TIMEOUT_SECONDS = float(os.getenv("LLM_MODEL_TIMEOUT_SECONDS", "75"))
# Data older than this many candle timeframes is considered stale before signaling.
DATA_AGE_MULTIPLIER = float(os.getenv("DATA_AGE_MULTIPLIER", "1.5"))
# Chart-capable model for the 3-model vote: "kilo" (Step 3.7 Flash) or "gemini" (Gemini Flash).
# All three voters get the same chart image + prompt. Gemini Flash is the fast
# default (~3s, chart filled); the other two are Nemotron 3 Nano Omni and
# Dots3-Note, both chart-capable on their Kilo gateways with reasoning disabled.
CHART_MODEL = os.getenv("CHART_MODEL", "gemini")


# ─── AUTO OTP READER FROM EMAIL ──────────────────────────────────────

async def auto_otp_callback(message):
    otp = await asyncio.to_thread(fetch_latest_otp, timeout=60)
    if otp:
        return otp
    logger.warning("Gmail API: no Quotex OTP found within 60s")
    return None


# ─── QUOTEX CONNECTION ───────────────────────────────────────────────

async def start_session_keeper():
    logger.info("Session keeper: A11ksa adapter handles auto-refresh natively")
    pass

async def stop_session_keeper():
    pass

async def get_quotex_connection():
    """Get connected pyquotex client via proxy — handles auto-reconnect."""
    return await adapter_get_quotex_connection()


# ─── INDICATOR CALCULATION ───────────────────────────────────────────

def resample_to_tf(df: pd.DataFrame, minutes: int) -> pd.DataFrame | None:
    if df.empty or 'time' not in df.columns:
        return None
    d = df.copy()
    d['time'] = pd.to_datetime(d['time'], unit='s')
    d = d.set_index('time')
    rule = f'{minutes}min'
    if len(d) < 2:
        return None
    resampled = d.resample(rule).agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    resampled['time'] = resampled['time'].astype('int64') // 10**9
    return resampled


def compute_ema_alignment(price: float, ema9: float, ema20: float, ema50: float) -> str:
    if price > ema9 > ema20 > ema50:
        return "BULLISH_ALIGNED"
    if price < ema9 < ema20 < ema50:
        return "BEARISH_ALIGNED"
    return "MIXED"


def compute_three_candle_rule(df: pd.DataFrame) -> str:
    if len(df) < 4:
        return "NONE"
    closes = df['close'].values
    colors = ["G" if closes[i] >= closes[i-1] else "R" for i in range(1, len(closes))]
    last_3 = colors[-3:] if len(colors) >= 3 else colors
    if all(c == "G" for c in last_3):
        return "3_GREEN"
    if all(c == "R" for c in last_3):
        return "3_RED"
    return "NONE"


def detect_fvg(df: pd.DataFrame) -> list:
    fvg_list = []
    if len(df) < 4:
        return fvg_list
    for i in range(len(df) - 3):
        c1, c2, c3 = df.iloc[i], df.iloc[i+1], df.iloc[i+2]
        bullish_gap = c1['high'] < c3['low']
        if bullish_gap and c2['close'] < c2['open']:
            fvg_list.append({
                "index": i, "type": "BULLISH_FVG",
                "gap_high": float(c1['high']), "gap_low": float(c3['low']),
            })
        bearish_gap = c1['low'] > c3['high']
        if bearish_gap and c2['close'] > c2['open']:
            fvg_list.append({
                "index": i, "type": "BEARISH_FVG",
                "gap_low": float(c1['low']), "gap_high": float(c3['high']),
            })
    return fvg_list[-3:] if fvg_list else []


def detect_liquidity_sweep(df: pd.DataFrame) -> dict:
    if len(df) < 10:
        return {"detected": False, "type": None, "description": "Insufficient data"}
    lookback = min(10, len(df) - 1)
    recent = df.tail(lookback)
    recent_low = float(recent['low'].min())
    recent_high = float(recent['high'].max())
    last = df.iloc[-1]
    last2 = df.iloc[-2]
    close = float(last['close'])
    low = float(last['low'])
    high = float(last['high'])
    prev_close = float(last2['close'])

    support_sweep = low < recent_low * 0.999 and close > recent_low
    resistance_sweep = high > recent_high * 1.001 and close < recent_high

    if support_sweep:
        return {"detected": True, "type": "BULLISH_TRAP", "description": f"Price swept below recent support ({recent_low:.5f}) and closed back above. Bullish liquidity grab."}
    if resistance_sweep:
        return {"detected": True, "type": "BEARISH_TRAP", "description": f"Price swept above recent resistance ({recent_high:.5f}) and closed back below. Bearish liquidity grab."}
    return {"detected": False, "type": None, "description": "No sweep detected"}


def detect_smt_divergence(df: pd.DataFrame, rsi_col: str = 'rsi') -> dict:
    if len(df) < 20:
        return {"type": "NONE", "description": "Insufficient data"}
    window = min(14, len(df) // 2)
    recent = df.tail(window)
    low_idx = recent['low'].idxmin()
    high_idx = recent['high'].idxmax()
    price_low = float(recent.loc[low_idx, 'low'])
    price_high = float(recent.loc[high_idx, 'high'])
    rsi_low = float(recent.loc[low_idx, rsi_col])
    rsi_high = float(recent.loc[high_idx, rsi_col])

    mid = len(df) // 2
    first_half = df.iloc[mid-window:mid]
    if len(first_half) < 5:
        return {"type": "NONE", "description": "Insufficient data for divergence comparison"}
    prev_low_idx = first_half['low'].idxmin()
    prev_high_idx = first_half['high'].idxmax()
    prev_price_low = float(first_half.loc[prev_low_idx, 'low'])
    prev_price_high = float(first_half.loc[prev_high_idx, 'high'])
    prev_rsi_low = float(first_half.loc[prev_low_idx, rsi_col])
    prev_rsi_high = float(first_half.loc[prev_high_idx, rsi_col])

    if price_low < prev_price_low and rsi_low > prev_rsi_low:
        return {"type": "BULLISH", "description": f"Price made lower low ({price_low:.5f} < {prev_price_low:.5f}) but RSI made higher low ({rsi_low:.2f} > {prev_rsi_low:.2f}). Bullish divergence."}
    if price_high > prev_price_high and rsi_high < prev_rsi_high:
        return {"type": "BEARISH", "description": f"Price made higher high ({price_high:.5f} > {prev_price_high:.5f}) but RSI made lower high ({rsi_high:.2f} < {prev_rsi_high:.2f}). Bearish divergence."}
    return {"type": "NONE", "description": "No divergence detected"}


def analyze_wicks(df: pd.DataFrame) -> dict:
    if len(df) < 5:
        return {"avg_upper_wick_ratio": 0, "avg_lower_wick_ratio": 0, "last_candle_wick_direction": "NONE", "long_upper_wick_pct": 0, "long_lower_wick_pct": 0}
    last_10 = df.tail(10)
    ratios = []
    long_upper_count = 0
    long_lower_count = 0
    for _, r in last_10.iterrows():
        body = abs(r['close'] - r['open'])
        rng = r['high'] - r['low']
        if rng == 0:
            continue
        upper = (r['high'] - max(r['close'], r['open'])) / rng
        lower = (min(r['close'], r['open']) - r['low']) / rng
        ratios.append((upper, lower))
        if upper > 0.6:
            long_upper_count += 1
        if lower > 0.6:
            long_lower_count += 1
    if not ratios:
        return {"avg_upper_wick_ratio": 0, "avg_lower_wick_ratio": 0, "last_candle_wick_direction": "NONE", "long_upper_wick_pct": 0, "long_lower_wick_pct": 0}
    avg_upper = float(np.mean([r[0] for r in ratios]))
    avg_lower = float(np.mean([r[1] for r in ratios]))
    total = len(ratios)
    last_r = df.iloc[-1]
    last_body = abs(last_r['close'] - last_r['open'])
    last_upper = (last_r['high'] - max(last_r['close'], last_r['open'])) / (last_r['high'] - last_r['low']) if (last_r['high'] - last_r['low']) > 0 else 0
    last_lower = (min(last_r['close'], last_r['open']) - last_r['low']) / (last_r['high'] - last_r['low']) if (last_r['high'] - last_r['low']) > 0 else 0
    if last_upper > 0.6 and last_upper > last_lower * 2:
        direction = "TOP_SELL"
    elif last_lower > 0.6 and last_lower > last_upper * 2:
        direction = "BOTTOM_BUY"
    else:
        direction = "NEUTRAL"
    return {
        "avg_upper_wick_ratio": round(avg_upper, 3),
        "avg_lower_wick_ratio": round(avg_lower, 3),
        "last_candle_wick_direction": direction,
        "long_upper_wick_pct": round(long_upper_count / total * 100, 1),
        "long_lower_wick_pct": round(long_lower_count / total * 100, 1),
    }


def detect_volatility_expansion(df: pd.DataFrame) -> dict:
    if len(df) < 8:
        return {"detected": False, "description": "Insufficient data"}
    ranges = (df['high'] - df['low']).values
    bodies = abs(df['close'] - df['open']).values
    last_range = float(ranges[-1])
    last_body = float(bodies[-1])
    avg_range_5 = float(np.mean(ranges[-6:-1])) if len(ranges) >= 6 else float(np.mean(ranges[:-1]))
    avg_body_5 = float(np.mean(bodies[-6:-1])) if len(bodies) >= 6 else float(np.mean(bodies[:-1]))
    if avg_range_5 == 0:
        return {"detected": False, "description": "No volatility data"}
    range_ratio = last_range / avg_range_5
    body_ratio = last_body / avg_body_5 if avg_body_5 > 0 else 0
    if range_ratio > 2.0 or body_ratio > 2.5:
        return {"detected": True, "description": f"Volatility expansion detected. Current candle range {range_ratio:.1f}x average, body {body_ratio:.1f}x average. Breakout likely.", "range_ratio": round(range_ratio, 2), "body_ratio": round(body_ratio, 2)}
    if range_ratio < 0.5:
        return {"detected": False, "description": f"Volatility contraction. Range is only {range_ratio:.1f}x average. Market compressing.", "range_ratio": round(range_ratio, 2), "body_ratio": round(body_ratio, 2)}
    return {"detected": False, "description": f"Normal volatility. Range {range_ratio:.1f}x average.", "range_ratio": round(range_ratio, 2), "body_ratio": round(body_ratio, 2)}


def compute_higher_tf_metrics(df: pd.DataFrame, minutes: int, token: str, payout: int) -> dict | None:
    resampled = resample_to_tf(df, minutes)
    if resampled is None or len(resampled) < 10:
        return None
    candles = resampled.to_dict('records')
    return compute_indicators(candles, token=token, payout=payout, compute_htf=False, timeframe=minutes * 60)


def format_timeframe_label(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds / 60
    if mins.is_integer():
        m = int(mins)
        if m < 60:
            return f"{m}m"
        h = m / 60
        if h.is_integer() and m % 60 == 0:
            hr = int(h)
            if hr < 24:
                return f"{hr}h"
            d = hr / 24
            if hr % 24 == 0:
                return f"{int(d)}d"
        return f"{m}m"
    hours = mins / 60
    return f"{hours:g}h"


def compute_indicators(candles: list[dict], token: str = "EURUSD_otc", payout: int = 80, compute_htf: bool = True, timeframe: int = 60) -> dict:
    df = pd.DataFrame(candles)
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['open'] = df['open'].astype(float)
    if 'time' in df.columns:
        df['time'] = df['time'].astype(int)

    n = len(df)
    if n < 30:
        logger.warning(f"Too few candles ({n}) for {token}, returning low volatility fallback")
        return {
            "current_price": float(df['close'].iloc[-1]) if not df.empty else 0,
            "latest_atr": 0.0005, "average_atr_20": 0.0005,
            "payout_percentage": payout, "low_volatility": True,
            "analysis_timeframe_seconds": timeframe,
            "analysis_timeframe_label": format_timeframe_label(timeframe),
            "nearest_round_numbers": get_nearest_round_numbers(float(df['close'].iloc[-1])) if not df.empty else {},
            "color_probabilities": {"color_sequence_last_10": [], "last_3_sequence": "", "historical_probability": {"next_green_percentage": 50, "next_red_percentage": 50, "occurrences_found": 0}},
            "detected_candlestick_patterns": [], "ema_alignment": "MIXED",
            "adx": 0, "adx_strength": "WEAK", "three_candle_rule": "NONE",
            "stochastic": {"k": 50, "d": 50, "cross": "NONE", "overbought": False, "oversold": False},
            "fvg": [], "liquidity_sweep": {"detected": False, "type": None, "description": "Insufficient data"},
            "smt_divergence": {"type": "NONE", "description": "Insufficient data"},
            "fifty_percent_level": 0, "wick_analysis": {}, "volatility_expansion": {"detected": False, "description": "Insufficient data"},
            "metrics_1m": {"rsi": 50, "trend": "SIDEWAYS / NEUTRAL", "ema_9": 0, "ema_20": 0, "ema_50": 0, "macd": 0, "macd_signal": 0, "macd_diff": 0, "bollinger_upper": 0, "bollinger_middle": 0, "bollinger_lower": 0, "support_50": 0, "resistance_50": 0, "adx": 0, "stoch_k": 50, "stoch_d": 50},
            "metrics_5m": None, "metrics_15m": None,
            "ema_alignment_lti": "MIXED",
            "support_resistance_break": {
                "prev_resistance": 0.0, "prev_support": 0.0,
                "resistance_break": False, "retest_resistance": False,
                "support_break": False, "retest_support": False,
                "description": "Insufficient data"
            },
            "rsi_directional": {
                "rsi_value": 50.0, "rsi_rising": False, "rsi_falling": False,
                "rsi_bullish_confluence": False, "rsi_bearish_confluence": False
            },
            "stochastic_strict": {
                "k": 50.0, "d": 50.0, "bullish_cross_strict": False, "bearish_cross_strict": False
            },
            "bollinger_squeeze": {
                "bb_width": 0.0, "bb_squeeze": False, "bb_rsi_buy_confluence": False, "bb_rsi_sell_confluence": False
            },
            "volume_trend": {
                "volume_ma_20": 0.0, "volume_increasing": False,
                "volume_trend_bullish": False, "volume_trend_bearish": False
            },
            "candlestick_at_level": {
                "at_support": False, "at_resistance": False,
                "bullish_pinbar_at_support": False, "bearish_pinbar_at_resistance": False
            },
            "cci": 0.0,
            "mfi": {
                "mfi_value": 50.0, "mfi_bullish_divergence": False
            },
            "williams_r": -50.0,
            "awesome_oscillator": {
                "ao_value": 0.0, "ao_cross_up": False, "ao_cross_down": False
            },
            "pivot_points": {
                "pivot": 0.0, "r1": 0.0, "s1": 0.0, "pivot_break_up": False, "r1_break_up": False
            },
            "ichimoku": {
                "tenkan": 0.0, "kijun": 0.0, "ichimoku_bullish": False
            },
            "session_filter": {
                "is_london_ny_overlap": False, "current_hour_utc": 0
            },
        }
    df['ema_9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
    ema50_window = min(50, n)
    df['ema_50'] = ta.trend.ema_indicator(df['close'], window=ema50_window)
    ema200_window = min(200, n)
    df['ema_200'] = ta.trend.ema_indicator(df['close'], window=ema200_window)
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    macd_obj = ta.trend.MACD(df['close'])
    df['macd'] = macd_obj.macd()
    df['macd_signal'] = macd_obj.macd_signal()
    df['macd_diff'] = macd_obj.macd_diff()
    adx_obj = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx_obj.adx()
    stoch_obj = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch_obj.stoch()
    df['stoch_d'] = stoch_obj.stoch_signal()
    bb_obj = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_hband'] = bb_obj.bollinger_hband()
    df['bb_lband'] = bb_obj.bollinger_lband()
    df['bb_mavg'] = bb_obj.bollinger_mavg()
    df['support_50'] = df['low'].rolling(window=min(50, n), min_periods=1).min()
    df['resistance_50'] = df['high'].rolling(window=min(50, n), min_periods=1).max()
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # New indicators
    df['cci'] = ta.trend.cci(df['high'], df['low'], df['close'], window=20)
    df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
    df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
    df['ao'] = ta.momentum.awesome_oscillator(df['high'], df['low'], window1=5, window2=34)
    
    ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'])
    df['tenkan'] = ichimoku.ichimoku_conversion_line()
    df['kijun'] = ichimoku.ichimoku_base_line()
    
    df['volume_ma_20'] = df['volume'].rolling(window=min(20, n), min_periods=1).mean()
    df['bb_width'] = (df['bb_hband'] - df['bb_lband']) / df['bb_mavg']
    
    df = df.ffill().bfill().copy()

    latest_atr = float(df['atr'].iloc[-1])
    avg_atr_20 = float(df['atr'].tail(20).mean())
    latest_row = df.iloc[-1]
    close_1m = float(latest_row['close'])
    ema9_1m = float(latest_row['ema_9']) if not pd.isna(latest_row['ema_9']) else close_1m
    ema20_1m = float(latest_row['ema_20']) if not pd.isna(latest_row['ema_20']) else close_1m
    ema50_1m = float(latest_row['ema_50']) if not pd.isna(latest_row['ema_50']) else close_1m
    ema200_1m = float(latest_row['ema_200']) if not pd.isna(latest_row['ema_200']) else close_1m

    rsi_val = float(latest_row['rsi']) if not pd.isna(latest_row['rsi']) else 50.0
    if rsi_val > 70:
        trend = "STRONG_UPTREND"
    elif rsi_val > 55:
        trend = "UPTREND"
    elif rsi_val > 45:
        trend = "SIDEWAYS / NEUTRAL"
    elif rsi_val > 30:
        trend = "DOWNTREND"
    else:
        trend = "STRONG_DOWNTREND"

    macd_v = float(latest_row['macd']) if not pd.isna(latest_row['macd']) else 0
    macd_s = float(latest_row['macd_signal']) if not pd.isna(latest_row['macd_signal']) else 0
    bb_u = float(latest_row['bb_hband']) if not pd.isna(latest_row['bb_hband']) else close_1m
    bb_l = float(latest_row['bb_lband']) if not pd.isna(latest_row['bb_lband']) else close_1m
    bb_m = float(latest_row['bb_mavg']) if not pd.isna(latest_row['bb_mavg']) else close_1m
    sup = float(latest_row['support_50']) if not pd.isna(latest_row['support_50']) else close_1m
    res = float(latest_row['resistance_50']) if not pd.isna(latest_row['resistance_50']) else close_1m
    adx_v = float(latest_row['adx']) if not pd.isna(latest_row['adx']) else 0
    stoch_k = float(latest_row['stoch_k']) if not pd.isna(latest_row['stoch_k']) else 50
    stoch_d = float(latest_row['stoch_d']) if not pd.isna(latest_row['stoch_d']) else 50
    prev_row = df.iloc[-2] if len(df) >= 2 else latest_row
    fifty_pct_level = round((float(prev_row['high']) + float(prev_row['low'])) / 2, 5) if len(df) >= 2 else close_1m

    ema_alignment = compute_ema_alignment(close_1m, ema9_1m, ema20_1m, ema50_1m)
    three_candle = compute_three_candle_rule(df)
    fvg_list = detect_fvg(df)
    sweep = detect_liquidity_sweep(df)
    smt_div = detect_smt_divergence(df)
    wick_analysis = analyze_wicks(df)
    vol_expansion = detect_volatility_expansion(df)

    if adx_v > 25:
        adx_strength = "STRONG"
    elif adx_v > 20:
        adx_strength = "MODERATE"
    else:
        adx_strength = "WEAK"

    stoch_overbought = stoch_k > 80 and stoch_d > 80
    stoch_oversold = stoch_k < 20 and stoch_d < 20
    if stoch_k > stoch_d and stoch_k < 30:
        stoch_cross = "BULLISH_CROSS"
    elif stoch_k < stoch_d and stoch_k > 70:
        stoch_cross = "BEARISH_CROSS"
    else:
        stoch_cross = "NONE"

    # 1. EMA 50 / EMA 200 alignment
    if close_1m > ema50_1m > ema200_1m:
        ema_alignment_lti = "BULLISH_ALIGNED_LTI"
    elif close_1m < ema50_1m < ema200_1m:
        ema_alignment_lti = "BEARISH_ALIGNED_LTI"
    else:
        ema_alignment_lti = "MIXED"

    # 2. Support / Resistance Breakout & Retest logic
    prev_close_val = float(prev_row['close'])
    prev_high_val = float(prev_row['high'])
    prev_low_val = float(prev_row['low'])
    current_high_val = float(latest_row['high'])
    current_low_val = float(latest_row['low'])

    if len(df) >= 3:
        prev3_row = df.iloc[-3]
        prev_sup_level = float(prev3_row['support_50'])
        prev_res_level = float(prev3_row['resistance_50'])
    else:
        prev_sup_level = sup
        prev_res_level = res

    resistance_break_val = prev_close_val > prev_res_level
    retest_resistance_val = (current_low_val <= prev_res_level) and (close_1m > prev_res_level)
    support_break_val = prev_close_val < prev_sup_level
    retest_support_val = (current_high_val >= prev_sup_level) and (close_1m < prev_sup_level)

    if resistance_break_val and retest_resistance_val:
        sr_break_desc = f"Resistance breakout and retest detected at level {prev_res_level:.5f}."
    elif support_break_val and retest_support_val:
        sr_break_desc = f"Support breakout and retest detected at level {prev_sup_level:.5f}."
    else:
        sr_break_desc = "No breakout and retest detected."

    support_resistance_break_data = {
        "prev_resistance": prev_res_level,
        "prev_support": prev_sup_level,
        "resistance_break": resistance_break_val,
        "retest_resistance": retest_resistance_val,
        "support_break": support_break_val,
        "retest_support": retest_support_val,
        "description": sr_break_desc
    }

    # 3. RSI Directional Change
    prev_rsi = float(prev_row['rsi']) if not pd.isna(prev_row['rsi']) else 50.0
    rsi_rising_val = rsi_val > prev_rsi
    rsi_falling_val = rsi_val < prev_rsi
    rsi_directional_data = {
        "rsi_value": round(rsi_val, 2),
        "rsi_rising": rsi_rising_val,
        "rsi_falling": rsi_falling_val,
        "rsi_bullish_confluence": (rsi_val < 30) and rsi_rising_val,
        "rsi_bearish_confluence": (rsi_val > 70) and rsi_falling_val
    }

    # 4. Stochastic Crossover Strict Rules
    prev_stoch_k = float(prev_row['stoch_k']) if not pd.isna(prev_row['stoch_k']) else 50.0
    prev_stoch_d = float(prev_row['stoch_d']) if not pd.isna(prev_row['stoch_d']) else 50.0
    stoch_bullish_cross_strict = (prev_stoch_k <= prev_stoch_d) and (stoch_k > stoch_d) and (stoch_k < 20)
    stoch_bearish_cross_strict = (prev_stoch_k >= prev_stoch_d) and (stoch_k < stoch_d) and (stoch_k > 80)
    stochastic_strict_data = {
        "k": round(stoch_k, 2),
        "d": round(stoch_d, 2),
        "bullish_cross_strict": stoch_bullish_cross_strict,
        "bearish_cross_strict": stoch_bearish_cross_strict
    }

    # 5. Bollinger Bands Squeeze
    bb_width_val = float(latest_row['bb_width']) if not pd.isna(latest_row['bb_width']) else 0.0
    is_squeeze = float(df['bb_width'].tail(20).min()) == bb_width_val if len(df) >= 20 else False
    bollinger_squeeze_data = {
        "bb_width": round(bb_width_val, 4),
        "bb_squeeze": is_squeeze,
        "bb_rsi_buy_confluence": (close_1m <= bb_l) and (rsi_val < 30),
        "bb_rsi_sell_confluence": (close_1m >= bb_u) and (rsi_val > 70)
    }

    # 6. Volume Trend Analysis
    vol_ma = float(latest_row['volume_ma_20']) if not pd.isna(latest_row['volume_ma_20']) else 0.0
    curr_vol = float(latest_row['volume']) if 'volume' in latest_row else 0.0
    vol_inc = curr_vol > vol_ma
    volume_trend_data = {
        "volume_ma_20": round(vol_ma, 1),
        "volume_increasing": vol_inc,
        "volume_trend_bullish": vol_inc and (close_1m > float(latest_row['open'])),
        "volume_trend_bearish": vol_inc and (close_1m < float(latest_row['open']))
    }

    # 7. Candlestick Pattern at Level Context
    detected_patterns = detect_candlestick_patterns(df)
    at_support_val = abs(close_1m - sup) / close_1m < 0.0005
    at_resistance_val = abs(close_1m - res) / close_1m < 0.0005
    candlestick_at_level_data = {
        "at_support": at_support_val,
        "at_resistance": at_resistance_val,
        "bullish_pinbar_at_support": ("Hammer (Bullish Reversal)" in detected_patterns) and at_support_val,
        "bearish_pinbar_at_resistance": ("Shooting Star (Bearish Reversal)" in detected_patterns) and at_resistance_val
    }

    # 8. CCI
    cci_val = round(float(latest_row['cci']), 2) if not pd.isna(latest_row['cci']) else 0.0

    # 9. MFI
    mfi_val = round(float(latest_row['mfi']), 2) if not pd.isna(latest_row['mfi']) else 50.0
    mfi_prev = round(float(df['mfi'].iloc[-5]), 2) if (len(df) >= 5 and not pd.isna(df['mfi'].iloc[-5])) else 50.0
    mfi_data = {
        "mfi_value": mfi_val,
        "mfi_bullish_divergence": (close_1m < float(df['close'].iloc[-5]) if len(df) >= 5 else False) and (mfi_val > mfi_prev)
    }

    # 10. Williams %R
    williams_r_val = round(float(latest_row['williams_r']), 2) if not pd.isna(latest_row['williams_r']) else -50.0

    # 11. Awesome Oscillator
    ao_curr_val = float(latest_row['ao']) if not pd.isna(latest_row['ao']) else 0.0
    ao_prev_val = float(prev_row['ao']) if not pd.isna(prev_row['ao']) else 0.0
    ao_data = {
        "ao_value": round(ao_curr_val, 6),
        "ao_cross_up": (ao_prev_val < 0) and (ao_curr_val > 0),
        "ao_cross_down": (ao_prev_val > 0) and (ao_curr_val < 0)
    }

    # 12. Pivot Points
    pivot_val = round((prev_high_val + prev_low_val + prev_close_val) / 3, 5)
    r1_val = round((2 * pivot_val) - prev_low_val, 5)
    s1_val = round((2 * pivot_val) - prev_high_val, 5)
    pivot_points_data = {
        "pivot": pivot_val,
        "r1": r1_val,
        "s1": s1_val,
        "pivot_break_up": (close_1m > pivot_val) and (prev_close_val <= pivot_val),
        "r1_break_up": (close_1m > r1_val) and (prev_close_val <= r1_val)
    }

    # 13. Ichimoku
    tenkan_val = float(latest_row['tenkan']) if not pd.isna(latest_row['tenkan']) else close_1m
    kijun_val = float(latest_row['kijun']) if not pd.isna(latest_row['kijun']) else close_1m
    ichimoku_data = {
        "tenkan": round(tenkan_val, 5),
        "kijun": round(kijun_val, 5),
        "ichimoku_bullish": (close_1m > tenkan_val) and (tenkan_val > kijun_val)
    }

    # 14. Session Filter
    current_hour_utc = datetime.now(timezone.utc).hour
    session_filter_data = {
        "is_london_ny_overlap": 13 <= current_hour_utc < 16,
        "current_hour_utc": current_hour_utc
    }

    return {
        "current_price": close_1m,
        "latest_atr": latest_atr,
        "average_atr_20": avg_atr_20,
        "payout_percentage": payout,
        "low_volatility": latest_atr < 0.0001,
        "analysis_timeframe_seconds": timeframe,
        "analysis_timeframe_label": format_timeframe_label(timeframe),
        "nearest_round_numbers": get_nearest_round_numbers(close_1m),
        "color_probabilities": calculate_color_probabilities(df),
        "detected_candlestick_patterns": detected_patterns,
        "ema_alignment": ema_alignment,
        "adx": round(adx_v, 2),
        "adx_strength": adx_strength,
        "three_candle_rule": three_candle,
        "stochastic": {
            "k": round(stoch_k, 2), "d": round(stoch_d, 2),
            "cross": stoch_cross, "overbought": stoch_overbought, "oversold": stoch_oversold,
        },
        "fvg": fvg_list,
        "liquidity_sweep": sweep,
        "smt_divergence": smt_div,
        "fifty_percent_level": fifty_pct_level,
        "wick_analysis": wick_analysis,
        "volatility_expansion": vol_expansion,
        "metrics_1m": {
            "rsi": round(rsi_val, 2), "trend": trend,
            "ema_9": round(ema9_1m, 5), "ema_20": round(ema20_1m, 5), "ema_50": round(ema50_1m, 5),
            "macd": round(macd_v, 6), "macd_signal": round(macd_s, 6), "macd_diff": round(macd_v - macd_s, 6),
            "bollinger_upper": round(bb_u, 5), "bollinger_middle": round(bb_m, 5), "bollinger_lower": round(bb_l, 5),
            "support_50": round(sup, 5), "resistance_50": round(res, 5),
            "adx": round(adx_v, 2), "stoch_k": round(stoch_k, 2), "stoch_d": round(stoch_d, 2),
        },
        "metrics_5m": compute_higher_tf_metrics(df, 5, token=token, payout=payout) if compute_htf else None,
        "metrics_15m": compute_higher_tf_metrics(df, 15, token=token, payout=payout) if compute_htf else None,
        "ema_alignment_lti": ema_alignment_lti,
        "support_resistance_break": support_resistance_break_data,
        "rsi_directional": rsi_directional_data,
        "stochastic_strict": stochastic_strict_data,
        "bollinger_squeeze": bollinger_squeeze_data,
        "volume_trend": volume_trend_data,
        "candlestick_at_level": candlestick_at_level_data,
        "cci": cci_val,
        "mfi": mfi_data,
        "williams_r": williams_r_val,
        "awesome_oscillator": ao_data,
        "pivot_points": pivot_points_data,
        "ichimoku": ichimoku_data,
        "session_filter": session_filter_data,
    }


def get_nearest_round_numbers(price: float) -> dict:
    step = 0.001 if price < 10 else (1.0 if price < 1000 else 10.0)
    above = round(np.ceil(price / step) * step, 5)
    below = round(np.floor(price / step) * step, 5)
    pip_mult = 10000 if price < 10 else (100 if price < 1000 else 10)
    return {
        "price": price,
        "nearest_round_above": above,
        "distance_above_pips": round((above - price) * pip_mult, 1),
        "nearest_round_below": below,
        "distance_below_pips": round((price - below) * pip_mult, 1),
    }


def calculate_color_probabilities(df: pd.DataFrame) -> dict:
    closes = df['close'].values
    colors = ["G" if closes[i] >= closes[i - 1] else "R" for i in range(1, len(closes))]
    last_10 = colors[-10:] if len(colors) >= 10 else colors
    last_3 = colors[-3:] if len(colors) >= 3 else colors
    occurrences = 0
    green_after = 0
    red_after = 0
    for i in range(len(colors) - 3):
        if colors[i:i + 3] == last_3:
            occurrences += 1
            if i + 3 < len(colors):
                if colors[i + 3] == "G":
                    green_after += 1
                else:
                    red_after += 1
    next_green_pct = (green_after / occurrences * 100) if occurrences > 0 else 50
    next_red_pct = (red_after / occurrences * 100) if occurrences > 0 else 50
    return {
        "color_sequence_last_10": last_10,
        "last_3_sequence": "-".join(last_3),
        "historical_probability": {
            "next_green_percentage": round(next_green_pct, 1),
            "next_red_percentage": round(next_red_pct, 1),
            "occurrences_found": occurrences,
        },
    }


def detect_candlestick_patterns(df: pd.DataFrame) -> list:
    patterns = []
    if len(df) < 3:
        return patterns
    r = df.iloc[-1]
    r1 = df.iloc[-2]
    body = abs(r['close'] - r['open'])
    upper_wick = r['high'] - max(r['close'], r['open'])
    lower_wick = min(r['close'], r['open']) - r['low']
    total_range = r['high'] - r['low']
    if total_range > 0:
        is_bearish = r['close'] < r['open']
        if body < total_range * 0.15 and upper_wick > body * 2 and lower_wick > body * 2:
            patterns.append("Doji (Indecision)")
        elif lower_wick > total_range * 0.6 and body < total_range * 0.3 and is_bearish:
            patterns.append("Hammer (Bullish Reversal)")
        elif upper_wick > total_range * 0.6 and body < total_range * 0.3 and not is_bearish:
            patterns.append("Shooting Star (Bearish Reversal)")
        elif len(df) >= 2:
            if is_bearish and r1['close'] > r1['open'] and r['open'] > r1['close'] and r['close'] < r1['open']:
                patterns.append("Bearish Engulfing (Strong Reversal)")
            elif not is_bearish and r1['close'] < r1['open'] and r['open'] < r1['close'] and r['close'] > r1['open']:
                patterns.append("Bullish Engulfing (Strong Reversal)")
    return patterns


async def fetch_and_process_indicators(client, token: str, payout: int = 80, timeframe: int = 60):
    # Scale the historical window so every timeframe yields ~600 candles
    # (Bollinger/SMA200 need 200+; 5m at 18000s would only give 60).
    amount_of_seconds = max(timeframe * 600, 3600)
    candles_data = await adapter_fetch_candles(client, token, count=amount_of_seconds, timeframe=timeframe)
    if candles_data is None:
        logger.error(f"Failed to fetch candles for {token}")
        return None

    if len(candles_data) < 30:
        logger.warning(f"Insufficient candles for {token}: {len(candles_data)}")
        return None

    candles = candles_data

    summary = compute_indicators(candles, token=token, payout=payout, timeframe=timeframe)
    if summary.get("low_volatility", False):
        logger.info(f"{token} has LOW VOLATILITY, marking as skip.")
        return "LOW_VOLATILITY"

    return {"summary": summary, "candles": candles}


def calculate_setup_readiness(tech: dict) -> float:
    summary = tech.get("summary", {})
    m1 = summary.get("metrics_1m", {})
    rsi = m1.get("rsi", 50)
    atr = summary.get("latest_atr", 0.0005)
    avg_atr = summary.get("average_atr_20", 0.0005)
    score = 50.0
    if rsi > 70 or rsi < 30:
        score += 10
    if atr > avg_atr:
        score += 10
    if m1.get("trend") in ("STRONG_UPTREND", "STRONG_DOWNTREND"):
        score += 15
    elif m1.get("trend") in ("UPTREND", "DOWNTREND"):
        score += 5
    cp = summary.get("color_probabilities", {}).get("historical_probability", {})
    if max(cp.get("next_green_percentage", 50), cp.get("next_red_percentage", 50)) > 60:
        score += 10
    return score


# ─── MATH SCORER + AUTO SCAN ─────────────────────────────────────────

def score_pair_math(summary: dict) -> float:
    s = summary or {}
    m1 = s.get("metrics_1m", {})
    score = 5.0

    adx = m1.get("adx", 0)
    if adx > 30:
        score += 2.0
    elif adx > 25:
        score += 1.5
    elif adx > 20:
        score += 0.5

    ema_alignment = s.get("ema_alignment", "MIXED")
    if ema_alignment in ("BULLISH_ALIGNED", "BEARISH_ALIGNED"):
        score += 1.5
    elif s.get("ema_alignment_lti", "MIXED") in ("BULLISH_ALIGNED_LTI", "BEARISH_ALIGNED_LTI"):
        score += 0.5

    macd_diff = m1.get("macd_diff", 0)
    if abs(macd_diff) > 0.0001:
        score += 1.0

    rsi = m1.get("rsi", 50)
    if rsi < 35 or rsi > 65:
        score += 1.0
    elif rsi < 45 or rsi > 55:
        score += 0.5

    cp = s.get("color_probabilities", {}).get("historical_probability", {})
    next_green = cp.get("next_green_percentage", 50)
    next_red = cp.get("next_red_percentage", 50)
    max_color = max(next_green, next_red)
    if max_color > 75:
        score += 1.5
    elif max_color > 60:
        score += 1.0

    atr = s.get("latest_atr", 0)
    avg_atr = s.get("average_atr_20", 0.0005)
    if avg_atr > 0 and atr > avg_atr * 0.8:
        score += 0.5

    sr_break = s.get("support_resistance_break", {})
    if sr_break.get("retest_resistance") or sr_break.get("retest_support"):
        score += 1.0

    return round(max(0.0, min(10.0, score)), 1)


async def auto_scan_best_pair(client, category: str, pairs: list, top_n: int = 1, timeframe: int = 60) -> dict | None:
    scored = []
    for payout, code in pairs:
        try:
            tech = await asyncio.wait_for(
                fetch_and_process_indicators(client, code, payout, timeframe=timeframe),
                timeout=30.0
            )
        except (asyncio.TimeoutError, Exception):
            logger.warning(f"Auto-scan timeout/fail for {code}")
            continue
        if tech is None or tech == "LOW_VOLATILITY":
            continue
        math_score = score_pair_math(tech.get("summary", {}))
        scored.append((math_score, code, payout, tech))
        logger.info(f"Auto-scan {code}: math score {math_score}/10")

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    return {
        "code": best[1],
        "payout": best[2],
        "math_score": best[0],
        "tech_data": best[3],
        "all_scores": [(s[1], s[0]) for s in scored[:top_n]]
    }


# ─── TRADING PROMPT ──────────────────────────────────────────────────

TRADING_PROMPT_TEMPLATE = """
You are an ELITE QUOTEX OTC ALGORITHMIC TRADER and RISK MANAGER. Your job is to survive, not to gamble.
You are trading synthetic OTC assets, which are generated by the broker's proprietary algorithm. You must look for algorithmic cycles, color probabilities, round number magnets, and stop-hunt spikes.

### MISSION
Analyze the following technical telemetry data and determine if there is a trade setup.
You MUST make the final decision: "BUY" or "SELL". You are strictly FORBIDDEN from choosing "SKIP" or "NO-TRADE". Even in high-risk setups, you must weigh the pros and cons and select the direction with the higher mathematical probability of success.
Your primary goal is CAPITAL PROTECTION. Your secondary goal is HIGH PROBABILITY.

### DATA INPUT
{data_json}

### TIMEFRAME CONTEXT
The `analysis_timeframe_seconds` / `analysis_timeframe_label` fields in the data identify the candle timeframe that ALL primary indicators (`metrics_1m`, `ema_alignment`, `adx`, `bollinger_squeeze`, etc.) were computed on. Do NOT assume 1 minute. `metrics_5m` and `metrics_15m` (if present) are higher-timeframe context derived by resampling. Interpret every threshold relative to the analysis timeframe: sub-minute timeframes are noisier, higher timeframes trend cleaner.

### ANALYZE ALL 20 TRADING FACTORS BY TIER IN THIS EXACT ORDER

#### 🔴 TIER 1: SABSE STRONG FACTORS - 70% Weight (Ye na hon to signal mat lo)

**1. Trend Alignment - EMA Alignment (including EMA 200)**
- Check `ema_alignment` (9/20/50 alignment): "BULLISH_ALIGNED" = CALL bias, "BEARISH_ALIGNED" = PUT bias, "MIXED" = lower confidence.
- Check `ema_alignment_lti` (50/200 alignment): "BULLISH_ALIGNED_LTI" (Price > EMA50 > EMA200) = Strong CALL validation. "BEARISH_ALIGNED_LTI" (Price < EMA50 < EMA200) = Strong PUT validation. "MIXED" = do not trade against long-term trend.

**2. ADX - Trend Strength**
- Check `adx` and `adx_strength`: ADX > 25 = Trend strong (perfect for following trend). ADX < 20 = Sideways, range-bound market, avoid trend-following entries.

**3. MACD Crossover**
- Check `metrics_1m.macd_diff`: positive = momentum UP = BUY, negative = momentum DOWN = SELL. Check for crossover: MACD line crossing above signal line (bullish) or below (bearish).

**4. Support / Resistance Break & Retest**
- Check `support_resistance_break` object. A breakout happens when price breaks support_50/resistance_50. 
- Look for breakout and pullback: `retest_resistance` = True (Resistance broken and retested as support) = Strong BUY setup. `retest_support` = True (Support broken and retested as resistance) = Strong SELL setup.

#### 🟡 TIER 2: CONFIRMATION FACTORS - 20% Weight

**5. RSI - Overbought/Oversold**
- Check `rsi_directional` object: `rsi_value` < 30 + `rsi_rising` = oversold turning up = BUY. `rsi_value` > 70 + `rsi_falling` = overbought turning down = SELL.

**6. Stochastic Oscillator**
- Check `stochastic_strict` object: `%K` < 20 and `bullish_cross_strict` (crossing `%D` upward below 20) = BUY. `%K` > 80 and `bearish_cross_strict` (crossing `%D` downward above 80) = SELL.

**7. Bollinger Bands Squeeze & Confluences**
- Check `bollinger_squeeze` object: `bb_squeeze` = True indicates a squeeze (consolidation). A breakout follows expansion.
- Check confluences: `bb_rsi_buy_confluence` = True (price touches lower band + RSI < 30) = BUY. `bb_rsi_sell_confluence` = True (price touches upper band + RSI > 70) = SELL.

**8. Volume / Tick Volume Trend Analysis**
- Check `volume_trend` object: `volume_increasing` = True shows volatility interest. 
- `volume_trend_bullish` = True (uptrend + volume increasing) = BUY. `volume_trend_bearish` = True (downtrend + volume increasing) = SELL.

**9. Candlestick Pattern at Level Context**
- Check `candlestick_at_level` object: `bullish_pinbar_at_support` = True (Hammer/Pin bar formed at support_50) = Strong BUY. `bearish_pinbar_at_resistance` = True (Shooting Star formed at resistance_50) = Strong SELL.

**10. HTF Alignment - Higher Timeframe**
- Compare `metrics_1m.trend` vs `metrics_5m.trend` vs `metrics_15m.trend` (if available). Same direction = high probability. Trade matching HTF direction.

#### 🟢 TIER 3: EXTRA FILTERS - 10% Weight

**11. CCI - Commodity Channel Index**
- Check `cci`: CCI > 100 = strong uptrend (BUY bias). CCI < -100 = strong downtrend (SELL bias).

**12. Money Flow Index (MFI)**
- Check `mfi` object: `mfi_value` < 20 = oversold. `mfi_value` > 80 = overbought. `mfi_bullish_divergence` = True (price lower low but MFI higher low) = BUY.

**13. Williams %R**
- Check `williams_r`: Williams %R < -80 and rising = BUY. Williams %R > -20 and falling = SELL.

**14. ATR - Volatility**
- Check `latest_atr` vs `average_atr_20`. High ATR = strong volatility and larger movements. Do not use for direction, but to confirm trading activity level.

**15. Awesome Oscillator (AO)**
- Check `awesome_oscillator` object: `ao_value` > 0 and `ao_cross_up` (crossing above zero line) = BUY. `ao_value` < 0 and `ao_cross_down` (crossing below zero line) = SELL.

**16. Pivot Points**
- Check `pivot_points` object: `pivot_break_up` = True (price crossing above Pivot) or `r1_break_up` = True (price crossing above R1 resistance) = BUY. Price below Pivot / S1 cross down = SELL.

**17. Ichimoku Cloud**
- Check `ichimoku` object: `ichimoku_bullish` = True (price above cloud and Tenkan > Kijun) = BUY. Price below cloud and Tenkan < Kijun = SELL.

**18. OTC Color Probability**
- Check `color_probabilities` object: `next_green_percentage` between 59% and 85% = BUY. `next_red_percentage` between 59% and 85% = SELL.

**19. Timeframe Matching**
- The analysis timeframe (`analysis_timeframe_label`) must be aligned with the higher timeframe trend configuration (`metrics_5m` / `metrics_15m`, if available). Trade with the HTF trend.

**20. Session Filter**
- Check `session_filter` object: `is_london_ny_overlap` = True indicates highest volume period (London/NY overlap).

### DECISION RULE (ALWAYS SIGNALS: STRICTLY BUY OR SELL)
1. You are strictly FORBIDDEN from choosing "SKIP" or "NO-TRADE". You MUST choose "BUY" or "SELL".
2. Weigh all 20 factors. Calculate Tier 1 (70% weight), Tier 2 (20% weight), and Tier 3 (10% weight) confluences.
3. Select the direction with the higher mathematical probability.
4. Set "direction": "BUY" or "SELL" (never skip), and assign a confidence score (ranging from 50 to 95).
5. Recommend a Martingale recovery level ("M0", "M1", or "M2").

### CHAIN OF THOUGHT MANDATE
You MUST perform step-by-step mathematical derivations. Fill out the "chain_of_thought_reasoning" fields, referencing the specific factor numbers (1-20) and their Tiers in your reasoning.

### OUTPUT RULES - STRICT JSON ONLY
You MUST output only a valid JSON object. No extra text.
### CONCISE OUTPUT REQUIREMENT (CRITICAL FOR REAL-TIME)
This is a real-time trading pipeline. Every string field MUST be short and concise (≤ 30 words). No essays, no long derivations. The shorter the response, the fresher the signal.
{{
  "token": "string",
  "direction": "string, strictly 'BUY' or 'SELL'",
  "confidence": int (50-95),
  "martingale_recommendation": "string, 'M0', 'M1', or 'M2'",
  "chain_of_thought_reasoning": {{
    "step_1_tier_1_strong_factors": "string (analyze factors 1-4)",
    "step_2_tier_2_confirmation_factors": "string (analyze factors 5-10)",
    "step_3_tier_3_extra_filters": "string (analyze factors 11-20)"
  }},
  "analysis": {{
    "tier_1_summary": "string",
    "tier_2_summary": "string",
    "tier_3_summary": "string"
  }},
  "reason": "string"
}}
"""


# ─── PROMPT 2: DEEPSEEK SCREENER (Gate Guard) ─────────────────────────

SCREENER_PROMPT_TEMPLATE = """
You are a GATE GUARD screener for Quotex OTC trading signals. Your ONLY job is to quickly check if this pair has a viable setup. You can and MUST say SKIP if the setup is weak.

### MISSION
Check only TIER 1 factors. If they don't align, output SKIP. Only PASS if setup is clear.

### DATA INPUT
{data_json}

### TIER 1 FACTORS TO CHECK
1. EMA Alignment (9/20/50): BULLISH_ALIGNED or BEARISH_ALIGNED? MIXED = weak.
2. ADX Strength: > 25 = trend strong. < 20 = range-bound, skip.
3. MACD Momentum: macd_diff positive or negative? Clear direction?
4. Support/Resistance Break: breakout + retest detected?

### DECISION
- If 3+ factors align in same direction → PASS
- If 2 or fewer align or market is unclear → SKIP

### OUTPUT - STRICT JSON ONLY
{{"decision": "PASS or SKIP", "directional_bias": "BUY or SELL or NEUTRAL", "reason": "brief reason"}}
"""


# ─── PROMPT 3: DIFFUSION GEMMA ELITE ANALYST (20-Factor Analysis) ────

ANALYST_PROMPT_TEMPLATE = """
You are an ELITE QUOTEX OTC ALGORITHMIC TRADER and RISK MANAGER. Your job is to survive, not to gamble.
You are trading synthetic OTC assets, generated by the broker's proprietary algorithm. Look for algorithmic cycles, color probabilities, round number magnets, and stop-hunt spikes.

### MISSION
Analyze the following technical telemetry data and decide the best course of action. You may choose BUY, SELL, or SKIP if no clear setup exists.

### DATA INPUT
{data_json}

### ANALYZE ALL 20 TRADING FACTORS BY TIER IN THIS EXACT ORDER

#### TIER 1: STRONG FACTORS - 70% Weight

**1. Trend Alignment - EMA Alignment (including EMA 200)**
- Check `ema_alignment` (9/20/50): BULLISH_ALIGNED = CALL bias, BEARISH_ALIGNED = PUT bias, MIXED = lower confidence.
- Check `ema_alignment_lti` (50/200): BULLISH_ALIGNED_LTI = Strong CALL, BEARISH_ALIGNED_LTI = Strong PUT.

**2. ADX - Trend Strength**
- ADX > 25 = trend strong. ADX < 20 = range-bound, avoid trend-following.

**3. MACD Crossover**
- `macd_diff`: positive = momentum UP, negative = momentum DOWN.

**4. Support / Resistance Break & Retest**
- `retest_resistance` = True → Strong BUY. `retest_support` = True → Strong SELL.

#### TIER 2: CONFIRMATION FACTORS - 20% Weight

**5. RSI** - `rsi_value` < 30 + rising = BUY. > 70 + falling = SELL.

**6. Stochastic** - K < 20 + bullish_cross = BUY. K > 80 + bearish_cross = SELL.

**7. Bollinger Bands** - squeeze + bb_rsi_buy/sell confluence.

**8. Volume** - volume_increasing + direction.

**9. Candlestick Pattern at Level** - pinbar at support/resistance.

**10. HTF Alignment** - `analysis_timeframe_label` trend matches `metrics_5m`/`metrics_15m` trend (if available).

#### TIER 3: EXTRA FILTERS - 10% Weight

**11. CCI** - > 100 = uptrend, < -100 = downtrend.

**12. MFI** - < 20 oversold, > 80 overbought, divergence.

**13. Williams %R** - < -80 rising = BUY, > -20 falling = SELL.

**14. ATR** - compare latest vs average for volatility confirmation.

**15. Awesome Oscillator** - zero-line cross.

**16. Pivot Points** - pivot/r1 break.

**17. Ichimoku** - price above/below cloud.

**18. OTC Color Probability** - next_green/red 59-85%.

**19. Timeframe Matching** - `analysis_timeframe_label` aligned with `metrics_5m`/`metrics_15m` trend (if available).

**20. Session Filter** - London/NY overlap.

### DECISION
Weigh factors. Choose BUY, SELL, or SKIP. Assign confidence 50-95 if trading.

### OUTPUT - STRICT JSON ONLY
{{
  "direction": "BUY or SELL or SKIP",
  "confidence": int (50-95, 0 if SKIP),
  "martingale_recommendation": "M0, M1, or M2",
  "chain_of_thought_reasoning": {{
    "step_1_tier_1": "analysis of factors 1-4",
    "step_2_tier_2": "analysis of factors 5-10",
    "step_3_tier_3": "analysis of factors 11-20"
  }},
  "analysis": {{
    "tier_1_summary": "string",
    "tier_2_summary": "string",
    "tier_3_summary": "string"
  }},
  "reason": "string"
}}
"""


# ─── PROMPT 4: GEMINI RISK JUDGE ──────────────────────────────────────

RISK_JUDGE_PROMPT_TEMPLATE = """
You are a RISK JUDGE for Quotex OTC trading signals. You have FINAL AUTHORITY. You can approve, downgrade, reverse, or reject the analyst's decision.

### INPUT
- Analyst Decision: {analyst_result}
- Technical Data: {data_json}

### YOUR TASK
Check these risk factors against the analyst's decision:
1. Overbought/Oversold extremes - RSI > 85 or < 15? (higher risk)
2. Volatility risk - ATR spike? (unstable)
3. Low color probability (< 55%)
4. Mixed EMA alignment on HTF
5. ADX < 20 (no trend = unreliable)
6. SMT divergence conflicting with direction
7. Counter-trend signals against EMAs

### DECISION OPTIONS
- **APPROVED**: analyst is correct, keep their direction and confidence
- **DOWNGRADED**: direction is right but confidence too high, reduce it
- **REVERSED**: analyst picked wrong direction, YOU flip it (e.g. SELL -> BUY)
- **REJECTED**: too many risks / unclear market, no trade

If you REVERSE, provide your own direction and confidence.

### OUTPUT - STRICT JSON ONLY
{{"decision": "APPROVED or DOWNGRADED or REVERSED or REJECTED", "direction": "BUY or SELL or null", "final_confidence": int (0-95), "reason": "risk assessment"}}
"""


# ─── AI: NEMOTRON 3.5 LIGHTNING 30B VIA NVIDIA (replaces MiMo V2.5 / Zen) ──

MIMO_ZEN_KEY = os.getenv("MIMO_ZEN_KEY", "sk-9wvf1O4OyqST9iQzklxU2PQOPxlw8I0hKEtakaDKgJNg6wOFrRvRY0146DJsdaoD")
mimo_client = OpenAI(base_url="https://api.kilo.ai/api/gateway", api_key=os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34"), timeout=120.0)


def _coerce_dict(data):
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return None


def _extract_json_obj(text: str) -> str | None:
    """Pull the JSON object '{...}' out of a noisy model response (thinking preamble, fences, etc.)."""
    if not text:
        return None
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def _parse_model_output(text: str) -> dict | None:
    """Best-effort parse of a model's answer to a dict.

    Handles fenced/clean JSON (json.loads) and the single-quoted dicts some
    models (Nemotron) return instead of strict JSON (ast.literal_eval).
    """
    json_str = _extract_json_obj(text)
    if not json_str:
        return None
    try:
        return _coerce_dict(json.loads(json_str))
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        import ast
        return _coerce_dict(ast.literal_eval(json_str))
    except (SyntaxError, ValueError):
        return None


async def query_gemini_analysis(tech_data: dict) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    try:
        completion = await asyncio.to_thread(
            mimo_client.chat.completions.create,
            model="nvidia/nemotron-3.5-lightning:free",
            messages=[
                {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, max_tokens=AI_OUTPUT_MAX_TOKENS
        )
        text = completion.choices[0].message.content.strip()
        if not text:
            logger.warning("MiMo returned empty response")
            return None
        text = text.replace("```json", "").replace("```", "").strip()
        return _coerce_dict(json.loads(text))
    except Exception as e:
        logger.error(f"MiMo failed: {e}")
        return None


async def query_gemini_analysis_bulk(tech_data_list: list) -> dict | None:
    return await query_gemini_analysis(tech_data_list[0] if tech_data_list else {})


# ─── AI: STEP 3.5 FLASH RISK JUDGE VIA NVIDIA ────────────────────────

STEP_NVIDIA_API_KEY = "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"
step_nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=STEP_NVIDIA_API_KEY)


async def query_step_analysis(tech_data: dict, retries: int = 2) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    for attempt in range(retries + 1):
        try:
            logger.info(f"Querying Step 3.5 Flash (attempt {attempt+1})...")
            completion = await asyncio.to_thread(
                step_nvidia_client.chat.completions.create,
                model="stepfun-ai/step-3.5-flash",
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, top_p=0.7, max_tokens=AI_OUTPUT_MAX_TOKENS,
            )
            text = completion.choices[0].message.content
            if not text:
                logger.warning(f"Step attempt {attempt+1}: empty response, retrying...")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            text = text.replace("```json", "").replace("```", "").strip()
            return _coerce_dict(json.loads(text))
        except json.JSONDecodeError as e:
            logger.warning(f"Step attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.error(f"Step attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: DIFFUSION GEMMA (GOOGLE) VIA NVIDIA ──────────────────────────

NVIDIA_API_KEY = "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"
nvidia_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_API_KEY)


DIFFUSION_GEMMA_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["BUY", "SELL", "SKIP"]},
        "confidence": {"type": "integer"},
        "martingale_recommendation": {"type": "string"},
        "chain_of_thought_reasoning": {
            "type": "object",
            "properties": {
                "step_1_tier_1": {"type": "string"},
                "step_2_tier_2": {"type": "string"},
                "step_3_tier_3": {"type": "string"}
            },
            "required": ["step_1_tier_1", "step_2_tier_2", "step_3_tier_3"],
            "additionalProperties": False
        },
        "analysis": {
            "type": "object",
            "properties": {
                "tier_1_summary": {"type": "string"},
                "tier_2_summary": {"type": "string"},
                "tier_3_summary": {"type": "string"}
            },
            "required": ["tier_1_summary", "tier_2_summary", "tier_3_summary"],
            "additionalProperties": False
        },
        "chart_analysis": {
            "type": "object",
            "properties": {
                "visual_trend": {"type": "string"},
                "key_levels_seen": {"type": "string"},
                "pattern_at_price": {"type": "string"},
                "telemetry_agreement": {"type": "string"},
                "visual_signal_override": {"type": "string"}
            },
            "required": ["visual_trend", "key_levels_seen", "pattern_at_price", "telemetry_agreement", "visual_signal_override"],
            "additionalProperties": False
        },
        "reason": {"type": "string"}
    },
    "required": ["direction", "confidence", "martingale_recommendation", "chain_of_thought_reasoning", "analysis", "reason"],
    "additionalProperties": False
}

# When the chart image is attached, chart_analysis must be filled in too.
DIFFUSION_GEMMA_RESPONSE_SCHEMA_WITH_CHART = {
    **DIFFUSION_GEMMA_RESPONSE_SCHEMA,
    "required": [
        "direction", "confidence", "martingale_recommendation",
        "chain_of_thought_reasoning", "analysis", "chart_analysis", "reason",
    ],
}


CHART_IMAGE_PROMPT_SECTION = """
### CHART IMAGE ANALYSIS (VISUAL CONFIRMATION) - MANDATORY
A live candlestick chart image for this asset IS ATTACHED to this message.
You MUST look at the chart image and use it as your PRIMARY visual confirmation layer.
You are FORBIDDEN from ignoring the chart image or answering purely from telemetry alone.

You MUST do all of the following from the chart image:
- Read the actual candle bodies and wicks: confirm the recent trend direction (higher highs / lower lows).
- Check the EMA lines on the chart: which side is price trading on, are they stacked bullish or bearish?
- Identify the candlestick pattern forming AT the current price (engulfing, pin bar, doji, etc.).
- Note visible support/resistance levels, round-number magnets, and stop-hunt spikes.
- Compare the chart picture against the telemetry: if they disagree, say so and lower confidence.

The "chart_analysis" block is REQUIRED. It MUST be filled from what you visually see on the chart,
NOT from telemetry alone:
  visual_trend (UP/DOWN/SIDEWAYS), key_levels_seen, pattern_at_price,
  telemetry_agreement (CONFIRMS/CONTRADICTS/NEUTRAL), visual_signal_override (BUY/SELL/NEUTRAL).
In "reason", START with one sentence describing what you saw on the chart
(e.g. "The chart shows...") so it is clear you viewed the image.
"""


async def query_glm_analysis(tech_data: dict, chart_b64: str | None = None) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA_WITH_CHART
    else:
        user_content = prompt
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA
    try:
        completion = await asyncio.to_thread(
            nvidia_client.chat.completions.create,
            model="meta/muse-glimmer-30b",
            messages=[
                {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2, top_p=0.7, max_tokens=AI_OUTPUT_MAX_TOKENS,
            response_format={"type": "json_schema", "json_schema": {"name": "trading_analysis", "strict": True, "schema": schema}}
        )
        text = completion.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = _coerce_dict(json.loads(text))
        if isinstance(data, dict):
            ca = data.get("chart_analysis")
            logger.info(f"Muse Glimmer response chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
        return data
    except Exception as e:
        logger.error(f"Muse Glimmer failed: {e}")
        return None


# Clear alias: Diffusion Gemma (Google) is the model behind query_glm_analysis.
# Kept backwards-compatible so test/scratch scripts calling query_glm_analysis still work.
query_diffusion_gemma_analysis = query_glm_analysis


# ─── AI: GEMINI FLASH (FAST CHART-CAPABLE) VIA GOOGLE ─────────────────

GEMINI_FLASH_API_KEY = os.getenv("GEMINI_FLASH_API_KEY", "AIzaSyCdU-8xsePobK9Z8wk7DF6Ao0GRsV5-0PI")
# NOTE: the requested "gemini-2.5-flash" returns 404 on this key (deprecated for
# new users). "gemini-3.1-flash-lite" is the fastest chart-capable flash model
# available on the key (~4s, fills chart_analysis). Override via .env if needed.
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-3.1-flash-lite")


async def query_gemini_flash_analysis(tech_data: dict, chart_b64: str | None = None, retries: int = 2) -> dict | None:
    """Chart-capable analyst on Gemini Flash — replaces the slow 30B Muse Glimmer.

    Same prompt, same chart attachment, same JSON schema — but ~4s and capped at
    AI_OUTPUT_MAX_TOKENS, so the chart model no longer throttles the signal.
    Uses the native Gemini generateContent API (OpenAI-compat endpoint rejects
    older flash models on this key).
    """
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        parts = [
            {"inline_data": {"mime_type": "image/png", "data": chart_b64}},
            {"text": prompt},
        ]
    else:
        parts = [{"text": prompt}]

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "systemInstruction": {"parts": [{"text": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": AI_OUTPUT_MAX_TOKENS,
            "temperature": 0.2,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FLASH_MODEL}:generateContent"

    for attempt in range(retries + 1):
        try:
            response = await asyncio.to_thread(
                requests.post, url, params={"key": GEMINI_FLASH_API_KEY}, json=payload, timeout=90.0
            )
            if response.status_code != 200:
                logger.warning(f"Gemini Flash attempt {attempt+1} failed ({response.status_code}): {response.text[:300]}")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            res = response.json()
            parts_out = res.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts_out).strip()
            if not text:
                logger.warning(f"Gemini Flash attempt {attempt+1}: empty response, retrying...")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            text = text.replace("```json", "").replace("```", "").strip()
            data = _coerce_dict(json.loads(text))
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                logger.info(f"Gemini Flash response chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Gemini Flash attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.error(f"Gemini Flash attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: STEP 3.7 FLASH VIA KILO CODE GATEWAY ─────────────────────────

KILO_API_KEY = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
KILO_BASE_URL = os.getenv("KILO_BASE_URL", "https://api.kilo.ai/api/gateway")
KILO_MODEL = os.getenv("KILO_MODEL", "stepfun/step-3.7-flash:free")
# Step 3.7 Flash spends most output tokens on hidden reasoning; 2048 is NOT enough
# (finish=length, empty content). It needs its own larger budget regardless of
# the global AI_OUTPUT_MAX_TOKENS used by the faster text models.
KILO_MAX_TOKENS = int(os.getenv("KILO_MAX_TOKENS", "8192"))
kilo_client = OpenAI(base_url=KILO_BASE_URL, api_key=KILO_API_KEY, timeout=AI_MODEL_TIMEOUT_SECONDS)


async def query_kilo_step_analysis(tech_data: dict, chart_b64: str | None = None, retries: int = 2) -> dict | None:
    """Chart-capable analyst on Step 3.7 Flash via the Kilo Code gateway.

    Same prompt, same chart attachment, same JSON schema as the Gemini Flash
    and Muse Glimmer paths — kept pluggable so the two chart models can be
    A/B tested for speed (CHART_MODEL=kilo|gemini).
    """
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        user_content = prompt

    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                kilo_client.chat.completions.create,
                model=KILO_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=KILO_MAX_TOKENS,
            )
            text = completion.choices[0].message.content or ""
            if not text:
                logger.warning(f"Kilo Step attempt {attempt+1}: empty response, retrying...")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            text = text.replace("```json", "").replace("```", "").strip()
            data = _coerce_dict(json.loads(text))
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                logger.info(f"Kilo Step response chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Kilo Step attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.error(f"Kilo Step attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: CLAUDE OPUS 5 ────────────────────────────────────────────────

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "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")

async def query_claude_analysis(tech_data: dict, retries: int = 2) -> dict | None:
    summary_data = tech_data.get("summary", tech_data)
    data_json = json.dumps([summary_data], separators=(',', ':'))
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": "claude-opus-5",
        "max_tokens": 4096,
        "thinking": {"type": "disabled"},
        "system": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'.",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    for attempt in range(retries + 1):
        try:
            logger.info(f"Querying Claude Opus 5 (attempt {attempt+1})...")
            response = await asyncio.to_thread(
                requests.post,
                url,
                json=payload,
                headers=headers,
                timeout=120.0
            )
            if response.status_code != 200:
                logger.warning(f"Claude attempt {attempt+1} failed ({response.status_code}): {response.text}")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            
            res_json = response.json()
            content_blocks = res_json.get("content", [])
            text = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    break
            
            if not text:
                logger.warning(f"Claude attempt {attempt+1}: empty text, retrying...")
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            
            import re
            text = text.replace("```json", "").replace("```", "").strip()
            # Clean trailing commas
            text = re.sub(r',\s*([\]}])', r'\1', text)
            # Escape raw newlines inside JSON strings
            cleaned_chars = []
            in_string = False
            escape = False
            for char in text:
                if char == '"' and not escape:
                    in_string = not in_string
                    cleaned_chars.append(char)
                elif char == '\\' and in_string:
                    escape = not escape
                    cleaned_chars.append(char)
                elif char == '\n' and in_string:
                    cleaned_chars.append('\\n')
                    escape = False
                elif char == '\r' and in_string:
                    escape = False
                else:
                    escape = False
                    cleaned_chars.append(char)
            text = "".join(cleaned_chars)
            return _coerce_dict(json.loads(text))
        except json.JSONDecodeError as e:
            logger.warning(f"Claude attempt {attempt+1}: JSON decode error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            logger.error(f"Claude failed after {retries+1} attempts: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: LING 3.0 TINY VIA KILO CODE ──────────────────────────────────

KILO_LING_MODEL = "inclusionai/ling-3.0-tiny:free"
KILO_LING_BASE_URL = os.getenv("KILO_LING_BASE_URL", "https://api.kilo.ai/api/gateway")
KILO_LING_API_KEY = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
kilo_ling_client = OpenAI(base_url=KILO_LING_BASE_URL, api_key=KILO_LING_API_KEY, timeout=AI_MODEL_TIMEOUT_SECONDS)


async def query_ling_vote(tech_data: dict, retries: int = 2) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                kilo_ling_client.chat.completions.create,
                model=KILO_LING_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, max_tokens=AI_OUTPUT_MAX_TOKENS
            )
            text = completion.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            if not text:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            return _coerce_dict(json.loads(text))
        except json.JSONDecodeError as e:
            logger.warning(f"Ling vote attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.warning(f"Ling vote attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: MUSE GLIMMER 30B (VISION) VIA NVIDIA ───────────────────────────

NVIDIA_NEMOTRON_API_KEY = os.getenv("NVIDIA_NEMOTRON_API_KEY", "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")
nvidia_nemotron_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_NEMOTRON_API_KEY)
# Muse Glimmer 30B (NVIDIA) is chart-capable and fills chart_analysis reliably.
# It is a hidden-reasoning model: with tiny caps (<~1536) it spends the whole
# budget on reasoning and returns content=None. 2048 lets it emit the JSON while
# still voting comfortably inside the signal deadline.
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "meta/muse-glimmer-30b")
NEMOTRON_MAX_TOKENS = int(os.getenv("NEMOTRON_MAX_TOKENS", "2048"))

# ─── AI: KILO-CODE VISION MODELS (FAST, REASONING DISABLED) ───────────
# Nemotron 3 Nano Omni (free, via kilo gateway) replaces NVIDIA Muse Glimmer.
# Dots3-Note Preview (free, via kilo gateway) replaces NVIDIA Llama Vision.
# reasoning is disabled + max_tokens kept low so both answer ~1-2s like Gemini.

KILO_NEMOTRON_NANO_API_KEY = os.getenv(
    "KILO_NEMOTRON_NANO_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6IjUzNzFmNzkxLThkMzItNGY2Zi05OTQzLTcxOTI2MTkyOWNjNiIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODcyMjI0MTMsImV4cCI6MTk0NDkwMjQxM30.OiT1WU5iOE3ubJIZHZTkJq4v4bX6GQEHhV0IN7hXEyI",
)
KILO_VISION_BASE_URL = "https://api.kilo.ai/api/gateway"

kilo_nemotron_client = OpenAI(
    base_url=KILO_VISION_BASE_URL, api_key=KILO_NEMOTRON_NANO_API_KEY,
    timeout=AI_MODEL_TIMEOUT_SECONDS)
KILO_NEMOTRON_NANO_MODEL = os.getenv("KILO_NEMOTRON_NANO_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
KILO_NEMOTRON_NANO_MAX_TOKENS = int(os.getenv("KILO_NEMOTRON_NANO_MAX_TOKENS", "1024"))

KILO_DOTS_NOTE_API_KEY = os.getenv(
    "KILO_DOTS_NOTE_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6IjkwMWI2N2Q3LTEzMmYtNDllNC05YTU1LTUxOGI0YTFlNDNjMSIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODcyMjI4NDMsImV4cCI6MTk0NDkwMjg0M30.vCqxNit9FdMmFT8hR67sTnDTFQUEmV1MwkBW2GgfBqE",
)
kilo_dots_client = OpenAI(
    base_url=KILO_VISION_BASE_URL, api_key=KILO_DOTS_NOTE_API_KEY,
    timeout=AI_MODEL_TIMEOUT_SECONDS)
KILO_DOTS_NOTE_MODEL = os.getenv("KILO_DOTS_NOTE_MODEL", "dots-studio/dots-3-note-preview:free")
KILO_DOTS_NOTE_MAX_TOKENS = int(os.getenv("KILO_DOTS_NOTE_MAX_TOKENS", "1024"))


async def query_nemotron_nano_vote(tech_data: dict, chart_b64: str | None = None, retries: int = 1) -> dict | None:
    """Nemotron 3 Nano Omni via kilo gateway — vision vote, reasoning disabled.

    Kill all thinking before the JSON: kilo's 'reasoning' param is set to off
    and max_tokens stays low (default 1024) so it answers in ~1-2s like Gemini.
    Does NOT use response_format (kilo rejects strict json_schema on this route).
    """
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        user_content = prompt
    for attempt in range(retries + 1):
        try:
            completion_task = asyncio.to_thread(
                kilo_nemotron_client.chat.completions.create,
                model=KILO_NEMOTRON_NANO_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY the JSON object. No thinking, no preamble, no markdown fences. Start with '{' and end with '}'."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2, max_tokens=KILO_NEMOTRON_NANO_MAX_TOKENS,
                extra_body={"reasoning": {"enabled": False}},
            )
            repair_task = asyncio.create_task(
                _repair_chart_analysis_multi_image(kilo_nemotron_client, KILO_NEMOTRON_NANO_MODEL, chart_b64)
            ) if chart_b64 else None
            completion = await completion_task
            msg = completion.choices[0].message
            text = (msg.content or "").strip()
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                if ca and isinstance(ca, dict):
                    logger.info(f"Nemotron Nano chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
                elif repair_task:
                    logger.warning("Nemotron Nano skipped chart_analysis, using chart-only repair...")
                    repair = await repair_task
                    if repair:
                        data["chart_analysis"] = repair
            return data
        except Exception as e:
            logger.warning(f"Nemotron Nano vote attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


async def query_dots_note_vote(tech_data: dict, chart_b64: str | None = None, retries: int = 1) -> dict | None:
    """Dots3-Note Preview via kilo gateway — vision vote, reasoning disabled.

    reasoning disabled + low max_tokens for a fast (~1-2s) chart-capable vote.
    """
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        user_content = prompt
    for attempt in range(retries + 1):
        try:
            completion_task = asyncio.to_thread(
                kilo_dots_client.chat.completions.create,
                model=KILO_DOTS_NOTE_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY the JSON object. No thinking, no preamble, no markdown fences. Start with '{' and end with '}'."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2, max_tokens=KILO_DOTS_NOTE_MAX_TOKENS,
                extra_body={"reasoning": {"enabled": False}},
            )
            repair_task = asyncio.create_task(
                _repair_chart_analysis_multi_image(kilo_dots_client, KILO_DOTS_NOTE_MODEL, chart_b64)
            ) if chart_b64 else None
            completion = await completion_task
            text = (completion.choices[0].message.content or "").strip()
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                if ca and isinstance(ca, dict):
                    logger.info(f"Dots3-Note chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
                elif repair_task:
                    logger.warning("Dots3-Note skipped chart_analysis, using chart-only repair...")
                    repair = await repair_task
                    if repair:
                        data["chart_analysis"] = repair
                        logger.info(f"Dots3-Note chart_analysis (repair): " + json.dumps(repair))
                    else:
                        logger.warning("Dots3-Note chart-only repair failed")
            return data
        except Exception as e:
            logger.warning(f"Dots3-Note vote attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


async def _repair_chart_analysis_multi_image(client, model: str, chart_b64: str, max_tokens: int = 1024, timeout: float = 60.0) -> dict | None:
    """Chart-only repair call that works on both OpenAI and kilo gateway routes:
    sends the image as a list payload (used by the two new kilo vision models).
    """
    if not chart_b64:
        return None
    try:
        completion = await asyncio.wait_for(asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
                    {"type": "text", "text": CHART_ONLY_PROMPT_TEMPLATE},
                ]},
            ],
            temperature=0.2, max_tokens=max_tokens,
            extra_body={"reasoning": {"enabled": False}},
        ), timeout=timeout)
        text = ((completion.choices[0].message.content or "") or "").strip()
        parsed = _parse_model_output(text)
        if isinstance(parsed, dict) and parsed.get("visual_trend"):
            return parsed
        return None
    except Exception as e:
        logger.warning(f"chart-only repair for {model} failed: {e}")
        return None


CHART_ONLY_PROMPT_TEMPLATE = (
    "Look carefully at the attached candlestick chart image."
    ' Reply with ONLY a JSON object, no other text, exactly this shape:\n'
    '{"visual_trend":"UP","key_levels_seen":"list the visible levels/round numbers","pattern_at_price":"candle pattern at the last price",'
    '"telemetry_agreement":"CONFIRMS or CONTRADICTS","visual_signal_override":"BUY or SELL"}\n'
    "visual_trend is UP/DOWN/SIDEWAYS. Fill every field from what you SEE in the image, not from any other data."
)


async def _repair_chart_analysis(client, model: str, chart_b64: str, max_tokens: int = 2048, timeout: float = 60.0) -> dict | None:
    """Ask a model a focused vision-only question to get the chart_analysis block.

    On NVIDIA, Muse Glimmer / Llama Vision often skip 'chart_analysis' when
    the image is buried at the front of a long trading prompt. A second, tiny
    image-only call reliably forces them to actually read the chart.
    """
    try:
        completion = await asyncio.wait_for(asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=[
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
                    {"type": "text", "text": CHART_ONLY_PROMPT_TEMPLATE},
                ]},
            ],
            temperature=0.2, top_p=0.7, max_tokens=max_tokens,
        ), timeout=timeout)
        msg = completion.choices[0].message
        content = (msg.content or "").strip()
        if not content:
            content = ((getattr(msg, "reasoning_content", None) or "") or "").strip()
        text = content
        parsed = _parse_model_output(text)
        if isinstance(parsed, dict) and parsed.get("visual_trend"):
            return parsed
        logger.warning(f"chart-only repair for {model}: unparsable response: {text[:200]!r}")
        return None
    except asyncio.TimeoutError:
        logger.warning(f"chart-only repair for {model}: timed out after {timeout:.0f}s")
        return None
    except Exception as e:
        logger.warning(f"chart-only repair for {model} failed: {e}")
        return None


async def query_nemotron_vote(tech_data: dict, chart_b64: str | None = None, retries: int = 1) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA_WITH_CHART
    else:
        user_content = prompt
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA
    for attempt in range(retries + 1):
        try:
            completion_task = asyncio.to_thread(
                nvidia_nemotron_client.chat.completions.create,
                model=NEMOTRON_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY the JSON object. No thinking, no preamble, no markdown fences. Start with '{' and end with '}'."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2, top_p=0.7, max_tokens=NEMOTRON_MAX_TOKENS,
                response_format={"type": "json_schema", "json_schema": {"name": "trading_analysis", "strict": True, "schema": schema}},
            )
            repair_task = asyncio.create_task(
                _repair_chart_analysis(nvidia_nemotron_client, NEMOTRON_MODEL, chart_b64)
            ) if chart_b64 else None
            if repair_task:
                logger.info("Muse Glimmer: chart-only repair running concurrently with main analysis")
            completion = await completion_task
            msg = completion.choices[0].message
            content = (msg.content or "").strip()
            if not content:
                reasoning = getattr(msg, "reasoning_content", None) or ""
                content = reasoning.strip()
            text = content
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                if ca and isinstance(ca, dict):
                    logger.info(f"Muse Glimmer chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
                elif repair_task:
                    logger.warning("Muse Glimmer skipped chart_analysis, using concurrent chart-only repair...")
                    repair = await repair_task
                    if repair:
                        data["chart_analysis"] = repair
                        logger.info(f"Muse Glimmer chart_analysis (repair): " + json.dumps(repair))
                    else:
                        logger.warning("Muse Glimmer chart-only repair failed")
            return data
        except Exception as e:
            logger.warning(f"Muse Glimmer vote attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: NVIDIA LLAMA 3.2 11B VISION INSTRUCT (FAST VISION MODEL) ──────

NVIDIA_LLAMA_API_KEY = os.getenv("NVIDIA_LLAMA_API_KEY", "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")
nvidia_llama_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_LLAMA_API_KEY)
LLAMA_MODEL = "meta/llama-3.2-11b-vision-instruct"
# Llama Vision truncates badly at tiny caps (finish=length) and then drops
# chart_analysis. Give it enough budget to emit the full JSON object.
LLAMA_MAX_TOKENS = int(os.getenv("LLAMA_MAX_TOKENS", "1024"))


async def query_llama_vote(tech_data: dict, chart_b64: str | None = None, retries: int = 1) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    if chart_b64:
        prompt = prompt.replace(
            "### TIMEFRAME CONTEXT",
            CHART_IMAGE_PROMPT_SECTION + "\n\n### TIMEFRAME CONTEXT"
        )
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_b64}"}},
            {"type": "text", "text": prompt},
        ]
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA_WITH_CHART
    else:
        user_content = prompt
        schema = DIFFUSION_GEMMA_RESPONSE_SCHEMA
    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                nvidia_llama_client.chat.completions.create,
                model=LLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY the JSON object. No thinking, no preamble, no markdown fences. Start with '{' and end with '}'."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2, top_p=0.7, max_tokens=LLAMA_MAX_TOKENS,
                response_format={"type": "json_schema", "json_schema": {"name": "trading_analysis", "strict": True, "schema": schema}},
            )
            text = completion.choices[0].message.content.strip()
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            if isinstance(data, dict):
                ca = data.get("chart_analysis")
                if ca and isinstance(ca, dict):
                    logger.info(f"Llama Vision response chart_analysis: " + (json.dumps(ca) if ca else "MISSING"))
                else:
                    logger.warning(f"Llama Vision skipped chart_analysis, running chart-only repair...")
                    repair = await _repair_chart_analysis(nvidia_llama_client, LLAMA_MODEL, chart_b64) if chart_b64 else None
                    if repair:
                        data["chart_analysis"] = repair
                        logger.info(f"Llama Vision chart_analysis (repair): " + json.dumps(repair))
                    else:
                        logger.warning("Llama Vision chart-only repair failed")
            return data
        except Exception as e:
            logger.warning(f"Llama Vision vote attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: LLM MODELS (Text-based, no chart) ────────────────────────────

LLM_NEMOTRON_ULTRA_KEY = os.getenv("OPENCODE_ZEN_KEY", "sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32")
llm_nemotron_ultra_client = OpenAI(base_url="https://opencode.ai/zen/v1", api_key=LLM_NEMOTRON_ULTRA_KEY, timeout=AI_MODEL_TIMEOUT_SECONDS)
LLM_NEMOTRON_ULTRA_MODEL = "nemotron-3-ultra-free"
# Nemotron Ultra used to be reasoning-heavy (chain-of-thought before the JSON),
# so it needed ~3072 tokens. reasoning is now disabled and the cap is lowered to
# keep its LLM vote fast like Llama.
LLM_NEMOTRON_MAX_TOKENS = int(os.getenv("LLM_NEMOTRON_MAX_TOKENS", "1024"))
# Baseline budget for the fast text LLMs (default 1024 keeps them quick).
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

NVIDIA_LLM_API_KEY = os.getenv("NVIDIA_NEMOTRON_API_KEY", "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")
nvidia_llm_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=NVIDIA_LLM_API_KEY)
LLM_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"

KILO_LLM_MODEL = "poolside/laguna-s-2.1:free"
KILO_LLM_BASE_URL = os.getenv("KILO_LLM_BASE_URL", "https://api.kilo.ai/api/gateway")
KILO_LLM_API_KEY = os.getenv("KILO_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbnYiOiJwcm9kdWN0aW9uIiwia2lsb1VzZXJJZCI6ImQyYjRjOTIwLTYwYTAtNGQwZS04ZjliLWQ4MDAyNjI5MzIwMCIsImFwaVRva2VuUGVwcGVyIjpudWxsLCJ2ZXJzaW9uIjozLCJpYXQiOjE3ODY1MTk4MjEsImV4cCI6MTk0NDE5OTgyMX0.WhsCfQWhMCyJzeacsekuRTurBjqQr6iEUwx4ln-SK34")
kilo_llm_client = OpenAI(base_url=KILO_LLM_BASE_URL, api_key=KILO_LLM_API_KEY, timeout=AI_MODEL_TIMEOUT_SECONDS)
# Laguna-S 2.1: reasoning disabled + 1024-token cap so it votes fast (was 2048).
LLM_LAGUNA_MAX_TOKENS = int(os.getenv("LLM_LAGUNA_MAX_TOKENS", "1024"))


async def query_llm_nemotron_ultra(tech_data: dict, retries: int = 2) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                llm_nemotron_ultra_client.chat.completions.create,
                model=LLM_NEMOTRON_ULTRA_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, max_tokens=LLM_NEMOTRON_MAX_TOKENS,
                extra_body={"reasoning": {"enabled": False}},
            )
            text = completion.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            if not text:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Nemotron Ultra attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.warning(f"Nemotron Ultra attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


async def query_llm_nvidia_nemotron(tech_data: dict, retries: int = 2) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                nvidia_llm_client.chat.completions.create,
                model=LLM_NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, top_p=0.7, max_tokens=LLM_MAX_TOKENS
            )
            text = completion.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            if not text:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"NVIDIA Nemotron Super attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.warning(f"NVIDIA Nemotron Super attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


async def query_llm_kilo_ling(tech_data: dict, retries: int = 2) -> dict | None:
    data_json = json.dumps([tech_data], indent=2)
    prompt = TRADING_PROMPT_TEMPLATE.format(data_json=data_json)
    for attempt in range(retries + 1):
        try:
            completion = await asyncio.to_thread(
                kilo_llm_client.chat.completions.create,
                model=KILO_LLM_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, max_tokens=LLM_LAGUNA_MAX_TOKENS,
                extra_body={"reasoning": {"enabled": False}},
            )
            text = completion.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            if not text:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            data = _parse_model_output(text)
            if data is None:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"Kilo LLM Ling attempt {attempt+1}: JSON error ({e}), retrying...")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
        except Exception as e:
            logger.warning(f"Kilo LLM Ling attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            return None
    return None


# ─── AI: VOTE ─────────────────────────────────────────────────────────

CRYPTO_COMMODITY_PAIRS = {
    "XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "LTCUSD", "BCHUSD",
    "XRPUSD", "ADAUSD", "DOTUSD", "SOLUSD", "AVAUSD", "BNBUSD",
    "ETCUSD", "TRUUSD", "TONUSD", "LINUSD", "ATOUSD", "AXSUSD",
    "DASUSD", "XPDUSD", "XPTUSD", "UKBrent", "USCrude",
}

def get_pair_category(pair_code: str) -> str:
    if "_otc" in pair_code.lower():
        return "OTC"
    code = pair_code.upper().replace("_OTC", "")
    if code in CRYPTO_COMMODITY_PAIRS:
        return "CRYPTO"
    return "REAL"


def data_timestamp_seconds(tech_data: dict) -> float | None:
    """Epoch seconds of the newest closed candle in the analyzed data.

    Used by the freshness guard to detect when the AI's inputs have gone stale.
    """
    candles = (tech_data or {}).get("candles") or []
    for c in reversed(candles):
        t = c.get("time")
        if t:
            return float(t)
    return None


def quick_direction_check(summary: dict) -> str:
    """Fast deterministic BUY/SELL/NEUTRAL read on fresh data.

    Used to re-validate an AI signal when the original data became stale —
    running the full 3-model pipeline again would reintroduce the latency.
    """
    s = summary or {}
    m1 = s.get("metrics_1m", {}) or {}
    score = 0.0
    if s.get("ema_alignment") == "BULLISH_ALIGNED":
        score += 1.0
    elif s.get("ema_alignment") == "BEARISH_ALIGNED":
        score -= 1.0
    macd_diff = m1.get("macd_diff") or 0
    score += 1.0 if macd_diff > 0 else (-1.0 if macd_diff < 0 else 0.0)
    rsi = m1.get("rsi", 50) or 50
    if rsi < 30:
        score += 0.5
    elif rsi > 70:
        score -= 0.5
    cp = s.get("color_probabilities", {}).get("historical_probability", {}) or {}
    green = cp.get("next_green_percentage", 50) or 50
    red = cp.get("next_red_percentage", 50) or 50
    if green > red + 5:
        score += 0.5
    elif red > green + 5:
        score -= 0.5
    if score >= 1.5:
        return "BUY"
    if score <= -1.5:
        return "SELL"
    return "NEUTRAL"


def _process_vote_result(name, res, votes, confidences, reasons, model_details) -> bool:
    """Fold one model's response into the vote tally. Returns True on a valid vote."""
    if isinstance(res, Exception) or res is None:
        logger.warning(f"{name} failed, skipping vote")
        return False
    if not isinstance(res, dict):
        logger.warning(f"{name} returned non-dict result ({type(res).__name__}), skipping vote")
        return False

    direction = str(res.get("direction", "")).upper()
    direction = "BUY" if direction in ("BUY", "UP") else ("SELL" if direction in ("SELL", "DOWN") else None)
    if not direction:
        logger.warning(f"{name} returned invalid direction: {res.get('direction')}")
        return False

    votes[direction] += 1
    conf = int(res.get("confidence", 50))
    confidences.append(conf)
    reason = res.get("reason", "")
    line = f"{name}: {direction} ({conf}%) - {reason}"
    chart_analysis = res.get("chart_analysis") or {}
    if isinstance(chart_analysis, dict):
        ca = " | ".join(
            f"{k}: {v}" for k, v in (
                ("Visual chart", chart_analysis.get("visual_trend")),
                ("Levels seen", chart_analysis.get("key_levels_seen")),
                ("Pattern at price", chart_analysis.get("pattern_at_price")),
                ("Telemetry agreement", chart_analysis.get("telemetry_agreement")),
                ("Visual override", chart_analysis.get("visual_signal_override")),
            ) if v
        )
        if ca:
            line = f"{line}\n   👁️ CHART SEEN BY {name}: {ca}"
    reasons.append(line)
    model_details.append({"model": name, "direction": direction, "confidence": conf})
    chart_trend = chart_analysis.get("visual_trend") if isinstance(chart_analysis, dict) else None
    logger.info(f"{name} votes {direction} ({conf}%)" + (f" | chart: {chart_trend}" if chart_trend else ""))
    return True


async def query_all_models(tech_data: dict, pair_code: str = "", original_pair: str = None, chart_b64: str | None = None) -> dict:
    summary = tech_data.get("summary", tech_data) if isinstance(tech_data, dict) else tech_data

    logger.info(f"Voting system: Running 3 vision models for {pair_code}" + (" (all 3 analyze the chart image)" if chart_b64 else ""))

    async def _guarded(name, coro):
        try:
            return name, await asyncio.wait_for(coro, timeout=AI_MODEL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"{name} timed out after {AI_MODEL_TIMEOUT_SECONDS:.0f}s")
            return name, None
        except Exception as e:
            logger.warning(f"{name} failed: {e}")
            return name, None

    # Kick all 3 models off concurrently, but only wait for as long as we need.
    # We stop as soon as 2 models agree (majority) or the deadline passes.
    # Model lineup (all three are vision-capable and get the same chart image):
    #   1. Gemini Flash (chart-capable, first model)
    #   2. Nemotron 3 Nano Omni via Kilo (second model, reasoning disabled, fast)
    #   3. Dots3-Note Preview via Kilo (third model, reasoning disabled, fast)
    if CHART_MODEL == "gemini":
        chart_label = "Gemini Flash"
        chart_coro = query_gemini_flash_analysis(summary, chart_b64=chart_b64)
    else:
        chart_label = "Step 3.7 Flash"
        chart_coro = query_kilo_step_analysis(summary, chart_b64=chart_b64)
    pending = {
        chart_label: _guarded(chart_label, chart_coro),
        "Nemotron 3 Nano": _guarded("Nemotron 3 Nano", query_nemotron_nano_vote(summary, chart_b64=chart_b64)),
        "Dots3-Note": _guarded("Dots3-Note", query_dots_note_vote(summary, chart_b64=chart_b64)),
    }
    pending_tasks = {asyncio.ensure_future(coro): name for name, coro in pending.items()}

    votes = {"BUY": 0, "SELL": 0}
    confidences = []
    reasons = []
    model_details = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + AI_VOTE_DEADLINE_SECONDS

    while pending_tasks:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        done, _ = await asyncio.wait(pending_tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            name, res = fut.result()
            _process_vote_result(name, res, votes, confidences, reasons, model_details)
            pending_tasks.pop(fut, None)
        if votes["BUY"] >= 2 or votes["SELL"] >= 2:
            logger.info(f"Majority reached after {loop.time() - (deadline - AI_VOTE_DEADLINE_SECONDS):.0f}s, cancelling remaining models")
            break

    for fut in pending_tasks:
        fut.cancel()

    logger.info(f"Vote fast-path done: BUY={votes['BUY']}, SELL={votes['SELL']} "
                f"(models voted: {[d['model'] for d in model_details]})")

    if votes["BUY"] >= 2:
        final_direction = "BUY"
    elif votes["SELL"] >= 2:
        final_direction = "SELL"
    elif votes["BUY"] > votes["SELL"]:
        final_direction = "BUY"
    else:
        final_direction = "SELL"

    avg_confidence = int(sum(confidences) / len(confidences)) if confidences else 60
    final_confidence = max(50, min(95, avg_confidence))

    final_reason = "\n".join(reasons) if reasons else "No model provided reasoning."
    logger.info(f"Vote result: BUY={votes['BUY']}, SELL={votes['SELL']} -> {final_direction} ({final_confidence}%)")

    note = ""
    if original_pair and original_pair != pair_code:
        note = f"Note: Your pair ({original_pair}) had low setup. Auto-selected {pair_code} instead."

    return {
        "direction": final_direction,
        "confidence": final_confidence,
        "reason": final_reason,
        "martingale_recommendation": "M1" if final_confidence >= 75 else "M0",
        "note": note,
    }


async def query_all_llm_models(tech_data: dict, pair_code: str = "", original_pair: str = None) -> dict:
    summary = tech_data.get("summary", tech_data) if isinstance(tech_data, dict) else tech_data

    logger.info(f"LLM Voting system: Running 3 LLM models for {pair_code}")

    async def _guarded(name, coro):
        try:
            return name, await asyncio.wait_for(coro, timeout=LLM_MODEL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"{name} timed out after {LLM_MODEL_TIMEOUT_SECONDS:.0f}s")
            return name, None
        except Exception as e:
            logger.warning(f"{name} failed: {e}")
            return name, None

    pending = {
        "Nemotron 3 Ultra": _guarded("Nemotron 3 Ultra", query_llm_nemotron_ultra(summary)),
        "Llama 3.1 8B": _guarded("Llama 3.1 8B", query_llm_nvidia_nemotron(summary)),
        "Laguna-S 2.1": _guarded("Laguna-S 2.1", query_llm_kilo_ling(summary)),
    }
    pending_tasks = {asyncio.ensure_future(coro): name for name, coro in pending.items()}

    votes = {"BUY": 0, "SELL": 0}
    confidences = []
    reasons = []
    model_details = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + LLM_VOTE_DEADLINE_SECONDS

    while pending_tasks:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        done, _ = await asyncio.wait(pending_tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            name, res = fut.result()
            _process_vote_result(name, res, votes, confidences, reasons, model_details)
            pending_tasks.pop(fut, None)
        if votes["BUY"] >= 2 or votes["SELL"] >= 2:
            logger.info(f"LLM Majority reached after {loop.time() - (deadline - LLM_VOTE_DEADLINE_SECONDS):.0f}s, cancelling remaining models")
            break

    for fut in pending_tasks:
        fut.cancel()

    logger.info(f"LLM Vote fast-path done: BUY={votes['BUY']}, SELL={votes['SELL']} "
                f"(models voted: {[d['model'] for d in model_details]})")

    if votes["BUY"] >= 2:
        final_direction = "BUY"
    elif votes["SELL"] >= 2:
        final_direction = "SELL"
    elif votes["BUY"] > votes["SELL"]:
        final_direction = "BUY"
    else:
        final_direction = "SELL"

    avg_confidence = int(sum(confidences) / len(confidences)) if confidences else 60
    final_confidence = max(50, min(95, avg_confidence))

    final_reason = "\n".join(reasons) if reasons else "No model provided reasoning."
    logger.info(f"LLM Vote result: BUY={votes['BUY']}, SELL={votes['SELL']} -> {final_direction} ({final_confidence}%)")

    note = ""
    if original_pair and original_pair != pair_code:
        note = f"Note: Your pair ({original_pair}) had low setup. Auto-selected {pair_code} instead."

    return {
        "direction": final_direction,
        "confidence": final_confidence,
        "reason": final_reason,
        "martingale_recommendation": "M1" if final_confidence >= 75 else "M0",
        "note": note,
    }


# ─── SIGNAL FORMATTING ───────────────────────────────────────────────

def format_telegram_signal(signal: dict) -> str:
    token = signal.get("token", "EURUSD_otc")
    direction = signal.get("direction", "UP")
    confidence = signal.get("confidence", 0)
    reason = signal.get("reason", "")
    note = signal.get("note", "")
    martingale = signal.get("martingale_recommendation", "M0")
    timeframe = int(signal.get("timeframe_seconds", 60))
    timeframe_label = signal.get("timeframe_label") or format_timeframe_label(timeframe)

    is_otc = "_otc" in token.lower()
    display = token.replace("_otc", "").replace("_OTC", "")
    if len(display) == 6:
        display = display[:3] + "/" + display[3:]
    if is_otc:
        pair_label = f"{display} (OTC)"
    else:
        pair_label = display

    martingale_label = {"M0": "M0 (No Martingale)", "M1": "M1 (1-Step Martingale Safe)", "M2": "M2 (2-Step Martingale Aggressive)"}.get(martingale, martingale)

    PKT = timezone(timedelta(hours=5))
    now_pkt = datetime.now(PKT)
    now_ts = now_pkt.timestamp()
    elapsed = int(now_ts % timeframe)
    remaining = timeframe - elapsed
    if remaining == timeframe:
        remaining = 0
    candle_start = now_pkt.replace(microsecond=0) - timedelta(seconds=elapsed)
    next_start = candle_start + timedelta(seconds=timeframe)
    trade_time = next_start.strftime("%H:%M:%S")

    if remaining == 0:
        countdown = "0s"
    else:
        countdown = f"{remaining}s"

    if direction.upper() in ("BUY", "UP"):
        signal_emoji = "📈"
        signal_text = "BUY (UP)"
    else:
        signal_emoji = "📉"
        signal_text = "SELL (DOWN)"

    data_ts = signal.get("data_timestamp")
    data_age_line = ""
    if data_ts:
        try:
            captured = datetime.fromtimestamp(data_ts, tz=PKT)
            age_secs = max(0, int(now_ts - data_ts))
            data_age_line = f"\nData captured: {captured.strftime('%H:%M:%S')} PKT (fresh, {age_secs}s old)"
        except Exception:
            data_age_line = ""

    parts = [
        "\U0001f4ca NEXT CANDLE SIGNAL",
        f"Pair: {pair_label}",
        f"Timeframe: {timeframe_label}",
        f"Signal: {signal_emoji} {signal_text}",
        f"Confidence: {confidence}%",
        f"Trade Time: {trade_time}",
        f"Martingale: {martingale_label}",
    ]
    if data_age_line:
        parts.append(data_age_line)
    parts += [
        "",
        f"\u23f1\ufe0f Current candle ends in: {countdown}",
        "",
        f"Wait for the current {timeframe_label} candle to finish. Place the {timeframe_label} trade at the Trade Time above.",
    ]
    if note:
        parts.append("")
        parts.append(note)
    if reason:
        parts.append("")
        parts.append(f"Reason:\n{reason}")
    return "\n".join(parts)
