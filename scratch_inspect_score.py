import asyncio
import os
import json
import logging
from dotenv import load_dotenv

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

from pyquotex.stable_api import Quotex
from main import fetch_and_process_indicators, evaluate_math_setup, get_quotex_connection, FALLBACK_TOKENS

logging.basicConfig(level=logging.INFO)

async def main():
    load_dotenv()
    client = await get_quotex_connection()
    
    try:
        instruments = await client.get_instruments()
        active_tokens = []
        for inst in instruments:
            code = inst[1]
            category = inst[3]
            is_open = inst[14]
            payout = inst[5]
            if category == "currency" and is_open and payout >= 70:
                active_tokens.append(code)
    except Exception as e:
        print(f"Error fetching live instruments: {e}")
        active_tokens = FALLBACK_TOKENS

    print(f"\nScanning {len(active_tokens)} active tokens:")
    for token in active_tokens[:10]:  # inspect first 10
        try:
            tech_data = await fetch_and_process_indicators(client, token)
            if tech_data is None:
                print(f"Token {token}: Failed to fetch indicators")
                continue
            if tech_data == "LOW_VOLATILITY":
                print(f"Token {token}: Low volatility")
                continue
            
            direction, score = evaluate_math_setup(tech_data)
            print(f"Token: {token} | Direction: {direction} | Math Score: {score}")
            print(f"  1m Trend: {tech_data['summary']['metrics_1m']['trend']}")
            print(f"  5m Trend: {tech_data['summary']['metrics_5m']['trend'] if tech_data['summary']['metrics_5m'] else 'N/A'}")
            print(f"  RSI 1m: {tech_data['summary']['metrics_1m']['rsi']:.2f}")
            print(f"  Price: {tech_data['summary']['current_price']:.5f} | Support: {tech_data['summary']['metrics_1m']['support_50']:.5f} | Resistance: {tech_data['summary']['metrics_1m']['resistance_50']:.5f}")
        except Exception as e:
            print(f"Error scanning {token}: {e}")
            
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
