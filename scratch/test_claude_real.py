import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

url = "https://api.anthropic.com/v1/messages"
headers = {
    "x-api-key": "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",
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

payload = {
    "model": "claude-opus-5",
    "max_tokens": 1024,
    "thinking": {"type": "disabled"},
    "messages": [
        {"role": "user", "content": "Hello, world"}
    ]
}

print("Sending request...")
try:
    response = requests.post(url, json=payload, headers=headers)
    print("Status code:", response.status_code)
    try:
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print("Response text:", response.text)
except Exception as e:
    print("Error:", e)
