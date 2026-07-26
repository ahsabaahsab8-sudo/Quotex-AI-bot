import os
import asyncio
import sys
import json
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

import main as main_module

async def main():
    load_dotenv()
    email = os.getenv("QUOTEX_EMAIL")
    password = os.getenv("QUOTEX_PASSWORD")
    
    token = "XAUUSD_otc"
    payout = 91
    
    print(f"Connecting to Quotex to scan {token} (Payout: {payout}%)...")
    client = await main_module.get_quotex_connection()
    is_connected = await client.check_connect()
    if not is_connected:
        print("Failed to verify connection to Quotex.")
        return
        
    print("Connected successfully. Fetching indicators...")
    tech_data = await main_module.fetch_and_process_indicators(client, token, payout=payout)
    
    if tech_data is None:
        print("Failed to fetch indicators/candles.")
        return
    elif tech_data == "LOW_VOLATILITY":
        print("Skipped due to low volatility.")
        return
        
    print("Indicators fetched successfully. Querying AI model...")
    gemini_result = await main_module.query_deepseek_analysis(tech_data)
    
    if not gemini_result or not isinstance(gemini_result, dict):
        print("AI Decision System failed to respond or returned an invalid format.")
        return
        
    print("\n=== AI Decision Received ===")
    ai_direction = str(gemini_result.get("direction", "SKIP")).strip().upper()
    confidence = gemini_result.get("confidence", 0)
    martingale_rec = gemini_result.get("martingale_recommendation") or "M0"
    reason = gemini_result.get("reason") or "No reason provided by the AI."
    
    if ai_direction == "BUY":
        direction = "UP"
    elif ai_direction == "SELL":
        direction = "DOWN"
    else:
        direction = "UP"
        
    signal_dict = {
        "token": token,
        "direction": direction,
        "confidence": confidence,
        "reason": reason,
        "martingale_recommendation": martingale_rec
    }
    
    formatted_message = main_module.format_telegram_signal(signal_dict)
    print("\n--- Formatted Telegram Signal Output ---")
    print(formatted_message)
    print("----------------------------------------")
    
    await client.close()

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
