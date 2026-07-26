import time
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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",
    timeout=60.0
)

try:
    start = time.time()
    completion = client.chat.completions.create(
        model="deepseek-ai/deepseek-v4-flash",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Output ONLY valid JSON."},
            {"role": "user", "content": 'Return {"status":"ok","message":"working"}'}
        ],
        temperature=0.2,
        max_tokens=200
    )
    elapsed = time.time() - start
    content = completion.choices[0].message.content
    print(f"SUCCESS! Response time: {elapsed:.1f}s")
    print(f"Content: {content}")
except Exception as e:
    print(f"FAILED: {e}")
