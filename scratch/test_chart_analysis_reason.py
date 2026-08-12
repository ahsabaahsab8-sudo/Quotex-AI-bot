# -*- coding: utf-8 -*-
"""Test chart_analysis append formatting."""
name = "Diffusion Gemma 26B"
direction = "SELL"
conf = 78
reason = "The asset is in a clear structural downtrend on multiple timeframes."
res = {
    "direction": "SELL", "confidence": 78, "reason": reason,
    "chart_analysis": {
        "visual_trend": "DOWN", "key_levels_seen": "0.9370 / 0.9400",
        "pattern_at_price": "bearish engulfing", "telemetry_agreement": "CONFIRMS",
        "visual_signal_override": "NEUTRAL",
    },
}
chart_analysis = res.get("chart_analysis") or {}
line = f"{name}: {direction} ({conf}%) - {reason}"
if isinstance(chart_analysis, dict) and chart_analysis.get("visual_trend"):
    ca = " | ".join(
        f"{k}: {v}" for k, v in (
            ("Visual chart", chart_analysis.get("visual_trend")),
            ("Levels seen", chart_analysis.get("key_levels_seen")),
            ("Pattern at price", chart_analysis.get("pattern_at_price")),
            ("Telemetry agreement", chart_analysis.get("telemetry_agreement")),
            ("Visual override", chart_analysis.get("visual_signal_override")),
        ) if v
    )
    line = line + "\n   \U0001F441 CHART SEEN BY " + name + ": " + ca
print(line)
print("---without chart_analysis---")
res2 = {"direction": "SELL", "confidence": 72, "reason": "plain telemetry"}
chart_analysis2 = res2.get("chart_analysis") or {}
line2 = f"{'DeepSeek V4 Flash'}: {res2['direction']} ({res2['confidence']}%) - {res2['reason']}"
print(line2)
