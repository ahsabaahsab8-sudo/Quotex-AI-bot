import os
import sys
import json
import asyncio
from openai import OpenAI
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Patch pyquotex mirror
from pyquotex.network.login import Login
Login.base_url = "market-qx.trade"
Login.https_base_url = "https://market-qx.trade"

import main as main_module

async def test_hi(client, model_name):
    print(f"\n1. Sending 'hi' to model '{model_name}'...")
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "hi"}
            ],
            max_tokens=50
        )
        print("Success! Response from model:")
        print(completion.choices[0].message.content)
        return True
    except Exception as e:
        print(f"Failed to query model '{model_name}': {e}")
        return False

async def main():
    load_dotenv()
    nvidia_key = "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"
    model_name = "openai/gpt-oss-120b"
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nvidia_key
    )
    
    # Step 1: Send Hi
    hi_ok = await test_hi(client, model_name)
    if not hi_ok:
        print("\nAborting full test since 'hi' request failed.")
        return
        
    # Step 2: Fetch one real market pair and run full scan
    token = "EURUSD"
    payout = 82
    print(f"\n2. Connecting to Quotex to fetch data for real pair: {token}...")
    
    quotex_client = await main_module.get_quotex_connection()
    is_connected = await quotex_client.check_connect()
    if not is_connected:
        print("Failed to connect to Quotex.")
        return
        
    print(f"Connected. Fetching indicators for {token}...")
    tech_data = await main_module.fetch_and_process_indicators(quotex_client, token, payout=payout)
    
    if not tech_data or tech_data == "LOW_VOLATILITY":
        print(f"Failed to fetch telemetry or low volatility for {token}.")
        await quotex_client.close()
        return
        
    print("\nTelemetry data fetched successfully. Constructing prompt...")
    prompt = main_module.build_trading_prompt([tech_data])
    
    print(f"Querying '{model_name}' with full trading prompt...")
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise trading assistant. Your task is to output ONLY a valid JSON object matching the requested schema. Do not write any conversational text, introductory thoughts, explanations, or summaries outside the JSON object. Start your output directly with '{' and end with '}'."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            top_p=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        print("\nSuccess! AI Response content:")
        print(content)
        
        # Verify JSON format
        try:
            parsed = json.loads(content)
            print("\nVerification: JSON parsed successfully!")
        except Exception as je:
            print(f"\nVerification failed: Response was not valid JSON: {je}")
            
    except Exception as e:
        print(f"Failed to complete full scan with '{model_name}': {e}")
        
    await quotex_client.close()

if __name__ == "__main__":
    asyncio.run(main())
