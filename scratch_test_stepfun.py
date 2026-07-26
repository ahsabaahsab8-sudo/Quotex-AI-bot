import os
import sys
import asyncio
from openai import OpenAI
from dotenv import load_dotenv

# Force standard stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
api_key = "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"
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

async def test_stepfun():
    try:
        print("Querying stepfun-ai/step-3.7-flash with response_format...")
        completion = client.chat.completions.create(
            model="stepfun-ai/step-3.7-flash",
            messages=[
                {"role": "user", "content": "Return a JSON object with a key 'test' and value 'hello'."}
            ],
            response_format={"type": "json_object"}
        )
        print("Success! Response:")
        print(completion.choices[0].message.content)
    except Exception as e:
        print(f"Failed with response_format: {e}")

    try:
        print("\nQuerying stepfun-ai/step-3.7-flash without response_format...")
        completion = client.chat.completions.create(
            model="stepfun-ai/step-3.7-flash",
            messages=[
                {"role": "user", "content": "Return a JSON object with a key 'test' and value 'hello'."}
            ]
        )
        print("Success! Response:")
        print(completion.choices[0].message.content)
    except Exception as e:
        print(f"Failed without response_format: {e}")

if __name__ == "__main__":
    asyncio.run(test_stepfun())
