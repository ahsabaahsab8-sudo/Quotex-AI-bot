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

async def test_glm():
    try:
        print("Querying google/diffusiongemma-26b-a4b-it...")
        completion = client.chat.completions.create(
            model="google/diffusiongemma-26b-a4b-it",
            messages=[
                {"role": "user", "content": "Return a JSON object with key 'test' and value 'hello'."}
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "test_response", "strict": True, "schema": {"type": "object", "properties": {"test": {"type": "string"}}, "required": ["test"], "additionalProperties": False}}}
        )
        print("Success! Response:")
        print(completion.choices[0].message.content)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_glm())
