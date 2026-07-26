import time, json, asyncio
from openai import OpenAI

client = OpenAI(
    base_url="https://opencode.ai/zen/v1",
    api_key="sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32",
    timeout=120.0
)

async def test():
    start = time.time()
    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="deepseek-v4-flash-free",
            messages=[
                {"role": "system", "content": "You are a precise quantitative trading assistant. Output ONLY valid JSON. Start with '{' and end with '}'."},
                {"role": "user", "content": '{"test": "Return this as valid JSON with key: status, value: ok"}'}
            ],
            temperature=0.2,
            max_tokens=2048
        )
        elapsed = time.time() - start
        content = completion.choices[0].message.content
        print(f"SUCCESS! Response time: {elapsed:.1f}s")
        print(f"Content: {content}")
        return content
    except Exception as e:
        print(f"FAILED ({time.time()-start:.1f}s): {type(e).__name__}: {e}")
        return None

result = asyncio.run(test())
print(f"\nFinal result: {result is not None}")
