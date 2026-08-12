"""
Diagnostic: Test DeepSeek V4 Flash and MiMo V2.5 via OpenCode Zen gateway.
Read-only investigation — does NOT modify any production code.
"""
import os, sys, time
from dotenv import load_dotenv

# Load .env from the project root
env_path = r"c:\Users\PC\Desktop\Quotex Signal\.env"
load_dotenv(dotenv_path=env_path)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed")
    sys.exit(1)

ZEN_KEY    = os.getenv("OPENCODE_ZEN_KEY", "sk-5UVZdq3bAXTbOm55FiX8LqZIy4gKz2VFs5MVdU7QFfsqXQ8evXzVDU3Y0Tc5qY32")
MIMO_KEY   = os.getenv("MIMO_ZEN_KEY",    "sk-9wvf1O4OyqST9iQzklxU2PQOPxlw8I0hKEtakaDKgJNg6wOFrRvRY0146DJsdaoD")
BASE_URL   = "https://opencode.ai/zen/v1"

SIMPLE_MSG = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user",   "content": 'Reply with exactly: {"ok": true}'}
]

def test_model(label: str, model: str, api_key: str):
    print(f"\n{'='*60}")
    print(f"Testing: {label}  (model={model})")
    print(f"Base URL: {BASE_URL}")
    print(f"API key prefix: {api_key[:12]}...")
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

if __name__ == "__main__":
    print("=== DeepSeek V4 + MiMo V2.5 Diagnostic ===")
    print(f"OPENCODE_ZEN_KEY from env: {'yes' if os.getenv('OPENCODE_ZEN_KEY') else 'NO (using hardcoded fallback)'}")
    print(f"MIMO_ZEN_KEY     from env: {'yes' if os.getenv('MIMO_ZEN_KEY') else 'NO (using hardcoded fallback)'}")

    test_model("DeepSeek V4 Flash", "deepseek-v4-flash-free", ZEN_KEY)
    test_model("MiMo V2.5",         "mimo-v2.5-free",         MIMO_KEY)

    print("\n=== Done ===")
