# -*- coding: utf-8 -*-
"""Render a candlestick chart PNG from candle data for visual AI confirmation.

Headless (matplotlib Agg) — works on local Windows and on a display-less VPS.
Produces a dark-theme trading chart with EMAs, Bollinger bands, support/resistance
and a volume pane, encoded as base64 PNG for the Diffusion Gemma vision call.
"""
import base64
import io
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

UP_COLOR = "#00C510"
DOWN_COLOR = "#ff0000"
BG_COLOR = "#0b0e14"
GRID_COLOR = "#1b2333"
TEXT_COLOR = "#c8d0e0"
EMA_COLORS = {"ema_9": "#fbbf24", "ema_20": "#38bdf8", "ema_50": "#f472b6", "ema_200": "#a78bfa"}
BB_FILL = "#38bdf8"


def _candles_to_frame(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    for col in ("time", "open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    if "volume" not in df.columns:
        df["volume"] = 0.0
    else:
        df["volume"] = df["volume"].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.sort_values("time").reset_index(drop=True)
    return df


def _compute_emas(df: pd.DataFrame) -> dict[str, pd.Series]:
    closes = df["close"]
    return {
        "ema_9": closes.ewm(span=9, adjust=False).mean(),
        "ema_20": closes.ewm(span=20, adjust=False).mean(),
        "ema_50": closes.ewm(span=50, adjust=False).mean(),
        "ema_200": closes.ewm(span=200, adjust=False).mean(),
    }


def render_chart_to_png(
    candles: list[dict],
    summary: dict | None = None,
    token: str = "",
    timeframe: int = 60,
    max_candles: int = 120,
    width_px: int = 1200,
    height_px: int = 680,
) -> bytes | None:
    """Render candles to PNG bytes. Returns None on failure."""
    try:
        df = _candles_to_frame(candles)
        if df.empty:
            return None
        if len(df) > max_candles:
            df = df.iloc[-max_candles:].reset_index(drop=True)

        emas = _compute_emas(df)

        summary = summary or {}
        m1 = summary.get("metrics_1m", {}) or {}

        # Support/resistance for overlay (from indicator pipeline when present)
        s_levels = []
        if m1.get("support_50"):
            s_levels.append(("S50", float(m1["support_50"])))
        if m1.get("resistance_50"):
            s_levels.append(("R50", float(m1["resistance_50"])))
        pivot = summary.get("pivot_points", {}) or {}
        for key, label in (("pivot", "P"), ("r1", "R1"), ("s1", "S1")):
            val = pivot.get(key)
            if val:
                s_levels.append((label, float(val)))

        fig = plt.figure(figsize=(width_px / 100.0, height_px / 100.0), dpi=100, facecolor=BG_COLOR)
        gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 0.8], hspace=0.06, left=0.05, right=0.98, top=0.90, bottom=0.06)
        ax = fig.add_subplot(gs[0])
        ax_vol = fig.add_subplot(gs[1], sharex=ax)

        for a in (ax, ax_vol):
            a.set_facecolor(BG_COLOR)
            a.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.7)
            a.tick_params(colors=TEXT_COLOR, labelsize=8)
            for spine in a.spines.values():
                spine.set_color(GRID_COLOR)
        for a in (ax, ax_vol):
            a.set_axisbelow(True)

        # Candlesticks
        width_frac = 0.6
        if len(df) > 1:
            x_step = (df["time"].iloc[1] - df["time"].iloc[0]).total_seconds()
            width_frac = min(0.7, max(0.35, x_step / (x_step + x_step * 0.3)))
        x = mdates.date2num(df["time"])
        xc = x * 24 * 3600.0  # seconds for bar width math
        candle_w = width_frac * (xc[1] - xc[0]) if len(df) > 1 else 60.0

        for i in range(len(df)):
            o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
            color = UP_COLOR if c >= o else DOWN_COLOR
            ax.plot([x[i], x[i]], [l, h], color=color, linewidth=1.0, zorder=3)
            body = max(abs(c - o), (h - l) * 0.02)
            rect = Rectangle(
                (x[i] - candle_w / 2.0, min(o, c)), candle_w, body,
                facecolor=color, edgecolor=color, linewidth=0.5, zorder=4,
            )
            ax.add_patch(rect)

        # EMA overlays
        for name, series in emas.items():
            if name not in EMA_COLORS:
                continue
            if len(series) < 3:
                continue
            ax.plot(x, series.values, color=EMA_COLORS[name], linewidth=1.1, zorder=5, label=name.upper())

        # Bollinger bands
        bb = {"upper": m1.get("bollinger_upper"), "lower": m1.get("bollinger_lower"), "middle": m1.get("bollinger_middle")}
        if all(v not in (None, 0) for v in bb.values()):
            u = float(bb["upper"]); lw = float(bb["lower"]); md = float(bb["middle"])
            ax.axhline(u, color="#f59e0b", linewidth=0.8, linestyle="--", alpha=0.7)
            ax.axhline(lw, color="#f59e0b", linewidth=0.8, linestyle="--", alpha=0.7)
            ax.fill_between(x, u, lw, color=BB_FILL, alpha=0.06, zorder=1)

        # Support/resistance lines
        for label, val in s_levels:
            ax.axhline(val, color="#94a3b8", linewidth=0.8, linestyle=":", alpha=0.9)
            ax.text(x[0], val, f"  {label} {val:.5f}", color="#94a3b8", fontsize=7, va="bottom")

        # Last price line + label
        last_price = df["close"].iloc[-1]
        ax.axhline(last_price, color="#e2e8f0", linewidth=1.0, alpha=0.8)
        ax.text(x[-1], last_price, f"  {last_price:.5f}", color="#ffffff", fontsize=8, va="bottom", fontweight="bold")

        # Volume bars
        vol_scale = 1.0
        max_v = df["volume"].max() if df["volume"].max() > 0 else 1.0
        for i in range(len(df)):
            v = df["volume"].iloc[i]
            color = UP_COLOR if df["close"].iloc[i] >= df["open"].iloc[i] else DOWN_COLOR
            ax_vol.bar(x[i], v / max_v, width=candle_w, color=color, alpha=0.55, linewidth=0)

        title_parts = [token or "CANDLES"]
        if timeframe:
            from quotex_adapter import format_timeframe_label as _ftfl
            title_parts.append(f"({_ftfl(timeframe)})")
        title_parts.append(f"Last: {last_price:.5f}")
        ax.set_title("  ".join(title_parts), color="#e2e8f0", fontsize=11, fontweight="bold", loc="left", pad=8)

        ax.legend(loc="upper left", fontsize=7, facecolor=BG_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, ncol=4)
        ax_vol.set_ylabel("Vol", color=TEXT_COLOR, fontsize=8)
        ax_vol.set_yticks([])
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        for a in (ax, ax_vol):
            plt.setp(a.get_xticklabels(), rotation=0)
            a.tick_params(axis="x", colors=TEXT_COLOR, labelsize=8)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, facecolor=BG_COLOR)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"chart_render failed: {e}")
        return None


def render_chart_to_base64(
    candles: list[dict],
    summary: dict | None = None,
    token: str = "",
    timeframe: int = 60,
    max_candles: int = 120,
) -> str | None:
    """Render candles to a base64 PNG data URI (without the 'data:' prefix).

    Returns None on failure — callers should fall back to text-only analysis.
    """
    png = render_chart_to_png(candles, summary=summary, token=token, timeframe=timeframe, max_candles=max_candles)
    if not png:
        return None
    return base64.b64encode(png).decode("ascii")
