import os
import sys
import asyncio
import json
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    load_dotenv()
    
    from openai import OpenAI
    api_key = "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"
    nvidia_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )
    
    # Mock technical data
    mock_tech_data = {"test": 123}
    
    prompt = f"Analyze the following technical data: {mock_tech_data} and return a JSON object with key 'result' and value 'success'."

    print("Sending prompt to stepfun-ai/step-3.7-flash without response_format and without system message...")
    try:
        completion = nvidia_client.chat.completions.create(
            model="stepfun-ai/step-3.7-flash",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        print("Raw Response:")
        print(completion.choices[0].message.content)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
