import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# Setup logging
logging.basicConfig(level=logging.INFO)

async def test_all():
    load_dotenv()
    
    # Patch pyquotex base url before importing main
    from pyquotex.network.login import Login
    Login.base_url = "market-qx.trade"
    Login.https_base_url = "https://market-qx.trade"
    
    import main
    
    print("\n=== STARTING END-TO-END TEST ===")
    
    # Test Step 1: Config check
    print("\n--- TEST 1: Config Check ---")
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    gemini_key = os.getenv("GEMINI_API_KEY")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    print(f"Quotex Email: {email}")
    print(f"Quotex Password: {'*' * len(password) if password else None}")
    print(f"Gemini API Key: {'*' * 10 if gemini_key else None}")
    print(f"Telegram Bot Token: {bot_token[:10]}...")
    
    if not all([email, password, gemini_key, bot_token]):
        print("FAIL: Missing credentials in .env")
        return
    print("PASS: Credentials configured.")
    
    # Test Step 2: Quotex Connection
    print("\n--- TEST 2: Quotex Connection ---")
    client = None
    try:
        client = await main.get_quotex_connection()
        is_connected = await client.check_connect()
        print(f"Connected to Quotex: {is_connected}")
        if is_connected:
            print("PASS: Connected successfully.")
        else:
            print("FAIL: Connection check failed.")
            return
    except Exception as e:
        print(f"FAIL: Quotex Connection failed with error: {e}")
        return
        
    # Test Step 3: Fetching and technical calculation
    print("\n--- TEST 3: Volatility & Technical Calculations ---")
    try:
        # Test scan on EURUSD_otc
        token = "EURUSD_otc"
        print(f"Fetching indicators for {token}...")
        tech_data = await main.fetch_and_process_indicators(client, token)
        if tech_data == "LOW_VOLATILITY":
            print(f"PASS/LOW_VOLATILITY: {token} has low volatility right now. Technical indicators calculated but filtered.")
        elif tech_data is None:
            print("FAIL: Failed to fetch candles / calculate indicators.")
            return
        else:
            print("PASS: Indicators calculated successfully.")
            print(f"Summary keys: {list(tech_data['summary'].keys())}")
            print(f"Latest Close: {tech_data['summary']['current_price']}, RSI: {tech_data['summary']['metrics_1m']['rsi']:.2f}")
    except Exception as e:
        print(f"FAIL: Technical calculation failed with error: {e}")
        return

    # Test Step 4: Gemini AI Analysis
    print("\n--- TEST 4: Gemini AI Analysis ---")
    try:
        # Bullish context
        mock_bullish_data = {
            "summary": {
                "token": "EURUSD_otc",
                "current_price": 1.0850,
                "latest_atr": 0.0008,
                "average_atr_20": 0.0006,
                "metrics_1m": {
                    "rsi": 65.5,
                    "ema_20": 1.0830,
                    "ema_50": 1.0810,
                    "macd": 0.0002,
                    "macd_signal": 0.0001,
                    "macd_diff": 0.0001,
                    "bollinger_upper": 1.0870,
                    "bollinger_middle": 1.0835,
                    "bollinger_lower": 1.0800,
                    "support_50": 1.0790,
                    "resistance_50": 1.0860
                },
                "metrics_5m": {
                    "rsi": 62.0,
                    "ema_20": 1.0820,
                    "ema_50": 1.0805,
                    "macd": 0.0001,
                    "macd_signal": 0.00005,
                    "macd_diff": 0.00005,
                    "current_price_5m": 1.0845
                }
            },
            "candles": [
                {"time": 1720000000 + i*60, "open": 1.0800 + i*0.0001, "high": 1.0805 + i*0.0001, "low": 1.0798 + i*0.0001, "close": 1.0802 + i*0.0001}
                for i in range(40)
            ]
        }
        print("Querying AI for Bullish context...")
        ai_bullish_res = await main.query_gemini_analysis(mock_bullish_data)
        print(f"Bullish AI response: {ai_bullish_res}")
        
        # Bearish context
        mock_bearish_data = {
            "summary": {
                "token": "EURUSD_otc",
                "current_price": 1.0800,
                "latest_atr": 0.0008,
                "average_atr_20": 0.0006,
                "metrics_1m": {
                    "rsi": 34.5,
                    "ema_20": 1.0810,
                    "ema_50": 1.0830,
                    "macd": -0.0002,
                    "macd_signal": -0.0001,
                    "macd_diff": -0.0001,
                    "bollinger_upper": 1.0850,
                    "bollinger_middle": 1.0815,
                    "bollinger_lower": 1.0780,
                    "support_50": 1.0770,
                    "resistance_50": 1.0840
                },
                "metrics_5m": {
                    "rsi": 38.0,
                    "ema_20": 1.0825,
                    "ema_50": 1.0840,
                    "macd": -0.0001,
                    "macd_signal": -0.00005,
                    "macd_diff": -0.00005,
                    "current_price_5m": 1.0805
                }
            },
            "candles": [
                {"time": 1720000000 + i*60, "open": 1.0840 - i*0.0001, "high": 1.0842 - i*0.0001, "low": 1.0828 - i*0.0001, "close": 1.0831 - i*0.0001}
                for i in range(40)
            ]
        }
        print("Querying AI for Bearish context...")
        ai_bearish_res = await main.query_gemini_analysis(mock_bearish_data)
        print(f"Bearish AI response: {ai_bearish_res}")
        
        if (ai_bullish_res and "direction" in ai_bullish_res and 
            ai_bearish_res and "direction" in ai_bearish_res):
            print("PASS: AI returned valid JSON formats for both directions.")
            assert ai_bullish_res["direction"].strip().upper() == "UP", f"Expected Bullish to be UP, got {ai_bullish_res['direction']}"
            assert ai_bearish_res["direction"].strip().upper() == "DOWN", f"Expected Bearish to be DOWN, got {ai_bearish_res['direction']}"
            assert int(ai_bullish_res["confidence"]) >= 90, f"Expected Bullish confidence >= 90, got {ai_bullish_res['confidence']}"
            assert int(ai_bearish_res["confidence"]) >= 90, f"Expected Bearish confidence >= 90, got {ai_bearish_res['confidence']}"
            print("PASS: AI successfully predicted UP for bullish and DOWN for bearish conditions with 90%+ confidence!")
        else:
            print("FAIL: AI returned invalid format.")
            return
    except Exception as e:
        print(f"FAIL: AI analysis test failed with error: {e}")
        return

    # Test Step 5: Formatting Output
    print("\n--- TEST 5: Formatting Output ---")
    try:
        mock_signal_up = {
            "token": "EURUSD_otc",
            "direction": "UP",
            "confidence": 85,
            "reason": "Strong EMA crossover and RSI momentum supports UP."
        }
        formatted_up = main.format_telegram_signal(mock_signal_up)
        print("Formatted message (UP):")
        print("-" * 30)
        print(formatted_up)
        print("-" * 30)
        
        # Verify elements in output
        assert "NEXT CANDLE SIGNAL" in formatted_up, "Missing NEXT CANDLE SIGNAL header"
        assert "Pair: EUR/USD" in formatted_up, "Missing display name"
        assert "Signal: 📈 BUY (UP)" in formatted_up, "Missing BUY signal indicator"
        assert "Confidence: 85%" in formatted_up, "Missing Confidence output"
        assert "Trade Time:" in formatted_up, "Missing Trade Time indicator"
        assert "Current candle ends in:" in formatted_up, "Missing countdown timer"
        assert "DEMO account" in formatted_up, "Missing DEMO account disclaimer"
        print("PASS: Output formatting matches template rules perfectly.")
    except Exception as e:
        print(f"FAIL: Formatting verification failed: {e}")
        return

    print("\n=== E2E TEST COMPLETED ===")

if __name__ == "__main__":
    asyncio.run(test_all())
