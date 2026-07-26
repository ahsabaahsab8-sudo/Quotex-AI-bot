import os
import requests
import dotenv

dotenv.load_dotenv()
nvidia_key = "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"

# Step 1: List all models from Nvidia NIM API
print("Fetching models from Nvidia NIM API...")
url_models = "https://integrate.api.nvidia.com/v1/models"
headers = {"Authorization": f"Bearer {nvidia_key}"}

try:
    res = requests.get(url_models, headers=headers, timeout=15)
    print(f"List Models Status: {res.status_code}")
    if res.status_code == 200:
        models = [m["id"] for m in res.json().get("data", [])]
        print(f"Number of available models: {len(models)}")
        # Check if openai/gpt-oss-20b is in the list
        matches = [m for m in models if "gpt-oss" in m.lower() or "openai" in m.lower()]
        print(f"Matching model IDs for 'gpt-oss' or 'openai': {matches}")
    else:
        print(res.text)
except Exception as e:
    print(f"Error fetching models: {e}")

# Step 2: Query openai/gpt-oss-20b and openai/gpt-oss-120b directly
for model in ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]:
    print(f"\nDirect POST request to {model} (90s timeout)...")
    url_chat = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 50
    }

    try:
        res = requests.post(url_chat, headers=headers, json=payload, timeout=90)
        print(f"{model} Status: {res.status_code}")
        print(f"{model} Headers: {dict(res.headers)}")
        print(f"{model} Body: {res.text}")
    except Exception as e:
        print(f"Error during POST to {model}: {e}")
