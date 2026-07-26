import time, os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    timeout=60.0
)

try:
    start = time.time()
    completion = client.chat.completions.create(
        model="deepseek-chat",
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
