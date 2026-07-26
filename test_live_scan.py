import os
import sys
import asyncio
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def run_restricted_scan(main_module) -> dict:
    client = await main_module.get_quotex_connection()
    all_tech_data = []

    # STRICTLY FOCUS ONLY ON THESE PAIRS:
    active_tokens = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "XAUUSD_otc", "EURJPY_otc", "GBPJPY_otc", "AUDUSD_otc"]
    print(f"Scanning restricted list of high-liquidity pairs: {active_tokens}")

    for token in active_tokens:
        print(f"Scanning token: {token}")
        try:
            tech_data = await main_module.fetch_and_process_indicators(client, token)
            await asyncio.sleep(0.5)
            if tech_data is None or tech_data == "LOW_VOLATILITY":
                continue
            all_tech_data.append(tech_data)
        except Exception as e:
            print(f"Error scanning {token}: {e}")

    if not all_tech_data:
        fallback_token = active_tokens[0]
        print(f"No pairs passed volatility filter. Forcing fallback: {fallback_token}")
        tech_data = await main_module.fetch_and_process_indicators(client, fallback_token)
        if tech_data and tech_data != "LOW_VOLATILITY":
            all_tech_data.append(tech_data)

    ranked_tech_data = []
    for tech in all_tech_data:
        readiness = main_module.calculate_setup_readiness(tech)
        ranked_tech_data.append((readiness, tech))

    if not ranked_tech_data:
        fallback_token = active_tokens[0]
        return {
            "token": fallback_token,
            "direction": "NO-TRADE",
            "confidence": 0,
            "reason": "No technical telemetry data available to analyze."
        }

    ranked_tech_data.sort(key=lambda x: x[0], reverse=True)
    best_readiness, best_tech_data = ranked_tech_data[0]
    best_token = best_tech_data["summary"]["token"]
    
    print(f"Selected strongest candidate: {best_token} (Readiness: {best_readiness}/100). Querying LLM...")

    gemini_result = await main_module.query_gemini_analysis_bulk([best_tech_data])
    
    if not gemini_result or not isinstance(gemini_result, dict):
        return {
            "token": best_token,
            "direction": "NO-TRADE",
            "confidence": 0,
            "reason": "AI Decision System failed to respond or returned an invalid format."
        }

    ai_direction = str(gemini_result.get("direction", "SKIP")).strip().upper()
    confidence = gemini_result.get("confidence", 0)
    try:
        confidence = int(confidence)
    except Exception:
        confidence = 0
        
    reason = gemini_result.get("reason") or "No reason provided by the AI."
    
    if confidence < 80 or ai_direction == "SKIP":
        print(f"AI decided to SKIP this trade setup (AI Direction: {ai_direction}, Confidence: {confidence}%).")
        return {
            "token": best_token,
            "direction": "NO-TRADE",
            "confidence": confidence,
            "reason": reason
        }
        
    if ai_direction == "BUY":
        direction = "UP"
    elif ai_direction == "SELL":
        direction = "DOWN"
    else:
        direction = "NO-TRADE"

    return {
        "token": best_token,
        "direction": direction,
        "confidence": confidence,
        "reason": reason
    }

async def main():
    load_dotenv()
    import logging
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    
    # Patch pyquotex base url before importing main
    from pyquotex.network.login import Login
    Login.base_url = "market-qx.trade"
    Login.https_base_url = "https://market-qx.trade"
    
    import main
    
    print("\n=== STARTING RESTRICTED HIGH-LIQUIDITY SCAN LOOP ===")
    attempt = 1
    while True:
        print(f"\n--- ATTEMPT #{attempt} ---")
        try:
            result = await run_restricted_scan(main)
            direction = result.get('direction', 'NO-TRADE').strip().upper()
            if direction in ['UP', 'DOWN']:
                print("\n=== VALID SIGNAL DETECTED! ===")
                print(f"Token: {result.get('token')}")
                print(f"Direction: {result.get('direction')}")
                print(f"Confidence: {result.get('confidence')}%")
                print(f"Reason: {result.get('reason')}")
                
                print("\n--- Formatted Telegram Message ---")
                msg = main.format_telegram_signal(result)
                print(msg)
                print("==================================")
                break
            else:
                print("NO-TRADE signal returned. Waiting 5 seconds before next scan attempt...")
                await asyncio.sleep(5)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("Error encountered. Waiting 10 seconds...")
            await asyncio.sleep(10)
        attempt += 1

if __name__ == "__main__":
    asyncio.run(main())
