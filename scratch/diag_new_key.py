import os, sys, time
from openai import OpenAI

NEW_KEY  = "sk-lQJqjN6O1Ol6LEr3SMlCcP7vCvywGmtGmGu6ZKkbfPwC1NYVcB6VMsEZKXlOLYV4"
BASE_URL = "https://opencode.ai/zen/v1"

SIMPLE_MSG = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": "Just reply with the word: WORKING"}
]

def test_model(label, model, api_key):
    print("\n" + "="*60)
    print(f"Testing: {label}  (model={model})")
    client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=40.0)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=SIMPLE_MSG,
            temperature=0.0,
            max_tokens=50,
        )
        elapsed = time.time() - t0
        text = resp.choices[0].message.content if resp.choices else "(no choices)"
        print(f"SUCCESS in {elapsed:.1f}s")
        print(f"   Response: {text!r}")
        print(f"   Usage: {resp.usage}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"FAILED after {elapsed:.1f}s")
        print(f"   Error type : {type(e).__name__}")
        print(f"   Error detail: {e}")

print("=== Testing New API Key ===")
print(f"Key prefix: {NEW_KEY[:16]}...")
test_model("DeepSeek V4 Flash", "deepseek-v4-flash-free", NEW_KEY)
test_model("MiMo V2.5",         "mimo-v2.5-free",         NEW_KEY)
print("\n=== Done ===")
