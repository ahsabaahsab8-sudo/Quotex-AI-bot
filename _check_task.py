import main
import inspect

src = inspect.getsource(main.compute_indicators)

checks = [
    ("EMA 200", "ema_200"),
    ("S/R Breakout/Retest", "support"),
    ("RSI Directional", "rsi_directional"),
    ("Stochastic Crossover", "stochastic"),
    ("BB Squeeze", "bollinger"),
    ("Volume Trend", "volume_ma"),
    ("Candlestick Pattern", "candlestick"),
    ("CCI", "cci"),
    ("MFI", "mfi"),
    ("Williams %R", "williams"),
    ("Awesome Oscillator", "awesome"),
    ("Pivot Points", "pivot"),
    ("Ichimoku", "ichimoku"),
    ("Session Filter", "session"),
]

print("=== Indicators in compute_indicators() ===")
all_ok = True
for name, kw in checks:
    found = kw.lower() in src.lower()
    if not found:
        all_ok = False
    print(f"  [{'OK' if found else 'XX'}] {name}")

print()
print("=== TRADING_PROMPT_TEMPLATE ===")
has = hasattr(main, "TRADING_PROMPT_TEMPLATE")
print(f"  Exists: {has}")
if has:
    print(f"  Length: {len(main.TRADING_PROMPT_TEMPLATE)} chars")

print()
print("=== test_single_scan_ai.py imported? ===")
print(f"  main.test_single_scan_ai attribute: {hasattr(main, 'test_single_scan_ai')}")

print()
print(f"ALL CHECKS PASSED: {all_ok}")